# Registration Validation Fix v2.2.5

## Fix
- Reject whitespace-only and punctuation-only registration values.
- Enforce Hive ID format: 3–64 characters, starting with a letter/number and containing only letters, numbers, `_` or `-`.
- Validate on both frontend and backend.
- Preserve duplicate-ID protection and required-field validation.

## Regression coverage
- Blank registration: rejected.
- Whitespace-only registration: rejected.
- Punctuation-only registration: rejected.
- Valid `HIVE_TEST-VALID`: accepted.
- Duplicate Hive ID: rejected.
