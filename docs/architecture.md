# Architecture

The React client calls the versioned FastAPI API. FastAPI owns scoring, pass/fail decisions, import transactions, answer history, and OpenAI access. Services coordinate domain rules; repositories isolate SQLAlchemy persistence. MySQL 8 stores UTC timestamps and application settings. The importer streams JSONL, validates before persistence, records job-level and row-level errors, and never mutates source files.

OpenAI is optional: study, scoring, mock exams and stored explanations continue without it. AI output is schema-validated, cached, logged without prompts or secrets, and never silently replaces a provided or administrator-final answer.

