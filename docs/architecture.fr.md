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
authentication:
  mode: internal

database:
  driver: sqlite
  path: /data/ttl-lama.db
```

L’authentification externe se configure indépendamment :

```yaml
authentication:
  mode: external

  oidc:
    issuer: https://identity.example.org
    client_id: ttl-lama
    client_secret_file: /run/secrets/oidc_client_secret
```

Le fournisseur d’identité répond à la question **qui est l’utilisateur**. TTL-LAMa détermine à quoi il peut accéder, depuis quel appareil et pendant combien de temps.

### Appareil

L’identité d’un utilisateur et son identité VPN sont distinctes. Un utilisateur peut avoir plusieurs appareils, chacun possédant sa propre identité auprès du backend d’accès. Il est ainsi possible de révoquer un appareil sans révoquer l’utilisateur ni ses autres appareils.

Un bail s’applique à un appareil déterminé et non simplement à un utilisateur.

### Profil d’accès

Un profil d’accès est une politique définie par l’administrateur. Les utilisateurs choisissent parmi les profils qui leur sont autorisés ; ils ne peuvent pas fournir arbitrairement des réseaux ou des règles d’accès.

```yaml
access_profiles:
  server-admin:
    duration:
      default: 2h
      maximum: 8h
    networks:
      - 192.168.10.0/24

  maintenance:
    duration:
      default: 30m
      maximum: 2h
    networks:
      - 192.168.10.10/32
```

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
| `internal` | PostgreSQL | Installation autonome avec base externe |
| `external` / OIDC | SQLite | Fournisseur d’identité existant et déploiement léger |
| `external` / OIDC | PostgreSQL | Infrastructure intégrée |

SQLite est le backend prévu par défaut pour une installation autonome.

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
