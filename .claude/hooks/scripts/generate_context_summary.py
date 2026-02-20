#!/usr/bin/env python3
"""
Context Preservation System — generate_context_summary.py

Triggered by: Stop (every time Claude finishes a response)

v2 Design: COMPREHENSIVE full snapshot, not lightweight.
  - Quality First (절대 기준 1): Every save is comprehensive.
  - The Stop hook is the last automatic save point before /clear.
  - If SessionEnd fails, this is the safety net.

Incremental approach:
  - Tracks last save byte offset in .last_save_offset
  - Only processes new transcript entries since last save
  - Regenerates full MD from accumulated data
  - Updates latest.md atomically

Architecture:
  - Reuses save_context.py's core logic via _context_lib
  - SOT: Read-only
  - Writes: .claude/context-snapshots/ (snapshots, knowledge archive)
  - Writes: autopilot-logs/ (Decision Log safety net — only when autopilot active)
"""

import os
import re
import sys
import json
from datetime import datetime

# Add script directory to path for shared library import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _context_lib import (
    read_stdin_json,
    parse_transcript,
    capture_sot,
    load_work_log,
    generate_snapshot_md,
    atomic_write,
    cleanup_snapshots,
    should_skip_save,
    get_snapshot_dir,
    read_autopilot_state,
    update_latest_with_guard,
    archive_and_index_session,
)


def main():
    input_data = read_stdin_json()

    # Determine project directory
    project_dir = os.environ.get(
        "CLAUDE_PROJECT_DIR",
        input_data.get("cwd", os.getcwd()),
    )

    snapshot_dir = get_snapshot_dir(project_dir)
    os.makedirs(snapshot_dir, exist_ok=True)

    # Dedup guard — Stop hook uses 30s window to reduce noise
    if should_skip_save(snapshot_dir, trigger="stop"):
        sys.exit(0)

    # Parse transcript
    transcript_path = input_data.get("transcript_path", "")
    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)  # No transcript to process

    # Check if transcript has grown since last save (incremental check)
    offset_file = os.path.join(snapshot_dir, ".last_save_offset")
    current_size = os.path.getsize(transcript_path)
    last_size = _read_offset(offset_file)

    # Only save if transcript has grown by at least 5KB since last save
    # (5KB threshold ensures meaningful changes only — reduces noise)
    if last_size > 0 and (current_size - last_size) < 5120:
        sys.exit(0)

    # Full transcript parse (comprehensive — 절대 기준 1)
    entries = parse_transcript(transcript_path)

    if not entries:
        sys.exit(0)

    # Load accumulated work log
    work_log = load_work_log(snapshot_dir)

    # Capture SOT state (read-only)
    sot_content = capture_sot(project_dir)

    # Generate comprehensive MD snapshot
    session_id = input_data.get("session_id", "unknown")
    md_content = generate_snapshot_md(
        session_id=session_id,
        trigger="stop",
        project_dir=project_dir,
        entries=entries,
        work_log=work_log,
        sot_content=sot_content,
    )

    # Atomic write: timestamped snapshot
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_stop.md"
    filepath = os.path.join(snapshot_dir, filename)
    atomic_write(filepath, md_content)

    # E5: Empty Snapshot Guard — update latest.md with rich content protection
    update_latest_with_guard(snapshot_dir, md_content, entries)

    # Update offset tracker
    _write_offset(offset_file, current_size)

    # Knowledge Archive: archive + index + cleanup (consolidated)
    archive_and_index_session(
        snapshot_dir, md_content, session_id, "stop",
        project_dir, entries, transcript_path,
    )

    # --- Autopilot Decision Log (supplementary safety net) ---
    # Primary: Claude generates Decision Log during execution.
    # Secondary: This hook detects auto-approve patterns and creates logs if missing.
    try:
        _generate_decision_log_if_needed(project_dir, entries)
    except Exception:
        pass  # Non-blocking — never fail the hook

    # --- Adversarial Review safety net ---
    # Detect steps with pACS logs but missing review reports.
    # Non-blocking: only logs warning, does not fail the hook.
    try:
        _check_missing_reviews(project_dir)
    except Exception:
        pass  # Non-blocking — never fail the hook

    # --- Translation safety net ---
    # Detect steps with translation pACS logs but missing translation files.
    # Non-blocking: only logs warning, does not fail the hook.
    try:
        _check_missing_translations(project_dir)
    except Exception:
        pass  # Non-blocking — never fail the hook

    # Cleanup old snapshots
    cleanup_snapshots(snapshot_dir)


def _read_offset(offset_file):
    """Read last saved transcript byte offset."""
    try:
        if os.path.exists(offset_file):
            with open(offset_file, "r") as f:
                return int(f.read().strip())
    except (ValueError, IOError):
        pass
    return 0


def _write_offset(offset_file, size):
    """Write current transcript byte offset."""
    try:
        with open(offset_file, "w") as f:
            f.write(str(size))
    except IOError:
        pass


def _generate_decision_log_if_needed(project_dir, entries):
    """Detect auto-approved (human) steps and generate Decision Logs if missing.

    This is a SUPPLEMENTARY safety net. Claude itself should generate
    Decision Logs as primary. This hook catches any that were missed.

    P1 Compliance: Pattern detection is regex-based (deterministic).
    SOT Compliance: Only writes to autopilot-logs/ (not SOT).
    """
    import re

    ap_state = read_autopilot_state(project_dir)
    if not ap_state:
        return  # Autopilot not active — nothing to do

    # Search assistant texts for auto-approve patterns
    AUTO_APPROVE_PATTERNS = [
        re.compile(r'autopilot.*auto[\s-]?approv', re.IGNORECASE),
        re.compile(r'자동\s*승인', re.IGNORECASE),
        re.compile(r'\(human\).*단계.*자동', re.IGNORECASE),
        re.compile(r'auto[\s-]?approve.*step\s*(\d+)', re.IGNORECASE),
        re.compile(r'step[\s-]*(\d+).*auto[\s-]?approv', re.IGNORECASE),
        re.compile(r'autopilot-logs/step-(\d+)', re.IGNORECASE),
    ]

    assistant_texts = [
        e for e in entries
        if e.get("type") == "assistant_text"
    ]

    detected_steps = set()
    for text_entry in assistant_texts:
        content = text_entry.get("content", "")
        for pattern in AUTO_APPROVE_PATTERNS:
            matches = pattern.findall(content)
            for match in matches:
                if isinstance(match, str) and match.isdigit():
                    detected_steps.add(int(match))

        # Also detect "step N" near auto-approve context
        if any(p.search(content) for p in AUTO_APPROVE_PATTERNS[:3]):
            step_nums = re.findall(r'step[\s-]*(\d+)', content, re.IGNORECASE)
            for sn in step_nums:
                detected_steps.add(int(sn))

    if not detected_steps:
        return

    # Create autopilot-logs directory
    logs_dir = os.path.join(project_dir, "autopilot-logs")
    os.makedirs(logs_dir, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for step_num in sorted(detected_steps):
        log_path = os.path.join(logs_dir, f"step-{step_num}-decision.md")
        if os.path.exists(log_path):
            continue  # Already exists — don't overwrite (Claude's version is primary)

        log_content = (
            f"# Decision Log — Step {step_num}\n\n"
            f"- **Step**: {step_num}\n"
            f"- **Checkpoint Type**: (human) — auto-approved\n"
            f"- **Decision**: Auto-approved (Autopilot mode)\n"
            f"- **Rationale**: Quality-maximizing default (절대 기준 1)\n"
            f"- **Timestamp**: {now}\n"
            f"- **Source**: Hook safety net (generate_context_summary.py)\n"
            f"\n"
            f"> Note: This log was generated by the Stop hook as a safety net.\n"
            f"> Claude's own Decision Log (if generated) takes precedence.\n"
        )
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(log_content)
        except Exception:
            pass  # Non-blocking


def _check_missing_reviews(project_dir):
    """Detect steps with pACS logs but no corresponding review reports.

    Safety net: If a step has pacs-logs/step-N-pacs.md but no
    review-logs/step-N-review.md, log a warning to stderr.
    This catches cases where the Adversarial Review was skipped
    for a step that has Review: specified in the workflow.

    P1 Compliance: File existence check (deterministic).
    SOT Compliance: Read-only.
    Non-blocking: Only logs to stderr, never fails.
    """
    pacs_dir = os.path.join(project_dir, "pacs-logs")
    review_dir = os.path.join(project_dir, "review-logs")

    if not os.path.isdir(pacs_dir):
        return

    step_pattern = re.compile(r"^step-(\d+)-pacs\.md$")

    for fname in os.listdir(pacs_dir):
        match = step_pattern.match(fname)
        if not match:
            continue
        step_num = match.group(1)
        review_file = os.path.join(review_dir, f"step-{step_num}-review.md")
        if not os.path.exists(review_file):
            print(
                f"[Review Safety Net] Step {step_num}: pACS log exists but "
                f"no review report found at review-logs/step-{step_num}-review.md",
                file=sys.stderr,
            )


def _check_missing_translations(project_dir):
    """Detect steps with translation pACS logs but no translation files.

    Safety net: If a step has pacs-logs/step-N-translation-pacs.md but no
    corresponding .ko.md file, log a warning to stderr.
    This catches cases where the Translation was started (pACS scored)
    but the output file is missing.

    P1 Compliance: File existence check (deterministic).
    SOT Compliance: Read-only.
    Non-blocking: Only logs to stderr, never fails.
    """
    pacs_dir = os.path.join(project_dir, "pacs-logs")
    translations_dir = os.path.join(project_dir, "translations")

    if not os.path.isdir(pacs_dir):
        return

    step_pattern = re.compile(r"^step-(\d+)-translation-pacs\.md$")

    for fname in os.listdir(pacs_dir):
        match = step_pattern.match(fname)
        if not match:
            continue
        step_num = match.group(1)

        # Check 3 possible locations for translation files
        found = False

        # Location 1: translations/step-N*.ko.md
        if os.path.isdir(translations_dir):
            try:
                for tf in os.listdir(translations_dir):
                    if tf.startswith(f"step-{step_num}") and tf.endswith(".ko.md"):
                        found = True
                        break
            except OSError:
                pass

        # Location 2: Any .ko.md in project (check SOT outputs)
        if not found:
            try:
                from _context_lib import _find_translation_files_for_step
                files = _find_translation_files_for_step(project_dir, int(step_num))
                if files:
                    found = True
            except Exception:
                pass  # Graceful fallback — already checked translations/ dir

        if not found:
            print(
                f"[Translation Safety Net] Step {step_num}: translation pACS log "
                f"exists but no .ko.md file found",
                file=sys.stderr,
            )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Non-blocking: log error but don't crash
        print(f"generate_context_summary error: {e}", file=sys.stderr)
        sys.exit(0)
