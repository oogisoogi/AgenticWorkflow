#!/usr/bin/env python3
"""
Context Preservation System — save_context.py

Triggered by:
  - SessionEnd (reason: "clear")  → /clear 직전 최종 저장 (E1: Dedup 면제)
  - PreCompact (auto|manual)      → 자동 압축 직전 저장
  - threshold (token 75%+)        → update_work_log.py에서 호출

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
  - Knowledge Archive: archives to sessions/, appends to knowledge-index.jsonl
  - Rotation: cleanup_session_archives + cleanup_knowledge_index
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
    replace_or_append_session_facts,
    cleanup_snapshots,
    should_skip_save,
    get_snapshot_dir,
    estimate_tokens,
    extract_session_facts,
    cleanup_knowledge_index,
    cleanup_session_archives,
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
    # E1: SessionEnd is exempt (user's explicit /clear action)
    if should_skip_save(snapshot_dir, trigger=trigger):
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

    # E5: Empty Snapshot Guard — don't overwrite good snapshot with empty one
    # If new snapshot has 0 tool_use entries and existing has content, protect it
    latest_path = os.path.join(snapshot_dir, "latest.md")
    new_tool_count = sum(1 for e in entries if e.get("type") == "tool_use")
    should_update_latest = True

    if os.path.exists(latest_path) and new_tool_count == 0:
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
            if "### 수정 중이던 파일" in existing_content:
                should_update_latest = False
        except Exception:
            pass

    if should_update_latest:
        atomic_write(latest_path, md_content)

    # Cleanup old snapshots (keep per-trigger limits)
    cleanup_snapshots(snapshot_dir)

    # --- Knowledge Archive (Area 1: Cross-Session) ---
    # Archive snapshot to sessions/ directory
    sessions_dir = os.path.join(snapshot_dir, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    archive_name = f"{datetime.now().strftime('%Y-%m-%dT%H%M')}_{session_id[:8]}.md"
    archive_path = os.path.join(sessions_dir, archive_name)
    try:
        atomic_write(archive_path, md_content)
    except Exception:
        pass  # Non-blocking

    # Extract session facts and append to knowledge-index.jsonl
    try:
        estimated_tokens, _ = estimate_tokens(transcript_path, entries)
        facts = extract_session_facts(
            session_id=session_id,
            trigger=trigger,
            project_dir=project_dir,
            entries=entries,
            token_estimate=estimated_tokens,
        )
        ki_path = os.path.join(snapshot_dir, "knowledge-index.jsonl")
        replace_or_append_session_facts(ki_path, facts)
    except Exception:
        pass  # Non-blocking

    # Cleanup archives and knowledge index (rotation)
    cleanup_session_archives(snapshot_dir)
    cleanup_knowledge_index(snapshot_dir)

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
