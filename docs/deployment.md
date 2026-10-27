# Deployment and Configuration

Portability is a key goal of TTL-LAMa. The minimal deployment is intended to fit in a single container; deployments that already have identity or database infrastructure can use those external components.

## Deployment Models

A standalone deployment may contain the application, internal authentication, SQLite persistence, lease management, the WireGuard backend, and reconciliation in one container.

An integrated deployment may instead use an existing OIDC identity provider and PostgreSQL, MariaDB, or MySQL database. The core lease-management function remains the same.

## Configuration

TTL-LAMa uses declarative configuration. Infrastructure configuration is deliberately not exposed through a web administration interface. Configuration sources may include:

1. application defaults;
2. the `/etc/ttl-lama/config.yml` YAML file;
3. `TTL_LAMA_...` environment variables, which override YAML values;
4. secrets mounted in the container and referenced with a `_FILE` setting.

The runtime Compose configuration reads the host-side `.env` file and injects its variables into the container process using `env_file`. The file is neither copied into the image nor sent in the build context; `.dockerignore` and `.gitignore` exclude it. Copy [.env.example](../.env.example) to `.env` and add only the overrides you need. Unset values continue to come from the embedded YAML configuration.

Start the service with:

```sh
cp .env.example .env
mkdir -p secrets
docker compose up --build -d
```

The embedded configuration enables internal authentication in development: `DEBUG` is enabled, HTTP connections are allowed, and cookies are not marked `Secure`. The initial `admin` account password is `admin`. For the first production initialization, replace it in the configuration before startup. This value is used only to create the account; changing the configuration later does not change the password already stored.

A Flask secret mounted at `secrets/flask_secret_key` takes precedence. If it is absent, the container entrypoint generates a random key at `/data/flask_secret_key`, with owner-only permissions. The key persists across restarts through the `/data` volume. If a mounted secret exists but cannot be read, startup fails. An admin password secret is not required by the base configuration; do not put secret values in `.env`.

For production, explicitly set the environment, disable debug mode, and enable HTTPS enforcement and `Secure` cookies. Setting only `FLASK_ENV=production` is not enough: startup is rejected while `DEBUG` remains enabled. For example, the override variables are `TTL_LAMA_FLASK_ENV=production`, `TTL_LAMA_DEBUG=false`, `TTL_LAMA_ENFORCE_SECURE_CONNECTION=true`, and `TTL_LAMA_SESSION_COOKIE_SECURE=true`. In production, a warning is logged while the administrator still uses the initial password. Authenticated API endpoint `GET /auth/security-status` exposes only the boolean indicator `default_admin_password_in_use`.

Example:

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

access_profiles:
  file: /etc/ttl-lama/access-profiles.yml
```

### Argon2id Parameters

`auth.password_hasher` configures the Argon2id hasher used by internal authentication. The following values are starting points, not performance guarantees or enforced limits. Benchmark them on the deployment hardware under its expected load.

| Indicative profile | Hardware | `time_cost` | `memory_cost` (KiB) | `parallelism` |
| --- | --- | ---: | ---: | ---: |
| Resource-constrained | 1 vCPU, 1 GiB RAM | 2 | 19,456 | 1 |
| Standard | 2 vCPU, 4 GiB RAM | 3 | 65,536 | 4 |
| Hardened | 4 vCPU, 16 GiB RAM | 3 | 131,072 | 4 |
| High capacity | 8 vCPU, 32 GiB RAM | 3 | 262,144 | 4 |

`hash_len: 32` and `salt_len: 16` can remain constant. `memory_cost` is in KiB and applies to each simultaneous verification: four calculations at the standard profile require about 256 MiB for Argon2id, in addition to the application's and system's memory. Measure latency and memory under load before choosing a profile. The `TTL_LAMA_TIME_COST`, `TTL_LAMA_MEMORY_COST`, `TTL_LAMA_PARALLELISM`, `TTL_LAMA_HASH_LEN`, and `TTL_LAMA_SALT_LEN` environment variables override the corresponding YAML values.

Settings are read at startup. Changing them does not alter passwords already stored; verification uses the parameters encoded in each hash. New password hashes must use the same configured policy.

Supported database engines are `sqlite`, `postgresql`, `mariadb`, and `mysql`. SQLite is the standalone default. An external database requires `database.host`, `database.name`, `database.user`, and `database.password_file`; `database.port` is optional and defaults to the engine's standard port ; `database.schema` is also required for some engines like postgresql. `TTL_LAMA_...` environment variables remain available as overrides; for example, `TTL_LAMA_AUTH_MODE` overrides `auth.mode`.

Access profiles are validated separately in `/etc/ttl-lama/access-profiles.yml`:

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
      - 192.168.10.10/32
```

Durations accept `d`, `h`, `m`, and `s` units. The default duration cannot exceed the maximum, and every profile must specify at least one network.

## Persistence Options

SQLite is the planned default for a standalone installation:

```yaml
database:
  type: sqlite
  path: /data/ttl-lama.db
```

An external database may be configured independently of authentication:

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

Secrets must be kept separate from ordinary configuration and are never included in the image. The Flask key may be mounted or generated and persisted under `/data`. Other external secrets may be referenced by their mounted paths:

```yaml
app:
  secret_key_file: /run/secrets/flask_secret_key

auth:
  oidc:
    client_secret_file: /run/secrets/oidc_client_secret

database:
  password_file: /run/secrets/database_password
```

Mounted secret contents are read at startup. In production, the Flask key must contain at least 32 characters and cookies must be marked `Secure`. Authentication is always required. The three profiles in `access-profiles.yml` are examples to adapt to your deployment's networks and durations.

## Container Paths

- `/opt/ttl-lama/`: Python source and WSGI server;
- `/etc/ttl-lama/config.yml`: base YAML configuration embedded in the image and replaceable with a read-only mount;
- `/etc/ttl-lama/access-profiles.yml`: base access profiles embedded in the image and replaceable with a read-only mount;
- `/data/`: SQLite database, persistent data, and generated Flask key when no secret is mounted;
- `/run/secrets/`: mounted secrets, kept out of the image.

The application process runs without root privileges. No WireGuard privilege is added until that backend is implemented.

The [compose.yml](../compose.yml) file uses a named volume for `/data`, mounts `secrets/` read-only, and passes the host `.env` values into the container.

## Database Integration Tests

The dedicated Compose stack runs authentication and persistence tests against SQLite, PostgreSQL, MariaDB, and MySQL:

```sh
docker compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yml down
```

The database services in this Compose file are test-only and have no persistent volumes.
