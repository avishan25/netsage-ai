"""
engine.py — NetSage AI Orchestrator
-------------------------------------
Implements the flow from the System Flowchart:

    Run Deterministic Rule Checker (checker.py)
        -> Errors detected?  -> Yes: Flag + format JSON directly (fast, free, deterministic)
                              -> No:  Pass to Prompt Engine for LLM Inference
    -> Format Structured JSON Diagnostic Output
    -> Return to caller (src/app.py) for Human-in-the-Loop review

This module never auto-executes a fix. It only ever returns a diagnosis
dict for a human to review in the dashboard.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, Any

from checker import run_checker

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = BASE_DIR / "prompts" / "diagnose_prompt.md"

# Load ANTHROPIC_API_KEY from a .env file in the project root, if present.
# This means you don't have to set the environment variable by hand every
# time you open a new terminal — just create a ".env" file (see .env.example).
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass  # python-dotenv not installed yet — env var can still be set manually


def _extract_system_prompt(prompt_md: str) -> str:
    """The diagnose_prompt.md file is human-readable Markdown. We send the
    whole file as the system prompt — Claude reads the schema, hard rules,
    and few-shot examples directly out of the Markdown."""
    return prompt_md


def _build_user_message(case: Dict[str, str]) -> str:
    return (
        f"Symptom: {case.get('symptom', '')}\n"
        f"Topology note: {case.get('topology_note', '')}\n"
        f"show_outputs:\n{case.get('show_outputs', '')}\n\n"
        f"Return only the JSON diagnostic object."
    )


def _parse_llm_json(text: str) -> Dict[str, Any]:
    """LLMs sometimes wrap JSON in markdown fences despite instructions.
    Strip those defensively before parsing."""
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def diagnose_with_llm(case: Dict[str, str]) -> Dict[str, Any]:
    """
    Calls the Anthropic API for cases the deterministic checker could not
    classify. Requires the ANTHROPIC_API_KEY environment variable.

    If no API key is configured, returns a clearly-labeled placeholder so
    the dashboard still works end-to-end in demo/offline mode.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "root_cause": "LLM diagnosis unavailable (no ANTHROPIC_API_KEY set)",
            "osi_layer": "Unknown",
            "confidence": 0.0,
            "evidence": case.get("show_outputs", ""),
            "next_command": "N/A",
            "fix_steps": ["Set the ANTHROPIC_API_KEY environment variable to enable LLM diagnosis."],
            "source": "llm_unavailable",
        }

    try:
        import anthropic
    except ImportError:
        return {
            "root_cause": "LLM diagnosis unavailable (anthropic package not installed)",
            "osi_layer": "Unknown",
            "confidence": 0.0,
            "evidence": case.get("show_outputs", ""),
            "next_command": "N/A",
            "fix_steps": ["Run: pip install anthropic"],
            "source": "llm_unavailable",
        }

    system_prompt = _extract_system_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
    user_message = _build_user_message(case)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")

    try:
        diagnosis = _parse_llm_json(text)
    except (json.JSONDecodeError, AttributeError):
        diagnosis = {
            "root_cause": "LLM returned unparseable output — manual review required",
            "osi_layer": "Unknown",
            "confidence": 0.0,
            "evidence": text[:300],
            "next_command": "N/A",
            "fix_steps": [],
        }

    diagnosis["source"] = "llm"
    return diagnosis


def diagnose(case: Dict[str, str], use_llm: bool = True) -> Dict[str, Any]:
    """
    Main entry point used by src/app.py.

    Runs the deterministic checker AND the LLM (if use_llm=True and an API
    key is configured), so you get two independent diagnoses to compare —
    this matches the assignment requirement to "Feed each case to the AI
    assistant... and compare it with the known correct answer".

    Returns:
        {
          "status": "ERRORS_DETECTED" | "NO_MATCH",
          "rule_diagnosis": {...} | None,
          "llm_diagnosis": {...} | None,
          "diagnosis": <the rule diagnosis if available, else the LLM one —
                        kept for backward compatibility with older code>
        }
    """
    checker_result = run_checker(case.get("show_outputs", ""))
    rule_diagnosis = checker_result["diagnosis"] if checker_result["status"] == "ERRORS_DETECTED" else None

    llm_diagnosis = None
    if use_llm:
        llm_diagnosis = diagnose_with_llm(case)

    primary = rule_diagnosis if rule_diagnosis is not None else llm_diagnosis

    return {
        "status": checker_result["status"],
        "rule_diagnosis": rule_diagnosis,
        "llm_diagnosis": llm_diagnosis,
        "diagnosis": primary,
    }


if __name__ == "__main__":
    # Simple manual smoke test
    sample_case = {
        "symptom": "PC1 cannot reach Server1 in VLAN 30",
        "topology_note": "PC1 on Fa0/1 (VLAN 10); Gateway on Router Sub-interface Gi0/0.10",
        "show_outputs": "GigabitEthernet0/0.10 is up, line protocol is up\n"
                         "GigabitEthernet0/0.30 is administratively down line protocol is down",
    }
    result = diagnose(sample_case)
    print(json.dumps(result, indent=2))
