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

Example:

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

Supported database engines are `sqlite`, `postgresql`, `mariadb`, and `mysql`. SQLite is the standalone default. An external database requires `database.host`, `database.name`, `database.user`, and `database.password_file`; `database.port` is optional and defaults to the engine's standard port. `TTL_LAMA_...` environment variables remain available as overrides; for example, `TTL_LAMA_AUTH_MODE` overrides `auth.mode`.

Access profiles are validated separately in `/etc/ttl-lama/access-profiles.yml`:

```yaml
profiles:
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

Secrets must be kept separate from ordinary configuration and are never included in the image. The default YAML files contain only paths to mounted secrets:

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

Secrets are read at startup. In production, the Flask key must contain at least 32 characters and cookies must be marked `Secure`. Authentication is always required.

## Container Paths

- `/opt/ttl-lama/`: Python source and WSGI server;
- `/etc/ttl-lama/config.yml`: base YAML configuration embedded in the image and replaceable with a read-only mount;
- `/etc/ttl-lama/access-profiles.yml`: base access profiles embedded in the image and replaceable with a read-only mount;
- `/data/`: SQLite database and persistent data;
- `/run/secrets/`: mounted secrets, kept out of the image.

The application process runs without root privileges. No WireGuard privilege is added until that backend is implemented.

## Database Integration Tests

The dedicated Compose stack runs authentication and persistence tests against SQLite, PostgreSQL, MariaDB, and MySQL:

```sh
docker compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yml down
```

The database services in this Compose file are test-only and have no persistent volumes.
