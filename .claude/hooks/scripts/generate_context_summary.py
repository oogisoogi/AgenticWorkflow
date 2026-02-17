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
    estimate_tokens,
    extract_session_facts,
    replace_or_append_session_facts,
    cleanup_session_archives,
    cleanup_knowledge_index,
    read_autopilot_state,
    E5_RICH_CONTENT_MARKER,
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

    # E5: Empty Snapshot Guard — don't overwrite good snapshot with empty one
    latest_path = os.path.join(snapshot_dir, "latest.md")
    new_tool_count = sum(1 for e in entries if e.get("type") == "tool_use")
    should_update_latest = True

    if os.path.exists(latest_path) and new_tool_count == 0:
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
            if E5_RICH_CONTENT_MARKER in existing_content:
                should_update_latest = False
        except Exception:
            pass

    if should_update_latest:
        atomic_write(latest_path, md_content)

    # Update offset tracker
    _write_offset(offset_file, current_size)

    # --- Knowledge Archive (Stop hook integration) ---
    sessions_dir = os.path.join(snapshot_dir, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    archive_name = f"{datetime.now().strftime('%Y-%m-%dT%H%M')}_{session_id[:8]}.md"
    archive_path = os.path.join(sessions_dir, archive_name)
    try:
        atomic_write(archive_path, md_content)
    except Exception:
        pass

    try:
        estimated_tokens, _ = estimate_tokens(transcript_path, entries)
        facts = extract_session_facts(
            session_id=session_id,
            trigger="stop",
            project_dir=project_dir,
            entries=entries,
            token_estimate=estimated_tokens,
        )
        ki_path = os.path.join(snapshot_dir, "knowledge-index.jsonl")
        replace_or_append_session_facts(ki_path, facts)
    except Exception:
        pass

    cleanup_session_archives(snapshot_dir)
    cleanup_knowledge_index(snapshot_dir)

    # --- Autopilot Decision Log (supplementary safety net) ---
    # Primary: Claude generates Decision Log during execution.
    # Secondary: This hook detects auto-approve patterns and creates logs if missing.
    try:
        _generate_decision_log_if_needed(project_dir, entries)
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


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Non-blocking: log error but don't crash
        print(f"generate_context_summary error: {e}", file=sys.stderr)
        sys.exit(0)
