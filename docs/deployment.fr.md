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

Pour transmettre des surcharges facultatives, utilisez `podman run --env-file .env`. Le fichier `.env` reste sur l’hôte et n’est ni copié dans l’image ni envoyé dans le contexte de build ; `.dockerignore` et `.gitignore` l’excluent. Le modèle [.env.example](../.env.example) peut être copié puis complété. Les valeurs absentes continuent d’utiliser le YAML intégré. N’y stockez pas de secrets : montez-les séparément sous `/run/secrets/`.

Pour démarrer :

```sh
cp .env.example .env
mkdir -p secrets
podman build -f ./src/Dockerfile -t ttl-lama:latest .
podman volume create ttl-lama-data
podman run -d --name ttl-lama \
  -p 8080:8080 \
  --env-file .env \
  -v "/chemin/vers/config.yml:/etc/ttl-lama/config.yml:z,rw" \
  -v "$PWD/secrets:/run/secrets:z,ro" \
  -v ttl-lama-data:/data:z,rw \
  ttl-lama:latest
```

Le build de l’image compile le SCSS et copie htmx et les fontes dans l’image. Les assets web générés n’ont pas besoin d’être présents dans le dépôt.

Gunicorn précharge l’application dans son processus maître : la création des tables, l’import des profils et l’initialisation de l’administrateur sont terminés avant le lancement des workers. En mode externe, si aucune identité OIDC n’est encore liée, TTL-LAMa prépare au démarrage le compte indiqué par `auth.admin.username`, sans credential interne. Les sessions et connexions SQLAlchemy du maître sont ensuite fermées avant le fork ; chaque worker ouvre ses propres connexions. Ce mécanisme est indépendant du SGBD et fonctionne avec SQLite, PostgreSQL, MariaDB et MySQL. Une erreur d’initialisation empêche le démarrage des workers. Conservez le préchargement lors de la personnalisation de Gunicorn. Cette coordination concerne une seule instance Gunicorn, pas plusieurs conteneurs démarrant simultanément sur la même base.

Remplacez `/chemin/vers/config.yml` par le chemin absolu de votre configuration. Si vous souhaitez utiliser le fichier YAML intégré à l’image, omettez son montage. Le volume nommé `ttl-lama-data` conserve la base SQLite et la clé Flask générée entre les redémarrages. Pour arrêter puis supprimer le conteneur sans supprimer les données : `podman stop ttl-lama` puis `podman rm ttl-lama`.

La CLI administrateur peut mettre à jour le YAML choisi par `TTL_LAMA_CONFIG_FILE` avec `ttlama global-config apply --file <candidat.yml>`. Montez ce fichier dans un volume persistant si les changements doivent survivre au remplacement du conteneur ; sinon, la commande avertit qu’ils pourraient être perdus. Gunicorn charge les réglages au démarrage : après une mise à jour réussie, un redémarrage externe du conteneur est requis. Les variables d’environnement restent prioritaires sur le YAML. Cette commande ne modifie ni `backend_config.yml` ni les policies de profils en base.

En mode `external`, le premier login OIDC du compte préparé au démarrage associe son identité au compte local, via le callback navigateur ou le flux device `--distant`. Le claim `preferred_username` doit correspondre exactement à `auth.admin.username`, et `sub` doit être présent dans l’ID token validé. Les scopes `openid profile` sont demandés au fournisseur à cette fin. Aucun rapprochement par courriel n’est effectué. Une fois la première identité liée, tous les logins exigent la paire exacte issuer + subject.

Si le fournisseur ne renvoie pas `preferred_username` ou si une intervention explicite est nécessaire, un opérateur ayant accès au conteneur peut faire le lien manuellement :

```sh
podman exec --env TTL_LAMA_SECRET_KEY_FILE=/data/flask_secret_key ttl-lama python -m api.local_admin bootstrap-oidc-admin --user-id "08a8684b-db88-4b73-90a9-3cd1661f5466"
```

La commande lit le username de `auth.admin.username` et l’issuer de `auth.oidc.issuer`. L’exemple utilise le `userID` du Dex fourni; remplacez-le si votre configuration Dex définit une autre valeur. Le `userID` correspond au claim OIDC `sub` (par exemple `staticPasswords[].userID`); ce n’est ni le username ni l’adresse courriel. L’entrypoint exporte le chemin de la clé Flask générée uniquement pour Gunicorn; `podman exec` ne récupère pas cet environnement, d’où `TTL_LAMA_SECRET_KEY_FILE=/data/flask_secret_key`. Si `app.secret_key_file` est configuré, transmettez plutôt ce chemin. Une identité déjà liée à un autre compte provoque une erreur. Si le username existe, seul le lien OIDC est ajouté : son rôle, son état et ses credentials sont conservés. La commande est idempotente et ne modifie pas le YAML.

Le modèle intégré active l’authentification interne en développement : `DEBUG` est activé, les connexions HTTP sont autorisées et les cookies ne sont pas marqués `Secure`. Le mot de passe initial du compte `admin` est `admin`. Pour une première initialisation en production, remplacez-le dans la configuration avant le démarrage. Cette valeur sert uniquement à créer le compte : changer la configuration ensuite ne modifie pas le mot de passe déjà stocké.

Un secret Flask monté dans `secrets/flask_secret_key` est prioritaire. S’il est absent, l’entrée du conteneur génère une clé aléatoire dans `/data/flask_secret_key`, protégée par les permissions du propriétaire. Cette clé reste disponible grâce au volume `/data` après les redémarrages. Un fichier secret monté mais illisible fait échouer le démarrage. Le secret d’administration n’est pas requis pour le modèle de base ; les secrets ne doivent pas être écrits dans `.env`.

En production, configurez explicitement l’environnement, désactivez le mode debug et activez HTTPS ainsi que les cookies `Secure`. Le seul réglage `FLASK_ENV=production` ne suffit pas : le démarrage est refusé si `DEBUG` reste activé. Par exemple, les variables de surcharge sont `TTL_LAMA_FLASK_ENV=production`, `TTL_LAMA_DEBUG=false`, `TTL_LAMA_ENFORCE_SECURE_CONNECTION=true` et `TTL_LAMA_SESSION_COOKIE_SECURE=true`. En production, un warning est journalisé tant que le compte administrateur utilise encore le mot de passe initial. L’API authentifiée `GET /auth/security-status` expose uniquement l’indicateur booléen `default_admin_password_in_use`.

### Erreurs de configuration et secrets

Les paramètres sont chargés des valeurs par défaut, puis du YAML et des variables d’environnement (`TTL_LAMA_*`); les variables d’environnement priment sur le YAML. Un fichier `_FILE` est une source de valeur distincte : ne configurez pas simultanément la valeur directe et le fichier pour un même secret, car la validation refuse ce conflit. Les fichiers secrets montés doivent être lisibles par l’utilisateur non privilégié `ttl-lama`. Un fichier absent ou illisible fait échouer la validation et empêche le démarrage; les messages identifient le paramètre sans afficher le contenu ni le chemin du secret. Un YAML malformé ou non objet empêche son chargement; l’API de configuration renvoie alors une erreur générique sans le contenu du fichier. Les types et valeurs hors schéma sont rejetés par les modèles de paramètres. Les contraintes d’unicité des noms de profil et des clés publiques s’appliquent aux tables créées sur une nouvelle base; `create_all()` ne met pas à niveau les tables existantes. Une installation existante doit prévoir une migration séparée avant de pouvoir compter sur ces contraintes.

### Journaux

L’API et le scheduler écrivent dans le volume persistant `/data/logs`, avec un fichier par niveau : `error.log`, `warning.log`, `info.log` et `debug.log`. Les lignes sont horodatées en UTC et identifient le processus émetteur :

```text
[TTL-LAMa API]-[yyyy-mm-dd HH:mm:ss] : <operation>-<Log>
[TTL-LAMa Scheduler]-[yyyy-mm-dd HH:mm:ss] : <operation>-<Log>
```

Les archives tournent chaque jour à minuit UTC et conservent 30 rotations. Le répertoire est privé (`0700`) et les fichiers sont accessibles uniquement au compte applicatif (`0600`). Le volume `/data` doit donc être persistant et accessible en écriture à TTL-LAMa; un répertoire absent, non inscriptible ou aux permissions trop ouvertes empêche le démarrage des processus. Le chemin par défaut `/data/logs` peut être remplacé par `TTL_LAMA_LOG_DIRECTORY`. `app.log_level` définit le niveau minimal enregistré (`info` par défaut); définissez-le à `debug` pour remplir `debug.log`. Les journaux d’accès HTTP Gunicorn sont désactivés pour éviter d’archiver des chemins ou paramètres sensibles. Les secrets, jetons bruts, clés privées, clés publiques complètes, corps de requête et sorties stderr distantes ne sont pas consignés.

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
  oidc:
    issuer: your_issuer_url
    client_id: your_client_id
    client_secret_file: /run/secrets/oidc_client_secret
    redirect_uri: /auth/callback
  allowed_origins: []
  success_redirect: your_auth_success_redirect_url
  password_hasher:
    time_cost: 3
    memory_cost: 65536 # 64 MiB
    parallelism: 4
    hash_len: 32
    salt_len: 16

database:
  type: sqlite
  path: /data/ttl-lama.db
  schema: public

security:
  enforce_secure_connection: false
  session_cookie_name: session
  session_cookie_httponly: true
  session_cookie_secure: false
  session_cookie_samesite: Lax
  session_cookie_path: /
  session_lifetime: 3600

backend_config:
  file: /etc/ttl-lama/backend_config.yml
```

### Connexion OIDC de la CLI

Pour `ttlama auth login oidc`, enregistrez l’URI `/auth/callback` configurée sur
le serveur auprès du fournisseur d’identité. Le parcours CLI par défaut ouvre le
fournisseur dans un navigateur puis revient vers un callback temporaire lié à
`127.0.0.1` ; le fournisseur n’a pas à enregistrer une URI loopback différente
pour chaque utilisateur ou invocation. Le serveur émet un ticket à usage unique
valide deux minutes et ne crée la session TTL-LAMa qu’à son échange par la CLI.

Le mode `--distant` exige aussi que le document de découverte du fournisseur
publie `device_authorization_endpoint` et que le client autorise le grant
`urn:ietf:params:oauth:grant-type:device_code`. Le secret client OIDC reste sur
le serveur dans les deux parcours. Les tickets sont temporaires et stockés dans
la base configurée; l’initialisation habituelle de la base crée leur table.

### Paramètres Argon2id

`auth.password_hasher` configure le hasher Argon2id utilisé par l’authentification interne. Les valeurs suivantes sont des points de départ, pas des garanties de performance ni des plafonds imposés. Elles doivent être mesurées sur le matériel et sous la charge réelle de chaque déploiement.

| Profil indicatif | Matériel | `time_cost` | `memory_cost` (KiB) | `parallelism` |
| --- | --- | ---: | ---: | ---: |
| Ressources limitées | 1 vCPU, 1 GiB RAM | 2 | 19 456 | 1 |
| Standard | 2 vCPU, 4 GiB RAM | 3 | 65 536 | 4 |
| Renforcé | 4 vCPU, 16 GiB RAM | 3 | 131 072 | 4 |
| Haute capacité | 8 vCPU, 32 GiB RAM | 3 | 262 144 | 4 |

`hash_len: 32` et `salt_len: 16` peuvent rester constants. `memory_cost` est exprimé en KiB et s’applique à chaque vérification simultanée : quatre calculs au profil standard demandent environ 256 MiB pour Argon2id, en plus de la mémoire de l’application et du système. Mesurez la latence et la mémoire sous charge avant de retenir un profil. Les variables `TTL_LAMA_TIME_COST`, `TTL_LAMA_MEMORY_COST`, `TTL_LAMA_PARALLELISM`, `TTL_LAMA_HASH_LEN` et `TTL_LAMA_SALT_LEN` remplacent les valeurs YAML correspondantes.

Les paramètres sont lus au démarrage. Leur modification ne change pas les mots de passe déjà stockés; la vérification utilise les paramètres encodés dans chaque hash. La création de nouveaux hashes doit utiliser la même politique configurée.

Les moteurs pris en charge sont `sqlite`, `postgresql`, `mariadb` et `mysql`. SQLite est le choix autonome par défaut. Une base externe nécessite `database.host`, `database.name`, `database.user` et `database.password_file`; `database.port` est facultatif et utilise le port standard du moteur; `database.schema` est également requis pour certains moteurs comme postgresql. Les variables d’environnement préfixées par `TTL_LAMA_` restent disponibles pour les surcharges ; par exemple, `TTL_LAMA_AUTH_MODE` remplace `auth.mode`.

Les interfaces backend sont validées séparément dans `/etc/ttl-lama/backend_config.yml` et servent à initialiser les policies de profil au premier démarrage :

```yaml
backend:
  wireguard:
    interfaces:
      - name: wg0
        description: Accès utilisateur
        networks:
          - 10.0.0.0/8
        public_key: your_public_key_here
        default_duration: 8h
        maximum_duration: 24h
```

La description de l’interface devient le nom du profil et son champ `name` devient `lease_target`. Les durées acceptent les unités `d`, `h`, `m` et `s`. La durée par défaut ne peut pas dépasser la durée maximale et chaque interface doit définir au moins un réseau.

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

Le contenu des secrets montés est lu au démarrage. En production, la clé Flask doit contenir au moins 32 caractères et les cookies doivent être marqués `Secure`. L’authentification est toujours obligatoire. Adaptez les interfaces de `backend_config.yml` aux réseaux et durées de votre déploiement.

## Chemins dans le conteneur

- `/opt/ttl-lama/` : code Python et serveur WSGI ;
- `/etc/ttl-lama/config.yml` : configuration YAML de base intégrée à l’image, remplaçable par un montage en lecture seule ;
- `/etc/ttl-lama/backend_config.yml` : interfaces backend de base intégrées à l’image, remplaçables par un montage en lecture seule ;
- `/etc/ttl-lama/ssh_config.yml` : paramètres SSH lus à l’ouverture d’une connexion par le scheduler ;
- `/data/` : base SQLite, données persistantes et clé Flask générée en l’absence de secret monté ;
- `/run/secrets/` : secrets montés, hors de l’image.

Le processus applicatif s’exécute sans privilèges root. Aucun privilège WireGuard n’est ajouté tant que le backend correspondant n’est pas implémenté.

## Tests d’intégration des bases

Le Compose dédié lance les tests d’authentification et de persistance contre SQLite, PostgreSQL, MariaDB et MySQL :

```sh
podman compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
podman compose -f compose.test.yml down
```

Les services de base de données de ce Compose sont réservés aux tests et n’utilisent aucun volume persistant.
