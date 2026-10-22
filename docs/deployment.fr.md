# Déploiement et configuration

La portabilité est un objectif essentiel de TTL-LAMa. Le déploiement minimal est conçu pour tenir dans un conteneur unique ; les installations disposant déjà d’une infrastructure d’identité ou de base de données peuvent utiliser ces composants externes.

## Modèles de déploiement

Une installation autonome peut regrouper dans un même conteneur l’application, l’authentification interne, la persistance SQLite, la gestion des baux, le backend WireGuard et la réconciliation.

Une installation intégrée peut utiliser un fournisseur d’identité OIDC et une base PostgreSQL, MariaDB ou MySQL existante. La fonction de gestion des baux reste identique.

## Configuration

TTL-LAMa utilise une configuration déclarative. La configuration de l’infrastructure n’est volontairement pas exposée par une interface web d’administration. Les sources de configuration peuvent comprendre :

1. les valeurs par défaut de l’application ;
2. le fichier YAML `/etc/ttl-lama/config.yml` ;
3. des variables d’environnement `TTL_LAMA_...`, prioritaires sur le YAML ;
4. des secrets montés dans le conteneur et référencés par un paramètre `_FILE`.

Exemple :

```yaml
app:
  environment: production
  debug: false
  secret_key_file: /run/secrets/flask_secret_key
  log_level: info

server:
  host: 0.0.0.0
  port: 8080

auth:
  mode: internal
  cookie_name: ttl-lama_session
  admin:
    username: admin
    password_file: /run/secrets/admin_password

database:
  type: sqlite
  path: /data/ttl-lama.db
  schema: public

security:
  enforce_secure_connection: true
  session_cookie_name: session

access_profiles:
  file: /etc/ttl-lama/access-profiles.yml
```

Les moteurs pris en charge sont `sqlite`, `postgresql`, `mariadb` et `mysql`. SQLite est le choix autonome par défaut. Une base externe nécessite `database.host`, `database.name`, `database.user` et `database.password_file`; `database.port` est facultatif et utilise le port standard du moteur. Les variables d’environnement préfixées par `TTL_LAMA_` restent disponibles pour les surcharges ; par exemple, `TTL_LAMA_AUTH_MODE` remplace `auth.mode`.

Les profils d’accès sont validés séparément dans `/etc/ttl-lama/access-profiles.yml` :

```yaml
profiles:
  maintenance:
    default_duration: 30m
    maximum_duration: 2h
    networks:
      - 192.168.10.10/32
```

Les durées acceptent les unités `d`, `h`, `m` et `s`. La durée par défaut ne peut pas dépasser la durée maximale et chaque profil doit définir au moins un réseau.

## Options de persistance

SQLite est le backend prévu par défaut pour une installation autonome :

```yaml
database:
  type: sqlite
  path: /data/ttl-lama.db
```

Une base externe peut être configurée indépendamment du mode d’authentification :

```yaml
database:
  type: postgresql
  host: postgres
  port: 5432
  name: ttl_lama
  user: ttl_lama
  password_file: /run/secrets/database_password
  schema: public
```

## Secrets

Les secrets doivent être séparés de la configuration ordinaire et ne sont jamais inclus dans l’image. Les YAML de configuration de base ne contiennent que les chemins des secrets montés :

```yaml
app:
  secret_key_file: /run/secrets/flask_secret_key

auth:
  admin:
    password_file: /run/secrets/admin_password
  oidc:
    client_secret_file: /run/secrets/oidc_client_secret

database:
  password_file: /run/secrets/database_password
```

Le contenu est lu au démarrage. En production, la clé Flask doit contenir au moins 32 caractères et les cookies doivent être marqués `Secure`. L’authentification est toujours obligatoire.

## Chemins dans le conteneur

- `/opt/ttl-lama/` : code Python et serveur WSGI ;
- `/etc/ttl-lama/config.yml` : configuration YAML de base intégrée à l’image, remplaçable par un montage en lecture seule ;
- `/etc/ttl-lama/access-profiles.yml` : profils d’accès de base intégrés à l’image, remplaçables par un montage en lecture seule ;
- `/data/` : base SQLite et données persistantes ;
- `/run/secrets/` : secrets montés, hors de l’image.

Le processus applicatif s’exécute sans privilèges root. Aucun privilège WireGuard n’est ajouté tant que le backend correspondant n’est pas implémenté.

## Tests d’intégration des bases

Le Compose dédié lance les tests d’authentification et de persistance contre SQLite, PostgreSQL, MariaDB et MySQL :

```sh
docker compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yml down
```

Les services de base de données de ce Compose sont réservés aux tests et n’utilisent aucun volume persistant.
