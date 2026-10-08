# Parser and mapper patches

Reviewed YAML fixes for edge cases. Nothing is special-cased silently in code: every fix lives here
with a reason and what it was checked against.

| File | Applied by | Shape |
|---|---|---|
| `acts.yaml` | `nyaya/ingest/parse_acts.py` | `- {act, section, field: title\|text\|in_force, value, reason, checked_against}` |
| `mapping.yaml` | `nyaya/ingest/parse_mapping.py` | `- {match: {bns?, ipc?}, set: {...}, reason, checked_against}` or `- {add: {...}, reason}` |
| `mapper_notes.yaml` | `nyaya/ingest/parse_mapping.py` | `- {ipc, note, reason}` |
