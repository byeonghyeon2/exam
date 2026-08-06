# Database

MySQL uses `utf8mb4` and UTC. Schema changes are made only through Alembic. Foreign keys protect ownership; unique constraints protect question UIDs and choice keys; indexes support certification/domain/status selection, random candidate sampling, wrong notes, reports, and import jobs. Questions use soft deactivation. Answer versions are append-only and identify the current version; originals are never overwritten.

