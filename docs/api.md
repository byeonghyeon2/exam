# API

All application endpoints are rooted at `/api/v1`; interactive OpenAPI documentation is available at `/docs`. Responses use appropriate HTTP status codes and validation errors do not expose stack traces. Pagination, filters and sorting are server-side. Administrative routes require `ADMIN_ACCESS_KEY` when configured; this shared key is a local convenience, not a complete authentication system.

