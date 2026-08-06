# Dataset format

A dataset directory contains `manifest.json`, `certifications.json`, `domains.json`, `questions.jsonl`, optional `assets/`, and `validation_report.json`. Question records are streamed one JSON object per UTF-8 line; do not wrap them in an array. The canonical question schema is `data/schema/question.schema.json`.

Question IDs and choice IDs within each question must be unique. `final_answers` must contain exactly `required_answer_count` values, and every answer must reference an existing choice. A `multiple_choice` record must require one answer. Asset references must be relative paths contained by the dataset directory.

Validation checks syntax and schema, certification/domain references, duplicates, answer cardinality, content hashes, and assets. `dry-run` performs no database writes; `strict` rolls back the whole import on any error; `partial` commits valid records and reports rejected records without overwriting originals or answer history.

```powershell
.\scripts\import-dataset.ps1 -Path ".\data\processed\dataset" -Mode "dry-run"
.\scripts\import-dataset.ps1 -Path ".\data\processed\dataset" -Mode "partial"
```

