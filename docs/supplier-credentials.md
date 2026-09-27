# Local supplier credential storage

Open `/supplier-connection` on the local AdvanCore server. This feature saves,
replaces and removes Santa FMS credentials in macOS login Keychain. No supplier
login, download, scheduler or secret-read endpoint is included.

Only code and synthetic tests belong in this repository. Do not commit passwords,
Keychain exports, cookies, supplier reports, database backups or business audit data.

## Security boundary

- Fixed service/account identifiers, native Security.framework calls; no shell
  arguments containing credentials and no plaintext fallback.
- Loopback peer, allowed Origin, action token and explicit confirmation required.
- Bounded input; generic errors; credentials never returned by the API.
- No database migrations or operational record changes.
- Password fields clear after submission and are never refilled from storage.
- macOS only; unsupported or locked Keychains fail closed.
- This trusts the local user account. It does not protect against compromised
  local software. Python transient strings cannot guarantee secure memory erasure.
- Do not enable HTTP request-body logging or expose this local service publicly.

## Verification

Run `python -m pytest tests/test_supplier_credentials.py -q`.
Tests use a fake vault and synthetic secrets, not the real supplier account.
Native Keychain save/replace/remove was separately exercised locally with a
synthetic item, which was removed after the test. A browser check of the local
form verified masking and empty saved-value fields.

## Release scope

The importer, consumption dashboard and finance migrations remain separate local
work with additional dependencies. This page deliberately uses a standalone
stylesheet and dashboard back-link so this PR does not require those changes.
