# Security Model

TTL-LAMa is a sensitive infrastructure component: it controls network access and may require more privileges than an ordinary web application. The design therefore emphasizes narrow permissions, explicit policies, automatic revocation, and auditability.

## Least Privileges

TTL-LAMa should request only the system capabilities required by the configured backend. Running with full privileges should be avoided when a more limited set of capabilities is sufficient.

## Minimal Public Surface

The user-facing surface should be limited to operations that are actually needed:

- authentication;
- managing one's own devices;
- requesting access;
- viewing one's own access;
- revoking one's own access.

Infrastructure configuration does not belong in this interface. A general administration interface for dynamically changing network configuration is not planned.

## Declarative Policies

Administrators define policies in configuration and users choose only from the options made available to them. A user must not be able to submit arbitrary network rules or expand an access profile's limits.

## Least Privilege

Each profile should provide only the access required for its intended use. For example, a maintenance profile might allow SSH to one server, while an administration profile might allow access to a defined server network and only the required interfaces.

Having VPN access does not necessarily mean having access to the entire private network.

Destination filtering is an external router responsibility. TTL-LAMa manages leases and WireGuard peers only; it never reads or modifies nftables at runtime. The installer prints integration proposals and can include commented rules in the host preparation script, without applying them. Client-side `AllowedIPs` are editable routing parameters, not a server-enforced access-control list.

## Application Baseline

In production, configuration must provide a Flask key of at least 32 characters and enable `Secure` cookies. Authentication is mandatory and must use either the internal account store or an external identity provider. Session cookies are `HttpOnly` and `SameSite=Lax`; state-changing requests are protected against CSRF.

Secrets may be mounted under `/run/secrets/` and referenced through `_FILE` settings. They must not appear in logs or in the image. Persisted session tokens are stored as digests.

The container runs without root privileges. Changing the authentication mode or issuer does not automatically delete existing accounts; it requires an explicit migration.

## Automatic Revocation

Expiration changes the lease state and releases its claim on the device's WireGuard peer. Several profiles may have concurrent leases on the same device/interface. The peer is removed after the last active lease ends:

```text
LAST ACTIVE LEASE ENDS -> WIREGUARD PEER REMOVED
```

The same applies to explicit revocation. Reconciliation restores the desired peer state after a restart. Partial expiration does not remove a destination from an external firewall while another lease keeps the peer active. An appropriate external policy is required; TTL-LAMa does not claim per-profile destination revocation or connection-tracking enforcement. Downloaded client configurations are snapshots and do not expire themselves.

## Auditability

Sensitive operations should generate audit events, including:

- authentication and authentication failures;
- device registration and revocation;
- lease creation and activation;
- lease expiration and manual revocation;
- provisioning failures;
- reconciliation.

Audit logs must not contain private keys or credentials.
