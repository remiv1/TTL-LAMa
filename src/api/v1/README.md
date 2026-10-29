# Routes

## API

```txt
app
 ├── api
 │    ├── v1
 │    │    ├── auth (POST)
 │    │    ├── users (GET, PATCH)
 │    │    │     ├── devices  (GET)
 │    │    │     ├── leases   (GET, POST, PATCH)
 │    │    │     └── profiles (GET)
 │    │    └── admin
 │    │          ├── users
 │    │          │     └── profiles
 │    │          ├── devices
 │    │          ├── leases
 │    │          └── profiles
 │    └── v2 ... another day, another version
 └── web
      ├── index.html
      └── assets
```

## Admin API v1

All endpoints below are relative to `/api/v1/admin`. Authentication uses the
existing session cookie or `Authorization: Bearer <session_token>`. Every admin
endpoint (including HEAD and OPTIONS) requires an enabled user whose persisted
`is_admin` flag is true: missing/invalid authentication returns 401, and an
authenticated non-admin receives 403. Access profiles are network policies, not
administrator roles.

Cookie-authenticated mutations also require `X-CSRFToken`, obtained from
`GET /api/v1/csrf`. Requests without valid bearer authentication undergo CSRF
validation first and may receive 400 for a missing token. Bearer-authenticated
mutations do not require CSRF. Authorization headers take precedence over cookies.

| Method | Path | Operation / optional query filters |
| --- | --- | --- |
| GET | `/users` | List; `device`, `lease`, `profile` |
| POST | `/users` | Create |
| GET, PATCH, DELETE | `/users/<user_id>` | Read, update, disable |
| GET | `/users/<user_id>/profiles` | List active assignments |
| PUT, DELETE | `/users/<user_id>/profiles/<profile_id>` | Assign, unassign (idempotent) |
| GET | `/devices` | List; `lease`, `profile` |
| GET, PATCH, DELETE | `/devices/<device_id>` | Read, update, logically delete |
| POST | `/devices/<device_id>/block` | Block |
| GET | `/leases` | List; `user`, `device`, `profile`, `status` |
| GET | `/leases/<lease_id>` | Read |
| POST | `/leases/<lease_id>/revoke` | Revoke (idempotent) |
| GET | `/profiles` | List; `user`, `device`, `lease` |
| POST | `/profiles` | Create policy |
| GET, PATCH, DELETE | `/profiles/<profile_id>` | Read, update, revoke |

User identifiers are UUIDs; other identifiers are positive integers. Filters
combine with AND; unknown, invalid or repeated filters return 400. Relationship
filters use historical leases; user/profile filters use non-revoked assignments.
Lease status is derived as `revoked` (takes precedence), `expired`, or `active`.
Lists include logically deleted records so that history remains inspectable.
Lists return JSON arrays; reads, assignments and updates return JSON objects.
Creation returns 201, successful deletion/unassignment returns 204, invalid input
returns 400, missing resources return 404, and uniqueness/state conflicts return
409. Timestamps are ISO 8601 UTC. Credentials and session tokens are never exposed.

### Request bodies

- Users: `username` (required at creation, 1-50 characters), nullable `email`,
  `enabled` and `is_admin` (booleans), optional `password` (1-1024 characters).
  Password management is only available in internal authentication mode and uses
  the configured Argon2id hasher. Without a password, no internal credential is
  created. Existing external identity linking is unchanged.
- Devices: PATCH accepts `name` (1-255 characters) and `public_key`
  (1-512 characters). Ownership and lifecycle timestamps cannot be supplied.
  Device creation remains outside the admin API, as planned above.
- Profiles: creation requires `name` (1-255 characters), `default_duration`,
  `maximum_duration`, and a non-empty `networks` list of CIDRs. Durations use
  `d`, `h`, `m`, `s` units, are positive, and default duration cannot exceed the
  maximum. PATCH accepts any subset and validates the merged policy.
  Responses include the policy under `policy`:

  ```json
  {
    "id": 1,
    "name": "server-admin",
    "policy": {
      "default_duration": "1h",
      "maximum_duration": "8h",
      "networks": ["10.0.0.0/24"]
    }
  }
  ```

Unknown body fields, empty PATCH bodies, and explicit nulls (except `email`)
are rejected. Server-managed IDs, timestamps, relationships and password hashes
cannot be overwritten.

### Persistence and revocations

Repositories in [`api/common/repositories`](../common/repositories) share
queries, password/session changes, policy validation and dependent revocations.
They flush when necessary but never commit: API handlers own transactions, and
future global-config operations can compose repositories into one transaction.

Policies are persisted in the new `profile_policies` table, created by normal
database initialization without altering existing profile columns. At startup,
the access-profile YAML file seeds missing profiles/policies only. Persisted
edits take precedence on restart; deleted profiles are not resurrected, and YAML
is not rewritten by API operations. Existing SQL profiles without a policy return
`policy: null` until a complete policy is supplied or seeded. Profile names must
be unambiguous when importing YAML.

Deleting/disabling a user revokes sessions, devices, assignments and leases.
Deleting/blocking a device revokes its leases (both operations use `revoked_at`
in the current model). Deleting a profile revokes its assignments and leases;
unassignment revokes the associated leases. Changing a device public key or
profile policy also revokes affected leases. Renaming does not. Password and
privilege changes invalidate sessions. Re-enabling a user does not restore
previously revoked access. Reassignment creates a new association, preserving
old leases and their history.

These operations persist the desired revocation state. Actual network removal
still depends on the access-backend reconciliation described in
[operations](../../../docs/operations.md); this API does not introduce a VPN
provisioner.

## CLI

```md
ttlama
 ├── auth → **Authentification** → **_Qui suis-je ?_**
 │    ├── login
 │    │     ├── internal --user <username>
 │    │     ├── external --user <username>
 │    │     └── oidc --user <username>
 │    │
 │    ├── logout
 │    └── status
 │
 ├── user → **Utilisation** → **_Qu'est-ce que j'utilise ?_**
 │    ├── get
 │    │
 │    ├── devices
 │    │     ├── list
 │    │     ├── get --id <device_id>
 │    │     ├── add --file <file_path>
 │    │     └── delete --id <device_id>
 │    │
 │    ├── leases
 │    │     ├── list
 │    │     ├── get --id <lease_id>
 │    │     ├── create --file <file_path>
 │    │     └── revoke --id <lease_id>
 │    │
 │    └── profiles
 │          ├── list
 │          └── get --id <profile_id>
 │
 ├── global-config → **Configuration** → **_Comment l'instance fonctionne ?_**
 │    ├── get [--output <file_path> | none]
 │    ├── diff --file <file_path> [--colored-diff | none]
 │    ├── validate --file <file_path>
 │    └── apply --file <file_path> [--dry-run | none]
 │
 └── admin → **Administration** → **_Qui a doit à quoi / Quel est l'état administré ?_**
      │
      ├── users
      │     ├── list [--device <device_id> &/| --lease <lease_id> &/| --profile <profile_id> | none]
      │     ├── get --user <user_id>
      │     ├── create --file <file_path>
      │     ├── update --user <user_id> --file <file_path>
      │     ├── delete --user <user_id>
      │     ├── assign --user <user_id> --profile <profile_id>
      │     └── unassign --user <user_id> --profile <profile_id>
      │
      ├── devices
      │     ├── list [--lease <lease_id> | --profile <profile_id> | none]
      │     ├── get --device <device_id>
      │     ├── update --device <device_id> --file <file_path>
      │     ├── block --device <device_id>
      │     └── delete --device <device_id>
      │
      ├── leases
      │     ├── list [
      │     │         --user <user_id>
      │     │     &/| --device <device_id>
      │     │     &/| --profile <profile_id>
      │     │     &/| --status <status>
      │     │     | none
      │     │     ]
      │     ├── get --lease <lease_id>
      │     └── revoke --lease <lease_id>
      │
      └── profiles
            ├── list [--user <user_id> &/| --device <device_id> &/| --lease <lease_id> | none]
            ├── get --profile <profile_id> [--output <file_path> | none]
            ├── create --file <file_path>
            ├── update --profile <profile_id> --file <file_path>
            └── delete --profile <profile_id>
```
