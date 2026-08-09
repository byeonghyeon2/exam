# API

All application endpoints are rooted at `/api/v1`; interactive OpenAPI documentation is available at `/docs`. Responses use appropriate HTTP status codes and validation errors do not expose stack traces. Pagination, filters and sorting are server-side. Administrative routes require an authenticated system admin session. The system admin password comes only from `INITIAL_ADMIN_PASSWORD`; regular user passwords are stored as PBKDF2 hashes in the database.

