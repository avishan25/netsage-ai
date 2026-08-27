# NetSage AI — Automated Network Diagnostic Platform

This is a working starter build of the project described in your
**Problem Statement** and **Technical Documentation**. It follows the exact
4-tier architecture from the docs:

```
data/        -> cases.csv (your 30 cases) + system_config.json
prompts/     -> diagnose_prompt.md (LLM instructions + JSON schema + few-shot examples)
src/         -> checker.py (rule engine) + engine.py (orchestrator) + app.py (dashboard)
docs/        -> model_audit_log.md (Responsible AI log) + audit_log.csv (auto-generated)
```

**You do not need to know how to code to run this.** Follow the steps below
exactly, in order.

---

## 1. Install prerequisites (one-time setup)

1. Install **Python 3.10+**: https://www.python.org/downloads/
   - On Windows, tick "Add Python to PATH" during install.
2. Open a terminal (Command Prompt / PowerShell / macOS Terminal) inside
   this project folder (`netsage-ai/`).
3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

## 2. Run the dashboard

```
streamlit run src/app.py
```

This opens a browser tab at `http://localhost:8501`. That's your
"Streamlit Operations Dashboard" from the architecture diagram.

## 3. Use it (this is your demo workflow)

1. **Diagnose a Case tab** → pick a case (e.g. `NET-001`) from the dropdown.
   You'll see the symptom, topology note, and raw `show` command output.
2. Click  Run Diagnosis. The system:
   - First runs `checker.py` (deterministic regex rules). All 30 of your
     current cases are matched here — instant, free, 100% reproducible.
   - If a *new* case you add isn't matched by any rule, it automatically
     falls back to an LLM call (see step 4 for enabling that).
3. Review the **root cause, OSI layer, confidence, evidence, next command,
   and fix steps**. You can edit the fix steps text box before deciding.
4. Click one of:
   - Approve & Deploy** — you agree with the diagnosis as-is.
   - Edit Commands & Deploy** — you agree with the root cause but
     changed something in the fix steps. Add a reviewer note explaining why.
   - Reject (False Positive)** — the diagnosis was wrong. Add a note.
5. Every decision is logged to `docs/audit_log.csv`. Edited/Rejected
   decisions are also appended to `docs/model_audit_log.md` automatically —
   **that's your "Responsible AI log"**. Do this for at least 5 different
   cases (mix of Approve/Edit/Reject) to satisfy that requirement.
6. **Summary Dashboard tab** — shows case counts by concept/severity and the
   live AI-vs-human agreement rate, built from your audit log.
7. **Audit Log tab** — full table of every decision, downloadable as CSV,
   plus the rendered Responsible AI log.

## 4. Enable real AI (LLM) diagnosis

The dashboard runs **both** the rule engine and the AI on every case, side
by side, so you can compare them (this is required by the assignment: "Run
AI diagnosis: Feed each case to the AI assistant... compare it with the
known correct answer"). Without an API key, the AI side just shows a
placeholder message and the rule engine still works fine on its own — but
to get a real AI diagnosis, set up a key:

1. Get a free/paid API key at https://console.anthropic.com/settings/keys
2. In the project folder, copy `.env.example` to a new file named `.env`:
   ```
   copy .env.example .env        (Windows)
   cp .env.example .env          (macOS/Linux)
   ```
3. Open `.env` in VS Code and replace `your-key-here` with your real key:
   ```
   ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
   ```
4. Save the file, then restart the app:
   ```
   streamlit run src/app.py
   ```

**Never commit or share your `.env` file** — it contains your private key.
The `.env.example` file is safe to share; `.env` is not.

In the dashboard, there's a checkbox "🤖 Also run AI (LLM) diagnosis" above
the Run Diagnosis button — untick it if you only want the rule engine (e.g.
to save API cost while testing).

## 5. Mapping to your deliverables checklist

| Deliverable | Where it is |
|---|---|
| `cases.csv` (≥30 cases) | `data/cases.csv` — already has all 30 |
| Prompt files | `prompts/diagnose_prompt.md` |
| Python checker | `src/checker.py` (run `python src/checker.py` for a self-test) |
| Dashboard | `src/app.py` — run with `streamlit run src/app.py` |
| Responsible AI log (≥5 corrected cases) | `docs/model_audit_log.md`, auto-built as you review cases in the dashboard |
| Demo video (5–10 min) | Screen-record yourself doing steps 3.1–3.5 above on 2–3 different cases (one Approve, one Edit, one Reject) |

## 6. Extending the project (optional, for extra credit / depth)

- **Add more cases:** append rows to `data/cases.csv` with the same 8
  columns. If `checker.py` doesn't recognize the new `show_outputs` pattern,
  it'll fall through to the LLM automatically — no code changes needed.
- **Add new deterministic rules:** open `src/checker.py`, look at the
  `RULES` list, and add a new `(name, regex, _rule(...))` tuple following
  the existing pattern.
- **Improve the prompt:** edit `prompts/diagnose_prompt.md` — add more
  few-shot examples for fault types your rule engine doesn't cover yet.

## 7. Troubleshooting

- **"streamlit: command not found"** → re-run `pip install -r requirements.txt`,
  make sure you're in the same terminal/folder.
- **Port already in use** → run `streamlit run src/app.py --server.port 8502`.
- **Blank dashboard / errors about missing file** → make sure you run the
  `streamlit` command from inside the `netsage-ai/` folder (the one
  containing `src/`, `data/`, `docs/`, `prompts/`).
