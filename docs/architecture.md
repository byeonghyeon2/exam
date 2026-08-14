# Architecture

The React client calls the versioned FastAPI API. FastAPI owns scoring, pass/fail decisions, import transactions, answer history, and OpenAI access. Services coordinate domain rules; repositories isolate SQLAlchemy persistence. MySQL 8 stores UTC timestamps and application settings. The importer streams JSONL, validates before persistence, records job-level and row-level errors, and never mutates source files.

OpenAI is optional: study, scoring, mock exams and stored explanations continue without it. AI output is schema-validated, cached, logged without prompts or secrets, and never silently replaces a provided or administrator-final answer.

Authentication uses an HttpOnly session cookie and resident Passkeys. A managed user uses the administrator-issued password only to open the first-device registration ceremony. Subsequent login starts with an anonymous, short-lived, single-use challenge stored as a hash-backed `exam_passkey_challenges` record; the discoverable credential identifies the user. Existing sessions are revoked only after assertion verification succeeds. Device reset removes Passkey credentials and sessions but keeps the account and learning data. Account deletion removes user-owned study attempts, study sessions, mock exams, wrong notes, sessions, and credentials while retaining shared certifications, questions, and AI explanations.

