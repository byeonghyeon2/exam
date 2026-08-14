# Database

MySQL uses `utf8mb4` and UTC. Schema changes are made only through Alembic. Foreign keys protect ownership; unique constraints protect question UIDs and choice keys; indexes support certification/domain/status selection, random candidate sampling, wrong notes, reports, and import jobs. Questions use soft deactivation. Answer versions are append-only and identify the current version; originals are never overwritten.

All application-owned table names start with `exam_`. Alembic's internal `alembic_version` table and unrelated legacy/shared tables in the same database are intentionally excluded. Migration `0008_prefix_application_tables` renames the 19 application tables without copying or deleting their rows and is safe to rerun after a partial rename.

