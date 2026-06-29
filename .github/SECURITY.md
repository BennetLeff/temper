# Security Policy

## Supported Versions

Only the latest commit on the `main` branch receives security updates.
No formal release versions are maintained at this time.

## Reporting a Vulnerability

**Do not open a public issue.**

To report a security vulnerability, please email the maintainer directly.

You should receive an acknowledgment within 5 business days. The project
follows responsible disclosure: once a fix is prepared, we will coordinate
a disclosure timeline with the reporter.

## Scope

Security reports are welcomed for any of the following:

- Firmware vulnerabilities (buffer overflows, injection, authentication
  bypass) in `firmware/`
- Safety-critical logic defects in the induction cooker state machine
- Supply-chain risks in dependencies (Python, Rust, or ESP-IDF ecosystem)
- Hardware design vulnerabilities in `pcb/` (unsafe isolation, thermal
  risks, electrical hazards)
- CI/CD pipeline integrity issues in `.github/workflows/`

## Out of Scope

- Issues in unmodified third-party dependencies (report upstream)
- Hypothetical attacks requiring physical access to the device
- Denial-of-service against the CI infrastructure
