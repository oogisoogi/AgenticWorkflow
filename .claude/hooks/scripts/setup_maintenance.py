#!/usr/bin/env python3
"""
AgenticWorkflow Setup Maintenance Hook — Deterministic Health Check

Triggered by: claude --maintenance
Location: .claude/settings.json (Project)

SOT Compliance: NO ACCESS to SOT (state.yaml).
  Maintenance operates on Context Preservation System artifacts only.

Design Principle: This script REPORTS but does NOT DELETE.
  Deletion decisions are made by the /maintenance slash command
  with user confirmation via the agent.

Quality Impact Path (절대 기준 1):
  Periodic health checks → data integrity maintenance →
  Knowledge Archive reliability → session recovery quality →
  long-term workflow continuity
"""

import ast
import json
import os
import sys
import time
from datetime import datetime


# =============================================================================
# Constants
# =============================================================================

# Age threshold for session archive staleness (30 days)
STALE_ARCHIVE_DAYS = 30
STALE_ARCHIVE_SECONDS = STALE_ARCHIVE_DAYS * 24 * 3600

# work_log.jsonl size warning threshold (1MB)
WORK_LOG_SIZE_WARN = 1_000_000

# Hook scripts to re-validate (17 scripts)
# D-7: Intentionally duplicated in setup_init.py — setup scripts are
# independent from _context_lib.py by design (no import dependency).
REQUIRED_SCRIPTS = [
    "_context_lib.py",
    "block_destructive_commands.py",
    "block_test_file_edit.py",
    "context_guard.py",
    "generate_context_summary.py",
    "predictive_debug_guard.py",
    "restore_context.py",
    "save_context.py",
    "update_work_log.py",
    "validate_domain_knowledge.py",
    "validate_pacs.py",
    "validate_retry_budget.py",
    "validate_review.py",
    "validate_traceability.py",
    "validate_translation.py",
    "validate_verification.py",
    "validate_workflow.py",
]

# Severity levels
WARNING = "WARNING"
INFO = "INFO"


# =============================================================================
# Main
# =============================================================================

def main():
    """Run all maintenance checks."""
    input_data = _read_stdin_json()
    project_dir = os.environ.get(
        "CLAUDE_PROJECT_DIR",
        input_data.get("cwd", os.getcwd()),
    )

    results = []

    # 1. Stale session archives (report only — no deletion)
    results.append(_check_stale_archives(project_dir))

    # 2. knowledge-index.jsonl integrity
    results.append(_check_knowledge_index(project_dir))

    # 3. work_log.jsonl size
    results.append(_check_work_log_size(project_dir))

    # 4. Hook scripts syntax re-validation
    scripts_dir = os.path.join(project_dir, ".claude", "hooks", "scripts")
    for script_name in REQUIRED_SCRIPTS:
        results.append(_check_script_syntax(scripts_dir, script_name))

    # Write log file
    log_path = os.path.join(
        project_dir, ".claude", "hooks", "setup.maintenance.log"
    )
    _write_log(log_path, results)

    # Build summary
    issues = sum(1 for r in results if r["status"] != "PASS")
    summary = f"Maintenance check: {len(results) - issues}/{len(results)} healthy"
    if issues > 0:
        summary += f" ({issues} issue(s) found — see /maintenance for details)"

    # Output structured JSON for Claude Code
    output = {
        "hookSpecificOutput": {
            "hookEventName": "Setup",
            "additionalContext": summary,
        }
    }
    print(json.dumps(output))

    # Maintenance never blocks the session (always exit 0)
    # Issues are informational, not blocking
    sys.exit(0)


# =============================================================================
# Maintenance Checks
# =============================================================================

def _check_stale_archives(project_dir):
    """List session archives older than 30 days.

    Does NOT delete — reports only. Deletion is performed by /maintenance
    slash command with user confirmation.
    """
    sessions_dir = os.path.join(
        project_dir, ".claude", "context-snapshots", "sessions"
    )

    if not os.path.isdir(sessions_dir):
        return _result(
            INFO, "PASS", "Session archives",
            "sessions/ directory not found (OK — no archives yet)",
        )

    now = time.time()
    stale_files = []
    total_files = 0
    total_size = 0

    try:
        for fname in sorted(os.listdir(sessions_dir)):
            if not fname.endswith(".md"):
                continue
            total_files += 1
            fpath = os.path.join(sessions_dir, fname)
            fsize = os.path.getsize(fpath)
            total_size += fsize
            age_seconds = now - os.path.getmtime(fpath)
            if age_seconds > STALE_ARCHIVE_SECONDS:
                age_days = int(age_seconds / 86400)
                stale_files.append((fname, age_days, fsize))
    except Exception as e:
        return _result(WARNING, "FAIL", "Session archives", f"cannot scan: {e}")

    if stale_files:
        stale_size = sum(f[2] for f in stale_files)
        names = ", ".join(
            f"{f[0]} ({f[1]}d)" for f in stale_files[:5]
        )
        extra = f" +{len(stale_files) - 5} more" if len(stale_files) > 5 else ""
        return _result(
            WARNING, "WARN", "Session archives",
            f"{len(stale_files)}/{total_files} archives older than {STALE_ARCHIVE_DAYS} days "
            f"({stale_size / 1024:.0f}KB reclaimable): {names}{extra}",
        )

    size_kb = total_size / 1024
    return _result(
        INFO, "PASS", "Session archives",
        f"{total_files} archives ({size_kb:.0f}KB), all within {STALE_ARCHIVE_DAYS} days",
    )


def _check_knowledge_index(project_dir):
    """Validate knowledge-index.jsonl — each line must be valid JSON.

    knowledge-index.jsonl is the RLM Knowledge Archive.
    Invalid entries degrade cross-session knowledge retrieval.
    """
    ki_path = os.path.join(
        project_dir, ".claude", "context-snapshots", "knowledge-index.jsonl"
    )

    if not os.path.exists(ki_path):
        return _result(
            INFO, "PASS", "Knowledge index",
            "file not found (OK — no sessions archived yet)",
        )

    total_lines = 0
    invalid_lines = []

    try:
        with open(ki_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                total_lines += 1
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    invalid_lines.append(line_num)
    except Exception as e:
        return _result(WARNING, "FAIL", "Knowledge index", f"cannot read: {e}")

    if invalid_lines:
        line_refs = ", ".join(str(n) for n in invalid_lines[:10])
        extra = f" +{len(invalid_lines) - 10} more" if len(invalid_lines) > 10 else ""
        return _result(
            WARNING, "WARN", "Knowledge index",
            f"{len(invalid_lines)}/{total_lines} lines have invalid JSON "
            f"(lines: {line_refs}{extra})",
        )

    size_kb = os.path.getsize(ki_path) / 1024
    return _result(
        INFO, "PASS", "Knowledge index",
        f"{total_lines} entries ({size_kb:.0f}KB), all valid JSON",
    )


def _check_work_log_size(project_dir):
    """Check work_log.jsonl size — warn if exceeds threshold."""
    log_path = os.path.join(
        project_dir, ".claude", "context-snapshots", "work_log.jsonl"
    )

    if not os.path.exists(log_path):
        return _result(INFO, "PASS", "Work log", "file not found (OK)")

    try:
        size = os.path.getsize(log_path)
        size_kb = size / 1024

        if size > WORK_LOG_SIZE_WARN:
            return _result(
                WARNING, "WARN", "Work log",
                f"{size_kb:.0f}KB — exceeds 1MB threshold. Consider cleanup.",
            )

        return _result(INFO, "PASS", "Work log", f"{size_kb:.0f}KB")
    except Exception as e:
        return _result(WARNING, "FAIL", "Work log", f"cannot check: {e}")


def _check_script_syntax(scripts_dir, script_name):
    """Re-validate hook script Python syntax."""
    script_path = os.path.join(scripts_dir, script_name)

    if not os.path.exists(script_path):
        return _result(
            WARNING, "FAIL", f"Script: {script_name}", "not found"
        )

    try:
        with open(script_path, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source, filename=script_name)
        return _result(
            INFO, "PASS", f"Script: {script_name}", "syntax valid"
        )
    except SyntaxError as e:
        return _result(
            WARNING, "FAIL", f"Script: {script_name}",
            f"syntax error at line {e.lineno}: {e.msg}",
        )
    except Exception as e:
        return _result(
            WARNING, "FAIL", f"Script: {script_name}",
            f"cannot read: {e}",
        )


# =============================================================================
# Helpers
# =============================================================================

def _result(severity, status, check, message):
    """Create a structured check result."""
    return {
        "severity": severity,
        "status": status,
        "check": check,
        "message": message,
    }


def _read_stdin_json():
    """Read JSON from stdin (Claude Code hook protocol)."""
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, Exception):
        return {}


def _write_log(log_path, results):
    """Write maintenance results to log file.

    Log format is human-readable and machine-parseable by /maintenance command.
    """
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        timestamp = datetime.now().isoformat()
        lines = [
            "# AgenticWorkflow Setup Maintenance Log",
            f"# Timestamp: {timestamp}",
            f"# Python: {sys.version.split()[0]}",
            "",
        ]

        for r in results:
            if r["status"] == "PASS":
                marker = "PASS"
            elif r["status"] == "WARN":
                marker = "WARN"
            else:
                marker = "FAIL"
            lines.append(
                f"[{r['severity']}] [{marker}] {r['check']}: {r['message']}"
            )

        lines.append("")

        # Summary
        pass_count = sum(1 for r in results if r["status"] == "PASS")
        issue_count = sum(1 for r in results if r["status"] != "PASS")
        lines.append(
            f"# Summary: {pass_count} healthy, {issue_count} issues, "
            f"{len(results)} total"
        )
        lines.append("")

        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass  # Log write failure is non-blocking


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Setup maintenance error: {e}", file=sys.stderr)
        sys.exit(0)  # Maintenance never blocks
