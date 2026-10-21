# Deployment and Configuration

Portability is a key goal of TTL-LAMa. The minimal deployment is intended to fit in a single container; deployments that already have identity or database infrastructure can use those external components.

## Deployment Models

A standalone deployment may contain the application, internal authentication, SQLite persistence, lease management, the WireGuard backend, and reconciliation in one container.

An integrated deployment may instead use an existing OIDC identity provider and PostgreSQL database. The core lease-management function remains the same.

## Configuration

TTL-LAMa uses declarative configuration. Infrastructure configuration is deliberately not exposed through a web administration interface. Configuration sources may include:

1. application defaults;
2. a configuration file;
3. environment variables;
4. secrets mounted in the container.

Example:

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

An operator could mount a configuration file at a path such as `/etc/ttl-lama/config.yml`.

Configuration defines what TTL-LAMa is allowed to offer. Users can only choose within those limits.

## Persistence Options

SQLite is the planned default for a standalone installation:

```yaml
database:
  driver: sqlite
  path: /data/ttl-lama.db
```

An external database may be configured independently of authentication:

```yaml
database:
  driver: postgresql
  host: postgres
  database: ttl_lama
  username: ttl_lama
  password_file: /run/secrets/database_password
```

## Secrets

Secrets must be kept separate from ordinary configuration. Non-sensitive settings can be supplied as environment variables:

```text
TTL_LAMA_DATABASE_HOST=postgres
TTL_LAMA_DATABASE_NAME=ttl_lama
```

Secrets can be provided as mounted files:

```text
TTL_LAMA_DATABASE_PASSWORD_FILE=/run/secrets/database_password
TTL_LAMA_OIDC_CLIENT_SECRET_FILE=/run/secrets/oidc_client_secret
```

Potential secrets include database credentials, application encryption keys, internal authentication secrets, OIDC secrets, and credentials required by some access backends.

Secrets must not be built into the container image or included in default configuration files.
