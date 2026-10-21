# TTL-LAMa 🦙⏱️

English | [Français](./docs/README.fr.md)

> **Time-To-Live Lease Access Manager**
>
> **Temporary access. Automatic revocation.**

TTL-LAMa is an open-source access manager for granting temporary, time-limited access to private networks. Instead of permanent VPN access, it treats each authorization as a **lease** with a defined expiration.

Users authenticate, select an authorized access profile and device, and receive access for a limited duration. When the lease expires or is revoked, the corresponding network access is removed. The first planned backend is **WireGuard**.

## Goals

- Time-limited network access with automatic expiration and revocation.
- Administrator-defined access profiles and device-specific VPN identities.
- Internal or external authentication, with local or external persistence.
- A standalone deployment path and an architecture open to other access backends.

TTL-LAMa manages access leases; it is not a general network administration interface, a replacement for WireGuard, or a general-purpose identity provider. Infrastructure policies remain under the operator's control.

## Documentation

| Topic | English | Français |
| --- | --- | --- |
| Architecture and domain model | [Architecture](docs/architecture.md) | [Architecture](docs/architecture.fr.md) |
| Deployment and configuration | [Deployment](docs/deployment.md) | [Déploiement](docs/deployment.fr.md) |
| Lease lifecycle and reconciliation | [Operations](docs/operations.md) | [Fonctionnement](docs/operations.fr.md) |
| Security principles | [Security](docs/security.md) | [Sécurité](docs/security.fr.md) |
| Use cases, roadmap, and project status | [Project](docs/project.md) | [Projet](docs/project.fr.md) |

## Project Status

TTL-LAMa is at the initial design / prototype stage. The APIs, configuration formats, data schemas, and architectural choices are preliminary and may change during implementation. See the [project overview](docs/project.md) for the roadmap and contribution topics.

**License:** to be determined before the first stable public release.

---

> **TTL-LAMa 🦙⏱️**
> *Time-To-Live Lease Access Manager*
> **Temporary access. Automatic revocation.**
