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
  - Writes: Only to .claude/context-snapshots/
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

    # Dedup guard — skip if saved within last 10 seconds
    if should_skip_save(snapshot_dir):
        sys.exit(0)

    # Check if this is a stop_hook_active scenario (already triggered once)
    if input_data.get("stop_hook_active", False):
        sys.exit(0)  # Don't re-save on hook-triggered continuation

    # Parse transcript
    transcript_path = input_data.get("transcript_path", "")
    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)  # No transcript to process

    # Check if transcript has grown since last save (incremental check)
    offset_file = os.path.join(snapshot_dir, ".last_save_offset")
    current_size = os.path.getsize(transcript_path)
    last_size = _read_offset(offset_file)

    # Only save if transcript has grown by at least 1KB since last save
    if last_size > 0 and (current_size - last_size) < 1024:
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

    # Update latest.md
    latest_path = os.path.join(snapshot_dir, "latest.md")
    atomic_write(latest_path, md_content)

    # Update offset tracker
    _write_offset(offset_file, current_size)

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


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Non-blocking: log error but don't crash
        print(f"generate_context_summary error: {e}", file=sys.stderr)
        sys.exit(0)
