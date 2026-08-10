# Security policy

This is an unofficial, community-built Home Assistant integration. It is **not**
affiliated with, endorsed by, or supported by Vext.

## Reporting a vulnerability

**Please do not open a public issue for anything security-related.**

Two cases:

- **A problem in this integration** (credential handling, storage, the bundled
  dashboard card, dependency issues): email the maintainer at
  `me_security@necmes.com`, or use GitHub's private
  [security advisory](https://github.com/necmes/ha-vext/security/advisories/new)
  form on this repository.
- **A problem in the Vext service or app itself** (anything server-side, access
  control, data belonging to other accounts): it belongs to Vext, not here.
  Report it privately to Vext directly — do not file it on this repository. If
  you do not have a contact there, email the maintainer and it will be forwarded
  privately without any public disclosure.

Please allow a reasonable window for a fix before disclosing anything publicly.

## Scope and intent

This integration signs in with the user's own Vext account and reads and writes
only that account's own data, exactly like the official app does. It does not
attempt to bypass authentication or access controls, and it deliberately keeps
its request volume low. See "How this behaves against the Vext service" in the
[README](README.md).
