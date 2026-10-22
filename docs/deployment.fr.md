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

Le Compose d’exécution lit le fichier `.env` présent sur l’hôte et injecte ses variables dans le processus du conteneur (`env_file`). Ce fichier n’est ni copié dans l’image ni envoyé dans le contexte de build ; `.dockerignore` et `.gitignore` l’excluent. Le modèle [.env.example](../.env.example) peut être copié puis complété pour les surcharges nécessaires. Les valeurs absentes continuent d’utiliser le YAML intégré.

Pour démarrer :

```sh
cp .env.example .env
mkdir -p secrets
docker compose up --build -d
```

Le modèle intégré active l’authentification interne en développement : `DEBUG` est activé, les connexions HTTP sont autorisées et les cookies ne sont pas marqués `Secure`. Le mot de passe initial du compte `admin` est `admin`. Pour une première initialisation en production, remplacez-le dans la configuration avant le démarrage. Cette valeur sert uniquement à créer le compte : changer la configuration ensuite ne modifie pas le mot de passe déjà stocké.

Un secret Flask monté dans `secrets/flask_secret_key` est prioritaire. S’il est absent, l’entrée du conteneur génère une clé aléatoire dans `/data/flask_secret_key`, protégée par les permissions du propriétaire. Cette clé reste disponible grâce au volume `/data` après les redémarrages. Un fichier secret monté mais illisible fait échouer le démarrage. Le secret d’administration n’est pas requis pour le modèle de base ; les secrets ne doivent pas être écrits dans `.env`.

En production, configurez explicitement l’environnement, désactivez le mode debug et activez HTTPS ainsi que les cookies `Secure`. Le seul réglage `FLASK_ENV=production` ne suffit pas : le démarrage est refusé si `DEBUG` reste activé. Par exemple, les variables de surcharge sont `TTL_LAMA_FLASK_ENV=production`, `TTL_LAMA_DEBUG=false`, `TTL_LAMA_ENFORCE_SECURE_CONNECTION=true` et `TTL_LAMA_SESSION_COOKIE_SECURE=true`. En production, un warning est journalisé tant que le compte administrateur utilise encore le mot de passe initial. L’API authentifiée `GET /auth/security-status` expose uniquement l’indicateur booléen `default_admin_password_in_use`.

Exemple :

```yaml
app:
  environment: development
  debug: true
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
    password: admin

database:
  type: sqlite
  path: /data/ttl-lama.db
  schema: public

security:
  enforce_secure_connection: false
  session_cookie_name: session
  session_cookie_secure: false

access_profiles:
  file: /etc/ttl-lama/access-profiles.yml
```

Les moteurs pris en charge sont `sqlite`, `postgresql`, `mariadb` et `mysql`. SQLite est le choix autonome par défaut. Une base externe nécessite `database.host`, `database.name`, `database.user` et `database.password_file`; `database.port` est facultatif et utilise le port standard du moteur. Les variables d’environnement préfixées par `TTL_LAMA_` restent disponibles pour les surcharges ; par exemple, `TTL_LAMA_AUTH_MODE` remplace `auth.mode`.

Les profils d’accès sont validés séparément dans `/etc/ttl-lama/access-profiles.yml` :

```yaml
profiles:
  admin:
    default_duration: 1h
    maximum_duration: 8h
    networks:
      - 10.0.0.0/8
  user:
    default_duration: 8h
    maximum_duration: 24h
    networks:
      - 192.168.0.0/16
  maintenance:
    default_duration: 30m
    maximum_duration: 2h
    networks:
      - 172.16.0.0/12
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

Les secrets doivent être séparés de la configuration ordinaire et ne sont jamais inclus dans l’image. La clé Flask peut être montée ou générée et persistée dans `/data`. Les autres secrets externes peuvent être référencés par leur chemin monté :

```yaml
app:
  secret_key_file: /run/secrets/flask_secret_key

auth:
  oidc:
    client_secret_file: /run/secrets/oidc_client_secret

database:
  password_file: /run/secrets/database_password
```

Le contenu des secrets montés est lu au démarrage. En production, la clé Flask doit contenir au moins 32 caractères et les cookies doivent être marqués `Secure`. L’authentification est toujours obligatoire. Les trois profils fournis dans `access-profiles.yml` sont des exemples à adapter aux réseaux et durées de votre déploiement.

## Chemins dans le conteneur

- `/opt/ttl-lama/` : code Python et serveur WSGI ;
- `/etc/ttl-lama/config.yml` : configuration YAML de base intégrée à l’image, remplaçable par un montage en lecture seule ;
- `/etc/ttl-lama/access-profiles.yml` : profils d’accès de base intégrés à l’image, remplaçables par un montage en lecture seule ;
- `/data/` : base SQLite, données persistantes et clé Flask générée en l’absence de secret monté ;
- `/run/secrets/` : secrets montés, hors de l’image.

Le processus applicatif s’exécute sans privilèges root. Aucun privilège WireGuard n’est ajouté tant que le backend correspondant n’est pas implémenté.

Le fichier [compose.yml](../compose.yml) utilise un volume nommé pour `/data`, monte `secrets/` en lecture seule et transmet le `.env` de l’hôte au conteneur.

## Tests d’intégration des bases

Le Compose dédié lance les tests d’authentification et de persistance contre SQLite, PostgreSQL, MariaDB et MySQL :

```sh
docker compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yml down
```

Les services de base de données de ce Compose sont réservés aux tests et n’utilisent aucun volume persistant.
