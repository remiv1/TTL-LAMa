# Operations

This document describes the intended lifecycle of an access lease and how TTL-LAMa keeps the persisted desired state aligned with the access backend. The project is still at the design/prototype stage; these behaviors are not yet an operational runbook.

## Lease Lifecycle

A lease follows an explicit lifecycle:

```text
REQUESTED -> authorization -> ACTIVE -> EXPIRED
                                  `-----> REVOKED
```

Additional states such as `PENDING_APPROVAL`, `DENIED`, `SUSPENDED`, or `ERROR` may be introduced if concrete use cases require them. The number of states should remain as small as possible.

An active lease is associated with an identity, a device, an access profile, and a duration. Its expiration is part of the desired state:

```text
expires_at <= now
    => lease = EXPIRED
    => provisioned_access = ABSENT
```

### Provisioning

When a lease becomes active, TTL-LAMa asks the configured access backend to materialize it. For WireGuard, the relevant information includes the device public key, VPN address, access profile, and expiration.

When the lease expires or is revoked, the backend must remove the corresponding access. A lease must not merely be marked `EXPIRED` or `REVOKED` while its network access remains provisioned.

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

TTL-LAMa must not rely exclusively on a scheduled task running at the exact expiration time. If the application stops before a lease expires and restarts later, the expired access must still be removed.

The system periodically compares:

```text
Desired state (database) <-> TTL-LAMa <-> Actual state (access backend)
```

The invariants are:

```text
if expires_at <= now:        access must not exist
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
