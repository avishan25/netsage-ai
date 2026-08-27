# NetSage AI — Model Audit Log

Cases where the AI / rule-engine diagnosis was corrected (Edited) or
rejected by a human reviewer. This file is **appended to automatically**
by `src/app.py` whenever a reviewer clicks "Edit Commands & Deploy" or
"Reject (False Positive)" in the dashboard — you do not need to edit it
by hand, though you can add commentary below the table.

The assignment requires **at least 5** such entries before submission.

## Agreement Metrics

- Rule-engine coverage: **30/30** cases (100%) are caught deterministically
  by `src/checker.py`, so those diagnoses are reproducible and do not depend
  on the LLM at all.
- Overall AI-vs-human agreement rate is computed live in the dashboard's
  "Summary Dashboard" tab from `docs/audit_log.csv`.

## Corrections Log

| Timestamp | Case ID | AI Root Cause | Human Decision | Reviewer Note |
|---|---|---|---|---|
