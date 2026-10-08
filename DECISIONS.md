# Decisions

What was chosen and why. Append whenever a non-obvious choice is made (PLAN.md §0.1 rule 9).

## P1: Foundation (2026-10-08)

### Data sources
- **Act PDFs come from the MHA-hosted Gazette copies, not India Code.** India Code returned 403
  to scripts and "An error occurred" in the browser for all three bitstream links. The Ministry of
  Home Affairs hosts the Gazette of India (Extraordinary, Part II Sec. 1) copies of Acts 45, 46 and
  47 of 2023 as published by the Legislative Department: the same enacted text. URLs are in
  `nyaya/ingest/download.py`; SHA-256 hashes in `data/raw/MANIFEST.json`. India Code remains the
  cited reference.
- **Kaggle token**: `download.py` accepts `kaggle.json`, the newer `~/.kaggle/access_token` file, or
  env vars. The token file is read with BOM detection, because PowerShell's `>` writes UTF-16 and the
  Kaggle client then sends a corrupt `Authorization` header.

### PDF spike → layout (a), Gazette layout
- All three Acts use the Gazette layout: bold `N.` at the paragraph indent (x≈141.6 pt) of a
  117.6–477.6 pt text column; section heading = marginal note (~7.9 pt) in the outer margin (right
  on odd pages, x≈486; left on even, x≈58), top-aligned with the section's first line.
- Running header (`THE GAZETTE OF INDIA EXTRAORDINARY`, `[PART II—SEC. 1]`, page number, rules)
  sits above y≈79 and is dropped by position. The bilingual masthead on the first and last pages
  uses legacy Devanagari fonts (Vivek, Mangal), dropped by font name; parsing starts after
  "BE it enacted" and stops at `THE … SCHEDULE` or the em-dash rule before the signature.
- **Word spacing is rebuilt from glyph boxes.** PyMuPDF's text drops some inter-word spaces
  ("ThisAct maybe"). Measured: missing spaces leave 1.2–1.5 pt gaps, kerning ≤ 0.8 pt at 10 pt, so
  a gap > 0.095 × font size becomes a space.
- Paragraph breaks: vertical gap > 1.42 × font size (leading 10.8–12.9 pt, paragraph gaps
  ≥ 15.8 pt); a line starting lowercase never starts a paragraph; across a page break a new
  paragraph needs a structural marker.
- Sub-sections: `(N)` paragraphs in sequence with an indent < 180 pt. Nested numbered lists inside
  clauses (BNS 4(c) "(1) Rigorous", at 190 pt) are not sub-sections. BNS 2 / BNSS 2 definitions are
  kept as numbered units so `[BNS 2(8)]` stays citable, matching the correspondence table.
- Headings: a line counts as centred only if left and right gaps match and it is not a clause/
  continuation line; chapter sub-headings ("Of offences affecting life", "A.—Summons") are dropped
  from section text, "Illustration(s)." headings are kept.
- Marginal notes: notes touching each other are split at a line ending "." followed by a capital;
  Act citations printed in the margin ("45 of 1860.") are cut out as separate segments and dropped;
  sections and notes are matched one-to-one, nearest first, within ±25 pt on the same page.
- **BNS 106(2) `in_force=false`** is applied from `data/patches/acts.yaml` (with source), not code.
- BNSS First/Second Schedules and the BSA Schedule (certificate form) are out of scope (stretch).

### Cross-check
- Titles `token_set_ratio`, bodies `ratio` on lowercase alphanumerics, threshold 90. BNSS is
  checked on titles only (Kaggle #4 is not a clean body transcription).
- Result: 9/1,059 sections flagged after fixing three parser title bugs the check found (Act
  citations merged into BNSS 300, BNSS 386, BSA 103 titles). Verdicts are the developer's.

### Chunker
- Token counts use bge-small's own `tokenizer.json` with special tokens and truncation off.
- A not-in-force sub-section is never packed with in-force text, so `in_force` on a chunk is exact
  (BNS 106 → two chunks).
- `Formerly:` lists at most 5 IPC refs then "…", to keep the header from eating the token budget
  (BNS 2 maps to ~40 IPC sections). Known wart: the header lists the section's refs on every chunk;
  per-sub-section refs (2(12) → IPC 17) would be more precise. Revisit with the P2 `enrich` ablation.
- Oversized blocks fall back to paragraph, then sentence boundaries; sentence-level cuts of a clause
  are logged in `chunk_stats.json → clause_splits` (currently none).

### Mapper
- Source: Kaggle #5 (`BNS_IPC_Comparative.csv`), a transcription of the UP Police / CAPT
  government table; 578 rows, statuses exactly as PLAN §3. IPC offence names and punishments
  joined from #7.
- **Known-pair expectations follow the table**, checked against the UP Police PDF: IPC 302 → BNS 103
  (section level, not 103(1)); IPC 124A is *Deleted* and BNS 152 is a *New Section*, so 124A
  returns "no direct equivalent" plus a reviewed note (`data/patches/mapper_notes.yaml`) that BNS 152
  is the closest provision, not a re-enactment.
- Agreement with Kaggle #6 (independent, NCRB CyTrain-derived): 150/150 at section level
  (`data/golden/MAPPER_AGREEMENT.md`). #6's nine "commonly confused" pairs (from its starter
  notebook's `HIGH_CONFUSION_PAIRS`) are regression tests.
