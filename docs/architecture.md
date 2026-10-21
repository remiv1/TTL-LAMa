# Architecture

TTL-LAMa is designed as a modular monolith that can be deployed in a single container. Its domain model remains independent of the authentication provider, persistence backend, and network access backend.

## Core Concepts

The domain model is built around four concepts:

```text
Identity -> Device -> Access Profile -> Lease -> Access Backend
```

### Identity and Authentication

An identity represents a user to whom TTL-LAMa can grant permissions. Two authentication modes are planned:

- **`internal`**: TTL-LAMa manages user accounts and the mechanisms required to authenticate them, including multi-factor authentication.
- **`external`**: authentication is delegated to an identity provider, initially through OIDC.

Both modes produce an identity for the domain core. Lease, device, and profile logic does not depend on how that identity was authenticated.

Internal authentication can use any supported persistence backend. For example:

```yaml
authentication:
  mode: internal

database:
  driver: sqlite
  path: /data/ttl-lama.db
```

External authentication is configured independently:

```yaml
authentication:
  mode: external

  oidc:
    issuer: https://identity.example.org
    client_id: ttl-lama
    client_secret_file: /run/secrets/oidc_client_secret
```

The identity provider answers **who the user is**. TTL-LAMa determines what that user can access, from which device, and for how long.

### Device

A user's identity and a VPN identity are distinct. A user may have several devices, each with its own identity at the access backend. This makes it possible to revoke one device without revoking the user or their other devices.

A lease applies to a specific device, not merely to a user.

### Access Profile

An access profile is a policy defined by the administrator. Users select from authorized profiles; they cannot supply arbitrary networks or access rules.

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

### Access Lease

A lease is temporary authorization granted to an identity and a device according to an access profile. It records its creation and expiration times and the information required to apply the access.

```text
Identity + Device + Access Profile + Duration -> Lease
```

Expiration is part of the desired state: when `expires_at <= now`, the lease is expired and provisioned access must be absent, including after a TTL-LAMa restart.

## Components

```text
User
  |
  v
TTL-LAMa
  |-- Authentication -> Identity
  |-- Authorization -> Device -> Access Profile -> Lease
  |-- Provisioning
  |-- Reconciliation
  `-- Audit
       |                 |
       v                 v
  Persistence       Access backend
  SQLite / SQL      WireGuard / future
```

### Authentication

The authentication module produces an identity for the domain core. The core does not directly depend on the mechanism used to authenticate that identity.

### Persistence

TTL-LAMa stores its own domain state regardless of the authentication mode. This includes referenced identities, devices, public keys, profiles and their associations, leases, audit events, and provisioning state.

Authentication and persistence are independent choices:

| Authentication | Persistence | Typical use |
| --- | --- | --- |
| `internal` | SQLite | Standalone installation |
| `internal` | PostgreSQL | Standalone installation with an external database |
| `external` / OIDC | SQLite | Existing identity provider and lightweight deployment |
| `external` / OIDC | PostgreSQL | Integrated infrastructure |

SQLite is the planned default for a standalone installation.

### Access Backend

The access backend materializes a lease. The first implementation targets WireGuard peers, while the domain core remains independent of backend-specific concepts so that other backends can be considered later.

## Code Organization

A possible logical layout is:

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

This is a logical separation within one deployable application, not a microservices architecture.
