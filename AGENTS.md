# Development rules

- Read this file before changing project files.
- Preserve source data and answer-version history; never overwrite originals.
- Keep scoring and pass/fail authority in the backend.
- Keep configuration in environment variables or the settings table.
- Python uses typed functions, Pydantic schemas, service/repository separation, and testable AI adapters.
- React uses strict TypeScript, TanStack Query for server state, accessible labels, and explicit loading/error states.
- Database changes require Alembic migrations, UTC timestamps, foreign keys, indexes, and documented rationale.
- Tests must not call external AI services; randomness uses fixed seeds and time-sensitive logic uses an injectable clock.
- Do not commit secrets, generated data, dependency folders, or build output.
