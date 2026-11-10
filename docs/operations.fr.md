# Fonctionnement

Ce document décrit le cycle de vie actuellement implémenté d’un bail et les limites opérationnelles connues de la synchronisation avec le backend d’accès.

## État du provisionnement WireGuard

Avant de démarrer APScheduler, le processus scheduler réconcilie l’état WireGuard avec les baux persistés. Il réapplique les peers actifs absents ou divergents, supprime les peers sans bail actif et restaure les jobs d’expiration. Les opérations WireGuard sont envoyées par SSH avec `sudo -n ttlama backend wg leases`. La réconciliation est exécutée au démarrage, pas périodiquement ; les opérations en attente et les suppressions échouées continuent d’être traitées par la scrutation du scheduler.

Les réseaux du profil deviennent les `AllowedIPs` du pair. Sur une même interface, deux réservations ne peuvent pas partager une clé publique ni des réseaux qui se chevauchent. Une réservation reste occupée tant que la suppression n’est pas confirmée. Après une application au résultat incertain, elle reste réservée même si une suppression ultérieure réussit : une commande distante tardive peut encore modifier l’état du pair.

Le fichier `/etc/ttl-lama/ssh_config.yml` définit la connexion, la clé privée et le fichier `known_hosts`. Les délais en secondes sont configurables par `TTL_LAMA_SSH_COMMAND_TIMEOUT` (30 par défaut), `TTL_LAMA_PROVISIONING_WAIT_SECONDS` (45) et `TTL_LAMA_SCHEDULER_POLL_INTERVAL` (1). L’attente API doit normalement dépasser le délai SSH et l’intervalle de scrutation.

Après `panic.retry` échecs consécutifs de réconciliation au démarrage (3 par défaut), le mode panic lance le script administrateur configuré et tente séparément l’envoi du courriel si celui-ci est activé. Le scheduler ne réalise pas d’action réseau supplémentaire en mode panic. L’absence de réconciliation périodique signifie qu’une dérive apparue pendant l’exécution ne sera corrigée qu’au prochain redémarrage du scheduler.

## Cycle de vie d’un bail

La création par `LeaseRepository.create()` valide l’identité, la propriété et l’état de l’appareil, l’affectation active du profil, sa politique et la durée demandée. Elle enregistre `ended_at` à partir de l’horloge UTC et crée une opération de provisioning `pending_apply` avec un snapshot immuable des paramètres backend. Le statut retourné par l’API est calculé, il n’est pas stocké :

| Statut API calculé | Condition, par ordre de priorité |
| --- | --- |
| `revoked` | `revoked_at` est renseigné |
| `expired` | `ended_at` est atteint |
| `pending` | Le provisioning n’est pas `applied` et aucune erreur n’est enregistrée |
| `failed` | Le provisioning n’est pas `applied` et contient une erreur |
| `active` | Le bail n’est ni révoqué ni échu et le provisioning est appliqué |

L’API attend la confirmation du provisioning avant de répondre au succès; un échec ou un délai dépassé produit une réponse d’échec et peut déclencher une compensation.

Les états persistés de `LeaseProvisioning` sont distincts du statut API :

```text
pending_apply -> applying -> applied -> deleting -> deleted
            |                      |
            +-> pending_delete      +-> pending_delete (échec, réessayé)
                 |                         |
                 +-> deleting -------------+
                    |
                    +-> uncertain (compensation d'une application échouée)
```

`pending_apply` attend l’application; `applying` est un claim écrit en base pendant l’appel backend. `applied` confirme l’accès et l’échéance est programmée. Une révocation ou une expiration rend l’accès non valide immédiatement dans l’état métier, puis demande `pending_delete`; `deleting` est le claim en base pendant l’appel de suppression. `deleted` confirme la suppression. Si une application échoue, TTL-LAMa demande une compensation; même après une suppression confirmée, le provisioning peut rester `uncertain`, car une commande distante tardive pourrait encore appliquer le pair. Une suppression échouée revient à `pending_delete` et est réessayée par la scrutation. Les états `applying` et `deleting` sont donc persistés temporairement, mais ne sont pas des états finaux. À la réconciliation de démarrage, chaque enregistrement est ramené à `applied` ou `deleted` selon l’état désiré.

### Expiration et révocation

Après la confirmation de l’application, APScheduler programme un job à `ended_at`. À son déclenchement, le scheduler relit l’état du bail et demande une suppression si le bail est révoqué ou échu. La révocation explicite renseigne `revoked_at` et demande aussi la suppression; le statut API devient `revoked` avant la fin de l’opération backend. Dans les deux cas, l’invariant est que l’accès d’un bail révoqué ou échu ne doit pas subsister.

### Propriété des clés

Dans la mesure du possible, les clients génèrent et conservent leurs propres clés privées. TTL-LAMa n’a besoin que de la clé publique nécessaire au provisionnement de l’appareil :

```text
Client                              TTL-LAMa
  | Génère une clé privée               |
  | Conserve la clé localement          |
  | Dérive la clé publique ------------>| Enregistre l’appareil
```

Le stockage d’une clé privée cliente ne doit pas être nécessaire au fonctionnement normal.

## Réconciliation

Au démarrage du processus scheduler, avant APScheduler, `LeaseScheduler.reconcile()` compare l’état désiré en base et les pairs observés par le backend. Il applique les pairs actifs absents ou divergents, supprime les pairs sans bail actif, restaure les jobs des baux encore valides et traite immédiatement les baux échus. Ainsi, un bail arrivé à échéance pendant l’arrêt ne récupère pas un accès lors du redémarrage.

La réconciliation complète ne s’exécute pas périodiquement. Après le démarrage, le scheduler scrute les seules opérations `pending_apply`, `pending_delete` et `uncertain`; cette scrutation n’est pas une comparaison complète de tous les pairs. Une dérive backend apparue pendant l’exécution ne sera donc réparée qu’au prochain redémarrage du scheduler.

```text
Base désirée + état backend observé
          |
          +-- démarrage : réconciliation complète et restauration des échéances
          `-- exécution : scrutation des opérations en attente
```

Les invariants sont :

```text
si ended_at <= now :         l’accès ne doit pas exister
si le bail est révoqué :     l’accès ne doit pas exister
si le bail est actif :       l’accès doit correspondre au bail
```

La base de données représente durablement l’état désiré ; le backend d’accès représente l’état réellement appliqué. La réconciliation maintient leur cohérence.

## Exemple de parcours

1. Alice s’authentifie.
2. TTL-LAMa identifie son compte et les profils d’accès autorisés.
3. Elle choisit son ordinateur, le profil `server-admin` et une durée de deux heures.
4. TTL-LAMa crée le bail et provisionne le pair WireGuard correspondant.
5. À l’expiration ou après une révocation explicite, TTL-LAMa supprime le pair.

Si Alice s’authentifie auprès d’un fournisseur d’identité externe, le déroulement du bail reste identique après l’authentification.

## Événements d’audit

Chaque ligne utilise le format UTC propre à son processus : `[TTL-LAMa API]-[yyyy-mm-dd HH:mm:ss] : <operation>-<Log>` ou `[TTL-LAMa Scheduler]-[yyyy-mm-dd HH:mm:ss] : <operation>-<Log>`. Le résultat est inclus dans le message (`succeeded`, `failed`, `requested` ou `superseded`); les niveaux `INFO`, `WARNING` et `ERROR` orientent les fichiers d’historique.

| Opérations | Origine et résultat journalisé | Métadonnées permises |
| --- | --- | --- |
| `lease.create`, `lease.revoke` | API : succès après commit ou échec de validation/persistance | ID du bail/appareil/profil au succès lorsque disponible; type d’erreur à l’échec |
| `lease.apply`, `lease.delete` | API : résultat confirmé par le scheduler, y compris échec ou délai dépassé | ID du bail et statut HTTP |
| `lease.provisioning.apply`, `lease.provisioning.delete` | Scheduler : résultat de l’opération backend | ID du bail et classe d’erreur ou code de sortie |
| `lease.expire` | Scheduler : suppression demandée puis expiration supprimée | ID du bail |
| `device.revoke` | API : révocation d’un appareil après commit | ID de l’appareil |
| `reconciliation.startup` | Scheduler : chaque tentative et résultat final | Numéro de tentative et classe d’erreur |
| `reconciliation.run` | Scheduler : réconciliation réussie | Nombre de baux et pairs actifs |
| `provisioning.poll`, `panic.script`, `panic.email` | Scheduler : erreurs de scrutation ou résultats des actions panic | Classe d’erreur uniquement |

Les métadonnées ne comprennent ni mot de passe, valeur de secret, jeton brut, clé privée, clé publique complète, corps de requête, sortie `stderr` distante ni message brut d’exception. `lease.create` est journalisé après le commit métier; `lease.apply` indique séparément la confirmation du backend. De même, `lease.revoke` précède le résultat backend `lease.delete`. Une suppression échouée reste en attente et est journalisée sous `lease.provisioning.delete` avant réessai. Les échecs de réconciliation au démarrage et de provisioning doivent déclencher une alerte opérationnelle; le mode panic peut exécuter le script administrateur après le nombre configuré de tentatives. Les journaux sont diagnostiques et ne remplacent pas un journal d’audit inviolable ou transactionnel.
