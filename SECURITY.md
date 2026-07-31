# Security Policy

substrate-alignment provides primitives used in safety-relevant agent code: the net-potential-gain gate, the halt-and-escalate protocol, drift-signal detection, audit-chain types. Defects in these primitives can have downstream safety consequences. Treat vulnerabilities accordingly and report them privately.

## Supported versions

substrate-alignment is pre-1.0. Security fixes are applied to the latest minor release.

| Version | Supported          |
| ------- | ------------------ |
| `0.x`   | Latest minor only  |

Once `1.0` ships, this table will list the actively maintained major / minor lines.

## Reporting a vulnerability

Use one of the following private channels:

- **Preferred:** [GitHub Security Advisory](https://github.com/System9ai/substrate-alignment/security/advisories/new). Drafts are private and let us collaborate on the fix.
- **Email:** `security@system9.ai`.

Please include:

- A description of the vulnerability.
- A minimal reproduction (code snippet, failing test, or scenario).
- The observed impact (incorrect gate outcome, missed halt condition, audit-chain divergence, unsafe defaults, etc.).
- Whether public disclosure is acceptable, and any timing constraint on your side.

**Please do not** open public issues or pull requests describing vulnerabilities.

## Response timeline

We aim for the following turnaround on private reports:

| Stage                          | Target          |
| ------------------------------ | --------------- |
| Acknowledge receipt            | 5 business days |
| Initial assessment             | 14 days         |
| Fix or coordinated disclosure  | 90 days         |

For vulnerabilities that affect deployed safety-relevant primitives (NPG gate, halt-and-escalate protocol), we will prioritise the fix and may request a shorter coordinated-disclosure window with your agreement.

## Scope

**In scope:**

- The reference Python implementation under `python/src/substrate/`.
- The specifications under `spec/`: errors that allow a conforming implementation to violate stated invariants.
- The conformance probes under `conformance/probes/`: false positives or false negatives that mis-classify implementations.
- GitHub Actions workflows in this repository.

**Out of scope:**

- Vulnerabilities in third-party dependencies. Please report those upstream; we are happy to track and update.
- Deprecated or unsupported versions.
- Theoretical issues without a concrete reproduction.
- Denial-of-service via pathological input on primitives explicitly documented as untrusted-input handlers (none, currently).

## Acknowledgement

With your permission, we credit reporters in the release notes for the version containing the fix. If you prefer to remain anonymous, please say so in your report.
