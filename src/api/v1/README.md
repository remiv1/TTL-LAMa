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
 │    │          └── leases
 │    └── v2 ... another day, another version
 └── web
      ├── index.html
      └── assets
```

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
