#!/usr/bin/env python3
"""
Context Preservation System — save_context.py

Triggered by:
  - SessionEnd (reason: "clear")  → /clear 직전 최종 저장
  - PreCompact (auto|manual)      → 자동 압축 직전 저장
  - update_work_log.py            → 75% 임계치 선제 저장

This is the core save engine. Generates comprehensive MD snapshots
following the RLM pattern (external memory objects on disk).

Usage:
  echo '{"session_id":"...","transcript_path":"..."}' | python3 save_context.py --trigger sessionend
  echo '{"session_id":"...","transcript_path":"..."}' | python3 save_context.py --trigger precompact
  echo '{"session_id":"...","transcript_path":"..."}' | python3 save_context.py --trigger threshold

Architecture:
  - SOT: Read-only (captures state.yaml, never modifies)
  - Writes: Only to .claude/context-snapshots/
  - Dedup: Skips if latest.md was updated < 10 seconds ago
  - Atomic: temp file → rename
"""

import os
import sys
import json
import fcntl
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
)


def main():
    # Parse trigger from CLI args
    trigger = "unknown"
    for i, arg in enumerate(sys.argv):
        if arg == "--trigger" and i + 1 < len(sys.argv):
            trigger = sys.argv[i + 1]

    # Read hook input from stdin
    input_data = read_stdin_json()

    # Determine project directory
    project_dir = os.environ.get(
        "CLAUDE_PROJECT_DIR",
        input_data.get("cwd", os.getcwd()),
    )

    # Setup snapshot directory
    snapshot_dir = get_snapshot_dir(project_dir)
    os.makedirs(snapshot_dir, exist_ok=True)

    # Dedup guard — skip if saved within last 10 seconds
    if should_skip_save(snapshot_dir):
        sys.exit(0)

    # Parse transcript
    transcript_path = input_data.get("transcript_path", "")
    entries = parse_transcript(transcript_path)

    # Load accumulated work log
    work_log = load_work_log(snapshot_dir)

    # Capture SOT state (read-only)
    sot_content = capture_sot(project_dir)

    # Generate comprehensive MD snapshot
    session_id = input_data.get("session_id", "unknown")
    md_content = generate_snapshot_md(
        session_id=session_id,
        trigger=trigger,
        project_dir=project_dir,
        entries=entries,
        work_log=work_log,
        sot_content=sot_content,
    )

    # Atomic write: timestamped snapshot
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{trigger}.md"
    filepath = os.path.join(snapshot_dir, filename)
    atomic_write(filepath, md_content)

    # Update latest.md (always points to most recent comprehensive snapshot)
    latest_path = os.path.join(snapshot_dir, "latest.md")
    atomic_write(latest_path, md_content)

    # Cleanup old snapshots (keep per-trigger limits)
    cleanup_snapshots(snapshot_dir)

    # Reset work log after successful full save (with lock to prevent race condition)
    work_log_path = os.path.join(snapshot_dir, "work_log.jsonl")
    if os.path.exists(work_log_path):
        try:
            with open(work_log_path, "r+", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.truncate(0)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (OSError, IOError):
            pass

    # Output confirmation (captured by hook system)
    print(f"Context saved: {filepath}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Non-blocking: log error but don't crash the hook
        print(f"save_context error: {e}", file=sys.stderr)
        sys.exit(0)  # Exit 0 to not block Claude
