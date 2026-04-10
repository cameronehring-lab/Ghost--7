# RRD2 Backlog Import Files

Generated: 2026-03-10

## Files
- `RRD2_EPICS.csv`: create epics first (or map to existing epics).
- `RRD2_BACKLOG_IMPORT_JIRA.csv`: Jira-friendly issue import sheet.
- `RRD2_BACKLOG_IMPORT_LINEAR.csv`: Linear-friendly issue import sheet.
- `RRD2_BACKLOG_IMPORT_NORMALIZED.csv`: canonical normalized sheet for custom mapping.

## Suggested import order
1. Import `RRD2_EPICS.csv` (or create epics manually).
2. Import issues CSV for your tracker.
3. Map `Epic Link`/`Parent Epic` to existing epic keys/names if your tracker requires internal IDs.

## Field notes
- Dependencies are stored as ticket IDs in the `Dependencies` field.
- Multi-line details are embedded in `Description` for Jira and `Description` for Linear.
- Priority values are textual (`Highest`, `High`, `Medium`) and may need mapping per workspace settings.
