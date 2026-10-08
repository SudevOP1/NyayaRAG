# Golden data and reference checks: changelog

Append-only. Golden-set versions (P2+) and hand-checks of reference data are logged here.

## Mapper hand-check (P1)

- Sample: `MAPPER_HANDCHECK.md` (40 rows, seed 42).
- Checked against: UP Police / CAPT PDFs: _pending_ · NCRB Sankalan: _pending_
- Agreement: _pending_ (fill in: x/40 PDF, y/40 Sankalan, who checked, date)
- Known-pair tests (`tests/test_mapper.py`): expectations confirmed against the UP Police PDF on
  2026-10-08. IPC 302 maps to BNS 103 (section level); IPC 124A is "Deleted" and BNS 152 a "New
  Section", so 124A answers "no direct equivalent" with a closest-provision note.
