# Déploiement et configuration

La portabilité est un objectif essentiel de TTL-LAMa. Le déploiement minimal est conçu pour tenir dans un conteneur unique ; les installations disposant déjà d’une infrastructure d’identité ou de base de données peuvent utiliser ces composants externes.

## Modèles de déploiement

Une installation autonome peut regrouper dans un même conteneur l’application, l’authentification interne, la persistance SQLite, la gestion des baux, le backend WireGuard et la réconciliation.

Une installation intégrée peut utiliser un fournisseur d’identité OIDC et une base PostgreSQL existants. La fonction de gestion des baux reste identique.

## Configuration

TTL-LAMa utilise une configuration déclarative. La configuration de l’infrastructure n’est volontairement pas exposée par une interface web d’administration. Les sources de configuration peuvent comprendre :

1. les valeurs par défaut de l’application ;
2. un fichier de configuration ;
3. des variables d’environnement ;
4. des secrets montés dans le conteneur.

Exemple :

```yaml
server:
  listen: "0.0.0.0:8080"

authentication:
  mode: internal

database:
  driver: sqlite
  path: /data/ttl-lama.db

access_backend:
  driver: wireguard

wireguard:
  interface: wg0
  subnet: 10.50.0.0/24

leases:
  default_duration: 2h
  maximum_duration: 24h
```

L’opérateur peut monter un fichier de configuration à un emplacement tel que `/etc/ttl-lama/config.yml`.

La configuration définit ce que TTL-LAMa est autorisé à proposer. Les utilisateurs ne peuvent choisir qu’au sein de ces limites.

## Options de persistance

SQLite est le backend prévu par défaut pour une installation autonome :

```yaml
database:
  driver: sqlite
  path: /data/ttl-lama.db
```

Une base externe peut être configurée indépendamment du mode d’authentification :

```yaml
database:
  driver: postgresql
  host: postgres
  database: ttl_lama
  username: ttl_lama
  password_file: /run/secrets/database_password
```

## Secrets

Les secrets doivent être séparés de la configuration ordinaire. Les paramètres non sensibles peuvent être fournis par variables d’environnement :

```text
TTL_LAMA_DATABASE_HOST=postgres
TTL_LAMA_DATABASE_NAME=ttl_lama
```

Les secrets peuvent être fournis par des fichiers montés :

```text
TTL_LAMA_DATABASE_PASSWORD_FILE=/run/secrets/database_password
TTL_LAMA_OIDC_CLIENT_SECRET_FILE=/run/secrets/oidc_client_secret
```

Les secrets potentiels comprennent les identifiants de base de données, les clés de chiffrement applicatives, les secrets de l’authentification interne, les secrets OIDC et ceux nécessaires à certains backends d’accès.

Les secrets ne doivent pas être intégrés à l’image du conteneur ni aux fichiers de configuration fournis par défaut.
