# API

All application endpoints are rooted at `/api/v1`; interactive OpenAPI documentation is available at `/docs`. Responses use appropriate HTTP status codes and validation errors do not expose stack traces. Pagination, filters and sorting are server-side. Administrative routes require an authenticated system admin session. The system admin password comes only from `INITIAL_ADMIN_PASSWORD`; regular user passwords are stored as PBKDF2 hashes in the database.

Managed users call `POST /auth/login` only for first-device registration. Discoverable Passkey login uses public `POST /auth/passkeys/authentication/options` followed by `POST /auth/passkeys/authentication/verify`; the challenge cookie and database record are short-lived and single use. Admin can reset only authentication material with `DELETE /admin/users/{id}/passkey`, or delete a regular user and that user's learning data with `DELETE /admin/users/{id}`. System admin deletion is rejected.

