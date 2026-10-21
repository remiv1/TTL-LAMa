# Fonctionnement

Ce document décrit le cycle de vie prévu d’un bail d’accès et la manière dont TTL-LAMa maintient la cohérence entre l’état désiré persisté et le backend d’accès. Le projet étant encore au stade de la conception et du prototype, il ne s’agit pas encore d’un guide d’exploitation opérationnel.

## Cycle de vie d’un bail

Un bail suit un cycle explicite :

```text
REQUESTED -> autorisation -> ACTIVE -> EXPIRED
                                  `----> REVOKED
```

Des états supplémentaires, tels que `PENDING_APPROVAL`, `DENIED`, `SUSPENDED` ou `ERROR`, pourront être introduits si des cas d’usage concrets le nécessitent. Le nombre d’états doit rester aussi réduit que possible.

Un bail actif est associé à une identité, un appareil, un profil d’accès et une durée. Son expiration fait partie de l’état désiré :

```text
expires_at <= now
    => lease = EXPIRED
    => provisioned_access = ABSENT
```

### Provisionnement

Lorsqu’un bail devient actif, TTL-LAMa demande au backend configuré de matérialiser l’accès. Pour WireGuard, les informations nécessaires comprennent la clé publique de l’appareil, son adresse VPN, le profil d’accès et la date d’expiration.

À l’expiration ou à la révocation du bail, le backend doit supprimer l’accès correspondant. Il ne suffit pas de marquer le bail `EXPIRED` ou `REVOKED` si l’accès réseau reste provisionné.

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

TTL-LAMa ne doit pas dépendre exclusivement d’une tâche planifiée exécutée à l’instant précis de l’expiration. Si l’application s’arrête avant l’expiration d’un bail et redémarre ensuite, l’accès expiré doit tout de même être supprimé.

Le système compare périodiquement :

```text
État désiré (base de données) <-> TTL-LAMa <-> État réel (backend d’accès)
```

Les invariants sont :

```text
si expires_at <= now :       l’accès ne doit pas exister
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
