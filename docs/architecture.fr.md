# Architecture

TTL-LAMa est conçu comme un monolithe modulaire déployable dans un conteneur unique. Son modèle métier reste indépendant du fournisseur d’authentification, du backend de persistance et du backend d’accès réseau.

## Concepts fondamentaux

Le modèle métier repose sur quatre concepts :

```text
Identité -> Appareil -> Profil d’accès -> Bail -> Backend d’accès
```

### Identité et authentification

Une identité représente un utilisateur auquel TTL-LAMa peut accorder des droits. Deux modes d’authentification sont prévus :

- **`internal`** : TTL-LAMa gère les comptes et les mécanismes nécessaires à leur authentification, dont l’authentification multifacteur.
- **`external`** : l’authentification est déléguée à un fournisseur d’identité, initialement via OIDC.

Les deux modes produisent une identité utilisable par le cœur métier. La logique des baux, appareils et profils ne dépend pas de la manière dont cette identité a été authentifiée.

L’authentification interne peut utiliser n’importe quel backend de persistance pris en charge. Par exemple :

```yaml
auth:
  mode: internal
  admin:
    username: admin
    password_file: /run/secrets/admin_password

database:
  type: sqlite
  path: /data/ttl-lama.db
```

L’authentification externe se configure indépendamment :

```yaml
auth:
  mode: external
  oidc:
    issuer: https://identity.example.org
    client_id: ttl-lama
    client_secret_file: /run/secrets/oidc_client_secret
    redirect_uri: https://ttl-lama.example.org/auth/callback

database:
  type: postgresql
  host: postgres
  name: ttl_lama
  user: ttl_lama
  password_file: /run/secrets/database_password
  schema: public
```

Le fournisseur d’identité répond à la question **qui est l’utilisateur**. TTL-LAMa détermine à quoi il peut accéder, depuis quel appareil et pendant combien de temps.

### Appareil

L’identité d’un utilisateur et son identité VPN sont distinctes. Un utilisateur peut avoir plusieurs appareils, chacun possédant sa propre identité auprès du backend d’accès. Il est ainsi possible de révoquer un appareil sans révoquer l’utilisateur ni ses autres appareils.

Un bail s’applique à un appareil déterminé et non simplement à un utilisateur.

### Profil d’accès

Un profil d’accès est une politique définie par l’administrateur. Les utilisateurs choisissent parmi les profils qui leur sont autorisés ; ils ne peuvent pas fournir arbitrairement des réseaux ou des règles d’accès.

```yaml
backend:
  wireguard:
    interfaces:
      - name: wg0
        description: Administration serveur
        networks:
          - 192.168.10.0/24
        default_duration: 2h
        maximum_duration: 8h
        public_key: your_public_key_here
```

Ce document correspond au fichier `/etc/ttl-lama/backend_config.yml`. La description de l’interface devient le nom du profil et le nom de l’interface est enregistré comme `lease_target`.

### Bail d’accès

Un bail représente une autorisation temporaire accordée à une identité et à un appareil selon un profil d’accès. Il consigne ses dates de création et d’expiration ainsi que les informations nécessaires à l’application de l’accès.

```text
Identité + Appareil + Profil d’accès + Durée -> Bail
```

L’expiration fait partie de l’état désiré : lorsque `expires_at <= now`, le bail est expiré et l’accès provisionné doit être absent, y compris après un redémarrage de TTL-LAMa.

## Composants

```text
Utilisateur
  |
  v
TTL-LAMa
  |-- Authentification -> Identité
  |-- Autorisation -> Appareil -> Profil d’accès -> Bail
  |-- Provisionnement
  |-- Réconciliation
  `-- Audit
       |                 |
       v                 v
  Persistance       Backend d’accès
  SQLite / SQL      WireGuard / futur
```

### Authentification

Le module d’authentification produit une identité pour le cœur métier. Celui-ci ne dépend pas directement du mécanisme utilisé pour authentifier cette identité.

### Persistance

TTL-LAMa conserve son propre état métier, quel que soit le mode d’authentification. Celui-ci comprend les identités référencées, les appareils, les clés publiques, les profils et leurs associations, les baux, les événements d’audit et l’état de provisionnement.

L’authentification et la persistance sont deux choix indépendants :

| Authentification | Persistance | Usage typique |
| --- | --- | --- |
| `internal` | SQLite | Installation autonome |
| `internal` | PostgreSQL / MariaDB / MySQL | Installation autonome avec base externe |
| `external` / OIDC | SQLite | Fournisseur d’identité existant et déploiement léger |
| `external` / OIDC | PostgreSQL / MariaDB / MySQL | Infrastructure intégrée |

SQLite est le backend prévu par défaut pour une installation autonome. Les moteurs SQL externes pris en charge sont PostgreSQL, MariaDB et MySQL.

### Backend d’accès

Le backend d’accès matérialise un bail. La première implémentation cible les pairs WireGuard, tandis que le cœur métier reste indépendant des concepts spécifiques au backend afin que d’autres mécanismes puissent être envisagés.

## Organisation du code

Une première organisation logique pourrait être :

```text
ttl-lama/
├── identity/
│   ├── internal/
│   └── oidc/
├── devices/
├── access/
│   ├── profiles/
│   ├── leases/
│   └── policies/
├── backends/
│   ├── interface/
│   └── wireguard/
├── persistence/
│   ├── interface/
│   ├── sqlite/
│   └── external/
├── reconciliation/
├── audit/
├── config/
└── api/
```

Il s’agit d’un découpage logique au sein d’une application unique déployable, et non d’une architecture en microservices.

## Gestion dynamique de WireGuard et expiration des baux

Cette section décrit les choix structuraux retenus pour l'intégration de WireGuard et la gestion du cycle de vie des baux dans TTL-LAMa.

TTL-LAMa reste responsable des **baux d'accès**, de leur expiration et de leur révocation. WireGuard constitue le premier backend réseau, mais sa configuration d'infrastructure reste sous le contrôle de l'opérateur. 【1-a68036】

### Principes

L'intégration WireGuard repose sur les principes suivants :

- la configuration de base de l'interface WireGuard appartient à l'opérateur ;
- TTL-LAMa ne génère pas et ne remplace pas la configuration complète de l'interface ;
- les peers associés aux baux sont ajoutés et supprimés dynamiquement ;
- la base TTL-LAMa constitue la source de vérité concernant les accès qui doivent être actifs ;
- l'état de WireGuard est un état matérialisé dérivé des baux actifs ;
- les opérations d'ajout, de révocation et de réconciliation doivent être idempotentes.

Cette séparation permet à TTL-LAMa de gérer le cycle de vie des accès sans devenir une interface générale d'administration de WireGuard.

### Configuration WireGuard

L'opérateur configure l'interface WireGuard indépendamment de TTL-LAMa.

Par exemple :

```ini
[Interface]
Address = 10.42.0.1/24
ListenPort = 51820
PrivateKey = ...
```

Cette configuration est persistante et définit l'infrastructure du VPN. Les peers dynamiques ne sont pas persistés dans cette configuration par TTL-LAMa.

### Gestion dynamique des peers

Lorsqu'un bail devient actif, le backend WireGuard matérialise l'accès correspondant directement dans l'interface active. Une opération équivalente peut être réalisée avec :

```bash
wg set wg0 \
peer <PUBLIC_KEY> \
allowed-ips <VPN_ADDRESS>/32
```

Lorsqu'un bail expire ou est révoqué, le peer correspondant est supprimé :

```bash
wg set wg0 \
peer <PUBLIC_KEY> \
remove
```

L'interface WireGuard n'a donc pas besoin d'être redémarrée à chaque modification d'un bail.
Conceptuellement :

```text
Lease ACTIVE
      |
      v
WireGuard backend
|
      v
peer présent dans wg0
 
 
Lease EXPIRED / REVOKED
      |
      v
WireGuard backend
|
      v
peer absent de wg0
```

### Source de vérité

WireGuard ne constitue pas une base de données des accès. L'état désiré est déterminé à partir des baux TTL-LAMa :

```SQL
desired_peers =
  leases
  WHERE status = ACTIVE
  AND expires_at > now()
```

La persistance TTL-LAMa reste donc la source de vérité.
Cela permet notamment de reconstruire entièrement l'état dynamique de WireGuard après un redémarrage.

### Réconciliation des peers dynamiques

Un redémarrage du serveur peut provoquer la disparition des peers qui avaient été ajoutés dynamiquement à WireGuard. TTL-LAMa dispose donc d'un mécanisme de réconciliation permettant de reconstruire l'état attendu à partir des baux persistés.

La commande :

```bash
ttlama sync
```

déclenche cette réconciliation via l'API TTL-LAMa.
Conceptuellement :

```text
Base TTL-LAMa
      |
      | baux actuellement valides
      v
État désiré
      |
+---------------------+
|                     |
v                     v
Peers manquants       Peers indésirables
|                     |
v                     v
ADD                   REMOVE
\                    /
 +--------+---------+
          |
          v
         wg0
```

La réconciliation est volontairement bidirectionnelle.
Elle permet :

- de recréer les peers manquants après un redémarrage ;
- de supprimer un peer qui ne correspond plus à un bail valide ;
- de corriger une divergence entre l'état persistant de TTL-LAMa et l'état effectif du backend.

La réconciliation constitue ainsi un mécanisme de convergence vers l'état désiré, et non seulement un mécanisme de restauration après démarrage.

### Expiration des baux

La réconciliation ne remplace pas la gestion normale de l'expiration. TTL-LAMa doit également supprimer l'accès réseau lorsque le terme du bail est atteint, conformément à son objectif d'expiration et de révocation automatiques.

Deux mécanismes complémentaires existent donc :

```texte
                   TTL-LAMa
                       |
           +-----------+-----------+
           |                       |
           v                       v
      Scheduler              Réconciliation
           |                       |
    expiration normale        convergence
       des baux              de l'état réseau
           |                       |
           +-----------+-----------+
                       |
                       v
                Backend WireGuard
```

### Scheduler

TTL-LAMa étant une application synchrone, l'expiration est prise en charge par un processus dédié de scheduling. Ce processus peut utiliser APScheduler ou un mécanisme équivalent. Il est distinct des workers de l'API afin d'éviter qu'un scheduler soit créé dans chaque worker HTTP.

L'implémentation actuelle utilise APScheduler et transmet les commandes WireGuard par SSH. Les sections suivantes décrivent notamment la reconstruction et la réconciliation visées, qui ne sont pas encore implémentées ; voir [Fonctionnement](operations.fr.md) pour les limites actuelles.

L'architecture du conteneur devient :

```text
Conteneur TTL-LAMa
|
+-- superviseur (PID 1)
|
+-- application API
|   |
|   +-- worker 1
|   +-- worker 2
|   +-- ...
|   +-- worker N
|
+-- scheduler
```

Il existe toujours un seul scheduler logique, quel que soit le nombre de workers utilisés par l'API.

### Reconstruction du scheduler

Les tâches du scheduler ne constituent pas une source de vérité. À chaque démarrage ou redémarrage du processus scheduler, TTL-LAMa reconstruit les échéances à partir de sa base persistante.

Le démarrage suit conceptuellement la séquence suivante :

```texte
scheduler start
      |
      v
charger les baux actifs
      |
      +--> expires_at <= now()
      |        |
      |        v
      |   expiration immédiate
      |
      +--> expires_at > now()
               |
               v
          programmation
             du job
```

Une perte de l'état interne du scheduler n'entraîne donc pas une perte des échéances.

L'information autoritative reste `Lease.expires_at` et non le job enregistré dans le scheduleur.

### Traitement d'une échéance

Lorsqu'un job se déclenche, il ne doit pas considérer aveuglément que le bail doit être supprimé. Le bail est relu depuis la persistence et son état courant est vérifié.

Conceptuellement :

```texte
job scheduler
     |
     v
reload lease
     |
     +-- absent --------------------> no-op
     |
     +-- déjà révoqué/expiré ------> no-op
     |
     +-- nouvelle expiration
     |   dans le futur ------------> no-op / reschedule
     |
     +-- ACTIVE et arrivé à terme
             |
             v
          expire()
             |
             v
       backend.revoke()
```

Le scheduler agit donc comme un déclencheur. La décision finale appartient toujours au modèle métier et à l'état persistant du bail.

### Idempotence et concurrence

L'expiration et la révocation doivent supporter plusieurs déclenchements sans produire d'état incohérent. Par exemple, une révocation manuelle peut avoir lieu au même moment que l'expiration programmée. La transition doit donc être protégée au niveau de la persistence.

Conceptuellement :

```SQL
UPDATE leases
SET status = 'expired'
WHERE id = :lease_id
  AND status = 'active'
  AND expires_at <= :now;
```

Si la transition a effectivement eu lieu, le backend est révoqué. Dans le cas contraire, aucune nouvelle révocation n'est nécessaire. Les opérations du backend WireGuard doivent également être conçues comme idempotentes : demander la suppression d'un peer déjà absent ne doit pas compromettre le cycle de réconciliation.

### Supervision des processus

L'API et le scheduler appartiennent au même conteneur mais s'exécutent dans des processus distincts. Le processus PID 1 du conteneur assure leur supervision.

Un crash du scheduler doit provoquer uniquement son redémarrage :

```texte
scheduler
    |
  crash
    |
    v
superviseur
    |
    v
restart scheduler
    |
    v
reconstruction depuis la DB
```

Le redémarrage du conteneur complet n'est donc pas nécessaire pour récupérer d'une panne isolée du scheduler. Après son redémarrage, celui-ci reconstruit ses tâches depuis les données persistantes et traite immédiatement les éventuelles échéances dépassées.

### Surveillance des processus

Le fonctionnement de l'API seul ne suffit pas à considérer TTL-LAMa comme pleinement opérationnel.

Le déploiement doit également permettre de détecter une défaillance durable du scheduler, car une API fonctionnelle accompagnée d'un scheduler arrêté empêcherait l'expiration automatique des accès.

Un heartbeat ou une information équivalente peut être utilisé pour exposer l'état du scheduler au mécanisme de healthcheck du conteneur.

### Responsabilités

Les responsabilités peuvent finalement être résumées ainsi :

| Composant | Responsabilité |
| --- | --- |
| Persistence TTL-LAMa | Source de vérité des baux et de leurs échéances |
| API | Création, modification et révocation des baux |
| Scheduler | Déclenchement des expirations à leur échéance |
| Backend WireGuard | Matérialisation et suppression des accès réseau |
| ttlama sync | Déclenchement de la réconciliation via l'API |
| Réconciliateur | Convergence entre les baux valides et l'état du backend |
| Superviseur | Surveillance et relance des processus internes au conteneur |

### Invariant principal

L'ensemble de cette architecture vise à maintenir l'invariant suivant :

> Un accès réseau matérialisé dans un backend ne doit exister que s'il correspond à un bail TTL-LAMa actuellement valide.

Le scheduler assure le fonctionnement normal de cet invariant dans le temps.
La réconciliation constitue le mécanisme de récupération et de convergence en cas de redémarrage, de panne ou de divergence.

La persistence TTL-LAMa reste dans tous les cas la source de vérité, tandis que le backend réseau ne représente que la matérialisation de l'état désiré.
