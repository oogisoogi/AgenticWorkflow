#!/usr/bin/env python3
"""
Context Preservation System — restore_context.py

Triggered by: SessionStart (all sources: clear, compact, resume, startup)

RLM Pattern Implementation:
  - Outputs a POINTER to the full snapshot file + brief summary
  - Does NOT inject the full snapshot content into stdout
  - Claude uses Read tool to load the external file when needed
  - This treats the snapshot as an "external environment object" (RLM)
  - Knowledge Archive: includes pointers to knowledge-index.jsonl and sessions/
  - Claude can Grep knowledge-index.jsonl for programmatic probing (RLM pattern)

Output (stdout, exit 0):
  [CONTEXT RECOVERY]
  pointer to .claude/context-snapshots/latest.md
  + brief summary (≤500 chars)
  + knowledge archive pointers (if available)

SOT Compliance:
  - Read-only: reads latest.md and state.yaml, never modifies
  - Verifies SOT consistency between snapshot and current state
"""

import os
import sys
import json
import time
from datetime import datetime

# Add script directory to path for shared library import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _context_lib import read_stdin_json, get_snapshot_dir


# Maximum age (seconds) for snapshot restoration per source type
RESTORE_THRESHOLDS = {
    "clear": float("inf"),    # Always restore after /clear
    "compact": float("inf"),  # Always restore after compression
    "resume": 3600,           # 1 hour for resume
    "startup": 1800,          # 30 minutes for fresh startup
}


def main():
    input_data = read_stdin_json()

    # Determine source type
    source = input_data.get("source", "startup")

    # Determine project directory
    project_dir = os.environ.get(
        "CLAUDE_PROJECT_DIR",
        input_data.get("cwd", os.getcwd()),
    )

    snapshot_dir = get_snapshot_dir(project_dir)
    latest_path = os.path.join(snapshot_dir, "latest.md")

    # Check if snapshot exists
    if not os.path.exists(latest_path):
        sys.exit(0)  # No snapshot to restore — silent exit

    # Check age threshold
    snapshot_age = time.time() - os.path.getmtime(latest_path)
    max_age = RESTORE_THRESHOLDS.get(source, 1800)
    if snapshot_age > max_age:
        sys.exit(0)  # Snapshot too old for this source type

    # E6: Find best available snapshot (fallback if latest.md is inadequate)
    best_path, best_size = _find_best_snapshot(snapshot_dir, latest_path)
    fallback_note = ""
    if best_path != latest_path:
        latest_size = 0
        try:
            latest_size = os.path.getsize(latest_path)
        except OSError:
            pass
        fallback_note = (
            f"⚠️ latest.md ({latest_size}B)가 빈약하여 "
            f"더 풍부한 아카이브({best_size}B)를 참조합니다."
        )

    # Read snapshot for summary extraction
    try:
        with open(best_path, "r", encoding="utf-8") as f:
            snapshot_content = f.read()
    except Exception:
        sys.exit(0)

    if not snapshot_content.strip():
        sys.exit(0)

    # Extract brief summary from snapshot
    summary = _extract_brief_summary(snapshot_content)

    # Verify SOT consistency
    sot_warning = _verify_sot_consistency(snapshot_content, project_dir)

    # Build RLM-style recovery output (pointer + summary)
    recovery_output = _build_recovery_output(
        source=source,
        latest_path=best_path,  # E6: point to best available snapshot
        summary=summary,
        sot_warning=sot_warning,
        snapshot_age=snapshot_age,
        fallback_note=fallback_note,
    )

    # Output to stdout — Claude receives this as session context
    print(recovery_output)
    sys.exit(0)


def _extract_brief_summary(content):
    """Extract key information from snapshot for brief summary.

    Deterministic extraction from snapshot structure:
      - 현재 작업 (Current Task): first content line
      - 수정된 파일 (Modified Files): count of table rows
      - 참조된 파일 (Referenced Files): count of table rows
      - 대화 통계: numeric stats lines
    """
    summary_parts = []

    lines = content.split("\n")
    current_section = ""
    files_count = 0
    read_count = 0

    for line in lines:
        # Section header detection
        if line.startswith("## 현재 작업"):
            current_section = "task"
            continue
        elif line.startswith("## 결정론적 완료 상태"):
            current_section = "completion"
            continue
        elif line.startswith("## Git 변경 상태"):
            current_section = "git"
            continue
        elif line.startswith("## 수정된 파일"):
            current_section = "files"
            continue
        elif line.startswith("## 참조된 파일"):
            current_section = "reads"
            continue
        elif line.startswith("## 대화 통계"):
            current_section = "stats"
            continue
        elif line.startswith("## "):
            current_section = ""
            continue

        line = line.strip()
        if not line or line.startswith(">"):
            continue

        if current_section == "task":
            if line.startswith("**마지막 사용자 지시:**"):
                instruction = line.replace("**마지막 사용자 지시:**", "").strip()
                summary_parts.append(("최근 지시", instruction[:200]))
            elif len(summary_parts) < 1:
                summary_parts.append(("현재 작업", line[:200]))
        elif current_section == "completion" and line.startswith("- "):
            # "- Edit: 18회 호출 → 18 성공, 0 실패" 형태
            if "실패" in line or "성공" in line:
                summary_parts.append(("완료상태", line[:150]))
        elif current_section == "git" and line.startswith("```"):
            pass  # skip code block markers
        elif current_section == "git" and (line.startswith("M ") or line.startswith(" M") or line.startswith("A ") or line.startswith("??")):
            summary_parts.append(("git", line[:100]))
        elif current_section == "files" and (line.startswith("| `") or line.startswith("### `")):
            files_count += 1
        elif current_section == "reads" and line.startswith("| `"):
            read_count += 1
        elif current_section == "stats" and line.startswith("- "):
            summary_parts.append(("통계", line[:100]))

    # Add file counts as summary entries
    if files_count > 0:
        summary_parts.append(("수정 파일", f"{files_count}개 파일 수정됨"))
    if read_count > 0:
        summary_parts.append(("참조 파일", f"{read_count}개 파일 참조됨"))

    return summary_parts


def _verify_sot_consistency(snapshot_content, project_dir):
    """Check if current SOT matches snapshot's recorded SOT."""
    sot_paths = [
        os.path.join(project_dir, ".claude", "state.yaml"),
        os.path.join(project_dir, ".claude", "state.yml"),
        os.path.join(project_dir, ".claude", "state.json"),
    ]

    current_sot_exists = any(os.path.exists(p) for p in sot_paths)

    if "SOT 파일 없음" in snapshot_content and not current_sot_exists:
        return None  # Consistent: both have no SOT

    if current_sot_exists:
        # Read current SOT modification time
        for sot_path in sot_paths:
            if os.path.exists(sot_path):
                sot_mtime = datetime.fromtimestamp(
                    os.path.getmtime(sot_path)
                ).isoformat()

                # Check if snapshot recorded an older mtime
                if "수정 시각:" in snapshot_content:
                    for line in snapshot_content.split("\n"):
                        if "수정 시각:" in line:
                            recorded_time = line.split("수정 시각:")[1].strip()
                            if recorded_time != sot_mtime:
                                return (
                                    f"SOT가 snapshot 저장 이후 변경되었습니다. "
                                    f"기록: {recorded_time} → 현재: {sot_mtime}"
                                )
                break

    return None


def _build_recovery_output(source, latest_path, summary, sot_warning, snapshot_age, fallback_note=""):
    """Build the RLM-style recovery output for SessionStart injection."""
    age_str = _format_age(snapshot_age)

    # Build header
    output_lines = [
        "[CONTEXT RECOVERY]",
        f"이전 세션이 {'clear' if source == 'clear' else 'compact' if source == 'compact' else source}되었습니다.",
        f"전체 복원 파일: {latest_path}",
        "",
    ]

    # Brief summary
    task_info = ""
    latest_instruction = ""
    files_info = ""
    reads_info = ""
    stats_info = []
    completion_info = []
    git_info = []

    for label, content in summary:
        if label == "현재 작업":
            task_info = content
        elif label == "최근 지시":
            latest_instruction = content
        elif label == "수정 파일":
            files_info = content
        elif label == "참조 파일":
            reads_info = content
        elif label == "통계":
            stats_info.append(content)
        elif label == "완료상태":
            completion_info.append(content)
        elif label == "git":
            git_info.append(content)

    if task_info:
        output_lines.append(f"■ 현재 작업: {task_info}")
    if latest_instruction:
        output_lines.append(f"■ 최근 지시: {latest_instruction}")
    output_lines.append(f"■ 마지막 저장: {age_str} 전")

    if stats_info:
        for s in stats_info[:3]:
            output_lines.append(f"■ {s}")
    if files_info:
        output_lines.append(f"■ {files_info}")
    if reads_info:
        output_lines.append(f"■ {reads_info}")

    # Completion state and git status (Change 4)
    if completion_info:
        output_lines.append(f"■ 완료상태: {'; '.join(completion_info[:3])}")
    if git_info:
        output_lines.append(f"■ Git: {', '.join(git_info[:5])}")

    # E6: Fallback note (if using archive instead of latest.md)
    if fallback_note:
        output_lines.append("")
        output_lines.append(fallback_note)

    # SOT warning
    if sot_warning:
        output_lines.append("")
        output_lines.append(f"⚠️ {sot_warning}")

    # Knowledge Archive pointers (Area 1: Cross-Session)
    snapshot_dir = os.path.dirname(latest_path)
    ki_path = os.path.join(snapshot_dir, "knowledge-index.jsonl")
    sessions_dir = os.path.join(snapshot_dir, "sessions")

    has_archive = os.path.exists(ki_path) or os.path.isdir(sessions_dir)
    if has_archive:
        output_lines.append("")
        if os.path.exists(ki_path):
            output_lines.append(f"■ 과거 세션 인덱스: {ki_path}")
            recent = _get_recent_sessions(ki_path, 3)
            for s in recent:
                ts = s.get("timestamp", "")[:10]
                task = s.get("user_task", "(기록 없음)")[:80]
                output_lines.append(f"  - [{ts}] {task}")
        if os.path.isdir(sessions_dir):
            output_lines.append(f"■ 세션 아카이브: {sessions_dir}")

    # Instruction for Claude
    output_lines.extend([
        "",
        "⚠️ 작업을 계속하기 전에 반드시 위 파일을 Read tool로 읽어",
        "   이전 세션의 전체 맥락을 복원하세요.",
    ])

    return "\n".join(output_lines)


def _get_recent_sessions(ki_path, n=3):
    """Read last N entries from knowledge-index.jsonl.

    Deterministic: reads file, parses JSON lines, returns last N.
    Non-blocking: returns empty list on any error.
    """
    try:
        entries = []
        with open(ki_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries[-n:] if entries else []
    except Exception:
        return []


def _find_best_snapshot(snapshot_dir, latest_path):
    """E6: Find the best available snapshot when latest.md is inadequate.

    Quality criterion: file size (more structured data = larger file).
    P1 Compliance: file size is a deterministic metric.

    Falls back to sessions/ archive if latest.md has < 3KB of content
    (indicating a likely empty or minimal snapshot).
    """
    MIN_QUALITY_SIZE = 3000  # bytes

    latest_size = 0
    try:
        if os.path.exists(latest_path):
            latest_size = os.path.getsize(latest_path)
    except OSError:
        pass

    if latest_size >= MIN_QUALITY_SIZE:
        return latest_path, latest_size  # Sufficient quality

    # Scan sessions/ for a better recent archive
    sessions_dir = os.path.join(snapshot_dir, "sessions")
    if not os.path.isdir(sessions_dir):
        return latest_path, latest_size

    best_path = latest_path
    best_size = latest_size

    try:
        for fname in os.listdir(sessions_dir):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(sessions_dir, fname)
            fsize = os.path.getsize(fpath)
            fmtime = os.path.getmtime(fpath)

            # Only consider archives from the last hour, larger than current best
            if (time.time() - fmtime) < 3600 and fsize > best_size:
                best_path = fpath
                best_size = fsize
    except Exception:
        pass

    return best_path, best_size


def _format_age(seconds):
    """Format age in seconds to human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}초"
    elif seconds < 3600:
        return f"{int(seconds / 60)}분"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}시간"
    else:
        return f"{int(seconds / 86400)}일"


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Non-blocking: log error but don't crash the hook
        print(f"restore_context error: {e}", file=sys.stderr)
        sys.exit(0)
