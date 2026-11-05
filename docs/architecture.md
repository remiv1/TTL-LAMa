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
auth:
  mode: internal
  admin:
    username: admin
    password_file: /run/secrets/admin_password

database:
  type: sqlite
  path: /data/ttl-lama.db
```

External authentication is configured independently:

```yaml
auth:
  mode: external
  oidc:
    issuer: https://identity.example.org
    client_id: ttl-lama
    client_secret_file: /run/secrets/oidc_client_secret
    redirect_uri: https://ttl-lama.example.org/auth/callback

database:
  type: postgresql
  host: postgres
  name: ttl_lama
  user: ttl_lama
  password_file: /run/secrets/database_password
  schema: public
```

The identity provider answers **who the user is**. TTL-LAMa determines what that user can access, from which device, and for how long.

### Device

A user's identity and a VPN identity are distinct. A user may have several devices, each with its own identity at the access backend. This makes it possible to revoke one device without revoking the user or their other devices.

A lease applies to a specific device, not merely to a user.

### Access Profile

An access profile is a policy defined by the administrator. Users select from authorized profiles; they cannot supply arbitrary networks or access rules.

```yaml
backend:
  wireguard:
    interfaces:
      - name: wg0
        description: Server administration
        networks:
          - 192.168.10.0/24
        default_duration: 2h
        maximum_duration: 8h
        public_key: your_public_key_here
```

This document belongs in `/etc/ttl-lama/backend_config.yml`. The interface description becomes the profile name, and the interface name is stored as its `lease_target`.

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
| `internal` | PostgreSQL / MariaDB / MySQL | Standalone installation with an external database |
| `external` / OIDC | SQLite | Existing identity provider and lightweight deployment |
| `external` / OIDC | PostgreSQL / MariaDB / MySQL | Integrated infrastructure |

SQLite is the planned default for a standalone installation. Supported external SQL engines are PostgreSQL, MariaDB, and MySQL.

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

## Dynamic WireGuard Management and Lease Expiration

This section describes the structural decisions made for WireGuard integration and lease lifecycle management in TTL-LAMa.

TTL-LAMa remains responsible for **access leases**, their expiration, and their revocation. WireGuard is the first network backend, while its infrastructure configuration remains under the operator's control.

### Principles

WireGuard integration follows these principles:

- the operator owns the base configuration of the WireGuard interface;
- TTL-LAMa does not generate or replace the complete interface configuration;
- peers associated with leases are added and removed dynamically;
- the TTL-LAMa database is the source of truth for the access that should be active;
- WireGuard state is a materialized state derived from active leases;
- add, revoke, and reconcile operations must be idempotent.

This separation allows TTL-LAMa to manage the access lifecycle without becoming a general-purpose WireGuard administration interface.

### WireGuard Configuration

The operator configures the WireGuard interface independently of TTL-LAMa.

For example:

```ini
[Interface]
Address = 10.42.0.1/24
ListenPort = 51820
PrivateKey = ...
```

This configuration is persistent and defines the VPN infrastructure. TTL-LAMa does not persist dynamic peers in this configuration.

### Dynamic Peer Management

When a lease becomes active, the WireGuard backend materializes the corresponding access directly in the active interface. An equivalent operation can be performed with:

```bash
wg set wg0 \
peer <PUBLIC_KEY> \
allowed-ips <VPN_ADDRESS>/32
```

When a lease expires or is revoked, the corresponding peer is removed:

```bash
wg set wg0 \
peer <PUBLIC_KEY> \
remove
```

The WireGuard interface therefore does not need to be restarted for every lease change.
Conceptually:

```text
Lease ACTIVE
      |
      v
WireGuard backend
|
      v
peer present in wg0


Lease EXPIRED / REVOKED
      |
      v
WireGuard backend
|
      v
peer absent from wg0
```

### Source of Truth

WireGuard is not an access database. The desired state is determined from TTL-LAMa leases:

```SQL
desired_peers =
  leases
  WHERE status = ACTIVE
  AND expires_at > now()
```

The TTL-LAMa persistence layer therefore remains the source of truth.
This makes it possible, in particular, to fully rebuild the dynamic WireGuard state after a restart.

### Reconciliation of Dynamic Peers

A server restart may cause peers that were dynamically added to WireGuard to disappear. TTL-LAMa therefore has a reconciliation mechanism that rebuilds the expected state from persisted leases.

The command:

```bash
ttlama sync
```

triggers this reconciliation through the TTL-LAMa API.
Conceptually:

```text
TTL-LAMa database
      |
      | currently valid leases
      v
Desired state
      |
+---------------------+
|                     |
v                     v
Missing peers         Unwanted peers
|                     |
v                     v
ADD                   REMOVE
\                    /
 +--------+---------+
          |
          v
         wg0
```

Reconciliation is intentionally bidirectional.
It makes it possible to:

- recreate missing peers after a restart;
- remove a peer that no longer corresponds to a valid lease;
- correct a divergence between TTL-LAMa's persisted state and the backend's effective state.

Reconciliation is therefore a mechanism for converging toward the desired state, not merely a recovery mechanism after startup.

### Lease Expiration

Reconciliation does not replace normal expiration handling. TTL-LAMa must also remove network access when a lease expires, in keeping with its goal of automatic expiration and revocation.

Two complementary mechanisms are therefore used:

```text
                   TTL-LAMa
                       |
           +-----------+-----------+
           |                       |
           v                       v
      Scheduler              Reconciliation
           |                       |
   normal lease expiration    network state
           |                  convergence
           +-----------+-----------+
                       |
                       v
                WireGuard backend
```

### Scheduler

Because TTL-LAMa is a synchronous application, expiration is handled by a dedicated scheduling process. This process can use APScheduler or an equivalent mechanism. It is separate from the API workers, preventing a scheduler from being created in every HTTP worker.

The container architecture becomes:

```text
TTL-LAMa container
|
+-- supervisor (PID 1)
|
+-- API application
|   |
|   +-- worker 1
|   +-- worker 2
|   +-- ...
|   +-- worker N
|
+-- scheduler
```

There is always a single logical scheduler, regardless of the number of API workers.

### Rebuilding the Scheduler

Scheduler jobs are not a source of truth. Whenever the scheduler process starts or restarts, TTL-LAMa rebuilds its deadlines from the persistent database.

Startup follows this conceptual sequence:

```text
scheduler start
      |
      v
load active leases
      |
      +--> expires_at <= now()
      |        |
      |        v
      |   expire immediately
      |
      +--> expires_at > now()
               |
               v
          schedule
             job
```

Losing the scheduler's internal state therefore does not result in lost deadlines.

The authoritative information remains `Lease.expires_at`, not the job registered with the scheduler.

### Handling a Deadline

When a job runs, it must not blindly assume that the lease should be removed. The lease is reloaded from persistence and its current state is checked.

Conceptually:

```text
scheduler job
     |
     v
reload lease
     |
     +-- absent --------------------> no-op
     |
     +-- already revoked/expired --> no-op
     |
     +-- expiration moved
     |   into the future ----------> no-op / reschedule
     |
     +-- ACTIVE and expired
             |
             v
          expire()
             |
             v
       backend.revoke()
```

The scheduler therefore acts as a trigger. The final decision always belongs to the domain model and the persisted lease state.

### Idempotency and Concurrency

Expiration and revocation must support repeated triggers without producing an inconsistent state. For example, a manual revocation may happen at the same time as a scheduled expiration. The transition must therefore be protected at the persistence layer.

Conceptually:

```SQL
UPDATE leases
SET status = 'expired'
WHERE id = :lease_id
  AND status = 'active'
  AND expires_at <= :now;
```

If the transition occurred, the backend is revoked. Otherwise, no further revocation is needed. WireGuard backend operations must also be designed to be idempotent: requesting the removal of an already absent peer must not compromise the reconciliation process.

### Process Supervision

The API and scheduler belong to the same container but run in separate processes. The container's PID 1 process supervises them.

A scheduler crash should trigger only its own restart:

```text
scheduler
    |
  crash
    |
    v
supervisor
    |
    v
restart scheduler
    |
    v
rebuild from the DB
```

A full container restart is therefore not necessary to recover from an isolated scheduler failure. After restarting, the scheduler rebuilds its jobs from persisted data and immediately handles any overdue deadlines.

### Process Monitoring

A functioning API alone is not enough to consider TTL-LAMa fully operational.

The deployment must also make it possible to detect a lasting scheduler failure, because a working API with a stopped scheduler would prevent automatic access expiration.

A heartbeat or equivalent information can be used to expose the scheduler's status to the container health check.

### Responsibilities

The responsibilities can ultimately be summarized as follows:

| Component | Responsibility |
| --- | --- |
| TTL-LAMa persistence | Source of truth for leases and their deadlines |
| API | Creating, modifying, and revoking leases |
| Scheduler | Triggering expirations at their deadlines |
| WireGuard backend | Materializing and removing network access |
| `ttlama sync` | Triggering reconciliation through the API |
| Reconciler | Converging valid leases and backend state |
| Supervisor | Monitoring and restarting internal container processes |

### Main Invariant

This architecture aims to maintain the following invariant:

> Network access materialized in a backend must exist only when it corresponds to a currently valid TTL-LAMa lease.

The scheduler maintains this invariant during normal operation.
Reconciliation provides recovery and convergence in the event of a restart, failure, or divergence.

TTL-LAMa persistence remains the source of truth in all cases, while the network backend is only a materialization of the desired state.
