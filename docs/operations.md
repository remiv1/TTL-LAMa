# Operations

This document describes the implemented lease lifecycle and the known operational limits of synchronization with the access backend.

## WireGuard Provisioning Status

Before starting APScheduler, the scheduler process reconciles WireGuard state against persisted leases. It reapplies missing or divergent active peers, removes peers without an active lease, and restores expiration jobs. WireGuard operations are sent over SSH with `sudo -n ttlama backend wg leases`. Reconciliation runs at startup, not periodically; pending operations and failed removals continue to be handled by the scheduler poll.

Profile networks become the peer's `AllowedIPs`. On the same interface, reservations cannot share a public key or overlapping networks. A reservation remains occupied until deletion is confirmed. After an application with an uncertain result, it remains reserved even if a subsequent deletion succeeds: a delayed remote command may still change the peer.

The file `/etc/ttl-lama/ssh_config.yml` configures the connection, private key and `known_hosts` file. Timeouts in seconds are configurable with `TTL_LAMA_SSH_COMMAND_TIMEOUT` (default 30), `TTL_LAMA_PROVISIONING_WAIT_SECONDS` (45) and `TTL_LAMA_SCHEDULER_POLL_INTERVAL` (1). The API wait should normally exceed the SSH timeout and polling interval.

After `panic.retry` consecutive startup reconciliation failures (3 by default), panic mode runs the configured administrator script and independently attempts email notification when enabled. The scheduler does not perform any additional network action in panic mode. Because reconciliation is not periodic, drift that appears while the process is running is repaired only at the next scheduler restart.

## Lease Lifecycle

Creation through `LeaseRepository.create()` validates the identity, device ownership and state, active profile assignment, profile policy, and requested duration. It stores `ended_at` using the UTC clock and creates a `pending_apply` provisioning operation with an immutable backend snapshot. The API status is computed, not persisted:

| Computed API status | Condition, in priority order |
| --- | --- |
| `revoked` | `revoked_at` is set |
| `expired` | `ended_at` has passed |
| `pending` | Provisioning is not `applied` and no error is recorded |
| `failed` | Provisioning is not `applied` and an error is recorded |
| `active` | The lease is neither revoked nor expired and provisioning is applied |

The API waits for provisioning confirmation before returning success; a failure or timeout returns an error and may trigger compensation.

Persisted `LeaseProvisioning` states are distinct from the API status:

```text
pending_apply -> applying -> applied -> deleting -> deleted
            |                      |
            +-> pending_delete      +-> pending_delete (failure, retried)
                 |                         |
                 +-> deleting -------------+
                    |
                    +-> uncertain (compensation for failed application)
```

`pending_apply` waits for application; `applying` is a claim written to the database while the backend call runs. `applied` confirms access and schedules expiration. Revocation or expiration immediately makes the lease invalid in domain state, then requests `pending_delete`; `deleting` is the database claim while removal runs. `deleted` confirms removal. If application fails, TTL-LAMa requests compensation; even after confirmed deletion, provisioning may remain `uncertain` because a delayed remote command could still apply the peer. A failed deletion returns to `pending_delete` and is retried by the poller. `applying` and `deleting` are therefore persisted temporarily, but are not final states. At startup reconciliation, each record is returned to `applied` or `deleted` according to desired state.

### Expiration and Revocation

After application is confirmed, APScheduler schedules a job at `ended_at`. When it fires, the scheduler reloads the lease and requests deletion if it is revoked or expired. Explicit revocation sets `revoked_at` and also requests deletion; the API status becomes `revoked` before the backend operation completes. In both cases, the invariant is that access for a revoked or expired lease must not remain provisioned.

### Key Ownership

Whenever possible, clients generate and retain their own private keys. TTL-LAMa only needs the public key required to provision the device:

```text
Client                              TTL-LAMa
  | Generate private key               |
  | Keep private key locally            |
  | Derive public key ----------------->| Register device
```

Storing a client private key should not be necessary for normal operation.

## Reconciliation

When the scheduler process starts, before APScheduler, `LeaseScheduler.reconcile()` compares desired database state with peers observed from the backend. It applies missing or divergent active peers, removes peers without an active lease, restores jobs for still-valid leases, and handles expired leases immediately. A lease that expired while the process was stopped therefore does not regain access after restart.

Full reconciliation does not run periodically. After startup, the scheduler polls only `pending_apply`, `pending_delete`, and `uncertain` operations; this poll is not a full comparison of all peers. Backend drift that appears during execution is repaired only at the next scheduler restart.

```text
Desired database state + observed backend state
          |
          +-- startup: full reconciliation and expiration-job restoration
          `-- runtime: poll pending operations
```

The invariants are:

```text
if ended_at <= now:          access must not exist
if the lease is revoked:     access must not exist
if the lease is active:      access must match the lease
```

The database is the persistent representation of desired state; the access backend represents the state actually applied. Reconciliation keeps them consistent.

## Example Flow

1. Alice authenticates.
2. TTL-LAMa resolves her identity and authorized access profiles.
3. She selects her laptop, the `server-admin` profile, and a duration of two hours.
4. TTL-LAMa creates the lease and provisions the corresponding WireGuard peer.
5. At expiration, or after explicit revocation, TTL-LAMa removes the peer.

If Alice authenticates through an external identity provider, the lease flow remains the same after authentication.

## Audit Events

Each line uses the process-specific UTC format: `[TTL-LAMa API]-[yyyy-mm-dd HH:mm:ss] : <operation>-<Log>` or `[TTL-LAMa Scheduler]-[yyyy-mm-dd HH:mm:ss] : <operation>-<Log>`. The result is included in the message (`succeeded`, `failed`, `requested`, or `superseded`); `INFO`, `WARNING`, and `ERROR` levels route events to their history files.

| Operations | Origin and recorded result | Permitted metadata |
| --- | --- | --- |
| `lease.create`, `lease.revoke` | API: success after commit or validation/persistence failure | Lease/device/profile IDs on success where available; error class on failure |
| `lease.apply`, `lease.delete` | API: result confirmed by the scheduler, including failure or timeout | Lease ID and HTTP status |
| `lease.provisioning.apply`, `lease.provisioning.delete` | Scheduler: backend operation result | Lease ID and error class or exit code |
| `lease.expire` | Scheduler: deletion requested and expiration removed | Lease ID |
| `device.revoke` | API: device revocation after commit | Device ID |
| `reconciliation.startup` | Scheduler: each startup attempt and final result | Attempt number and error class |
| `reconciliation.run` | Scheduler: successful reconciliation | Lease count and active peer count |
| `provisioning.poll`, `panic.script`, `panic.email` | Scheduler: polling errors or panic action results | Error class only |

Metadata excludes passwords, secret values, raw tokens, private keys, complete public keys, request bodies, remote `stderr`, and raw exception messages. `lease.create` is logged after the domain commit; `lease.apply` separately records backend confirmation. Likewise, `lease.revoke` precedes the backend result `lease.delete`. A failed deletion remains pending and is logged as a `lease.provisioning.delete` failure before retry. Startup reconciliation and provisioning failures should trigger operational alerts; panic mode can run the administrator script after the configured retry count. These logs are diagnostic and do not replace an immutable or transactional audit ledger.
