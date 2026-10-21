# Project

This document summarizes TTL-LAMa's intended uses, principles, roadmap, and current status.

## Use Cases

- **Homelab:** provide temporary remote administration without keeping permanent VPN access on every device.
- **Self-hosted infrastructure:** control access to servers, NAS devices, and internal administration interfaces.
- **Maintenance:** provide a profile limited to a resource and duration for a one-off intervention.
- **Small organization:** centralize temporary access assignment and revocation without requiring a particular identity provider.
- **Existing infrastructure:** integrate with an existing OIDC provider and database while keeping lease management in TTL-LAMa.
- **Automation:** eventually let other systems request or monitor temporary access under administrator-defined policies.

## Project Principles

### Do One Thing Clearly

Manage time-limited access leases. TTL-LAMa is not intended to become a general-purpose network administration platform.

### Remain Deployable

A standalone installation should fit in a single container. The minimal setup should not require complex infrastructure.

### Remain Configurable

Infrastructure policy is declarative and belongs to the operator, not the user interface.

### Be Secure by Design

Every access has a lifecycle. Expiration and revocation are core invariants, not optional features added on top of the model.

### Separate Domain Logic from Implementations

Identity, persistence, and access backends are abstractions around the lease model. WireGuard, SQLite, and OIDC are implementations, not the conceptual core.

### Stay Open

TTL-LAMa is intended to be open source and suitable for self-hosting.

## Roadmap

### Phase 0: Design

- [ ] Define the threat model
- [ ] Define the `Identity / Device / Profile / Lease` model
- [ ] Define the lease state machine
- [ ] Define configuration and access profile formats
- [ ] Define authentication, persistence, and access backend abstractions
- [ ] Define the audit model

### Phase 1: Standalone Prototype

- [ ] Single-container deployment
- [ ] Internal authentication and multi-factor authentication
- [ ] SQLite persistence
- [ ] WireGuard backend
- [ ] Device management and public key registration
- [ ] Access profiles and time-limited leases
- [ ] Automatic expiration and manual revocation
- [ ] Reconciliation and audit log

### Phase 2: Integration

- [ ] External authentication and OIDC
- [ ] PostgreSQL
- [ ] Associations between external identities and profiles
- [ ] Health checks, metrics, and observability
- [ ] Enhanced auditing capabilities

### Phase 3: Extensibility

- [ ] Stabilize the access backend interface
- [ ] Explore other authentication mechanisms and access backends
- [ ] Optional approval workflows
- [ ] Automation API and third-party integrations

## Mascot

TTL-LAMa's mascot is a **guardian llama**. Its visual identity combines:

- a llama as the project's recognizable identity;
- a cap representing its guardian role;
- a stopwatch representing the limited lifetime of access.

The stopwatch represents the project's central promise: **every access has a lifetime**.

## Status, Contributions, and License

> **Initial design / prototype**

TTL-LAMa is currently at the design stage. The APIs, configuration formats, data schemas, and architectural choices are preliminary and may change during implementation. The initial goal is a model that is simple, explicit, auditable, testable, secure, and extensible without unnecessary complexity.

Discussion and contributions are especially welcome on the threat model, security architecture, identity/device/profile/lease model, authentication, OIDC and WireGuard integration, container isolation, Linux privileges, persistence, reconciliation, network policies, and auditing.

**License:** to be determined before the first stable public release.
