#!/usr/bin/env python3
"""
Context Preservation System — Shared Library (_context_lib.py)

All hook scripts share this module for:
- Transcript JSONL parsing with deterministic extraction rules
- Structured MD snapshot generation (facts only, no heuristic inference)
- SOT state capture
- Atomic file writes with locking
- Token estimation (multi-signal)
- Dedup guard

Architecture:
  RLM Pattern: Snapshots are external memory objects (files on disk).
  P1 Compliance: Code handles deterministic extraction only.
                  Semantic interpretation is Claude's responsibility.
  SOT Compliance: Read-only access to SOT; writes only to context-snapshots/.
  Quality First: 100% accurate structured data, zero heuristic inference.
"""

import json
import os
import sys
import time
import fcntl
import tempfile
from datetime import datetime
from pathlib import Path


# =============================================================================
# Constants
# =============================================================================

# Token estimation: mixed Korean/English content ≈ 2.5 chars/token
CHARS_PER_TOKEN = 2.5
# Claude's context window (200K tokens)
CONTEXT_WINDOW_TOKENS = 200_000
# System prompt overhead estimate (tokens)
SYSTEM_OVERHEAD_TOKENS = 15_000
# Effective capacity
EFFECTIVE_CAPACITY = CONTEXT_WINDOW_TOKENS - SYSTEM_OVERHEAD_TOKENS
# 75% threshold
THRESHOLD_75_TOKENS = int(EFFECTIVE_CAPACITY * 0.75)
# Snapshot size target (characters) — keep under ~30KB for manageable Read
MAX_SNAPSHOT_CHARS = 30_000
# Dedup guard window (seconds)
DEDUP_WINDOW_SECONDS = 10
# Max snapshots to retain per trigger type
MAX_SNAPSHOTS = {
    "precompact": 3,
    "sessionend": 3,
    "threshold": 2,
    "stop": 5,
}
DEFAULT_MAX_SNAPSHOTS = 3


# =============================================================================
# Transcript Parsing
# =============================================================================

def parse_transcript(transcript_path):
    """
    Parse a Claude Code transcript JSONL file into structured entries.

    Returns list of dicts with keys:
        - type: 'user_message', 'assistant_text', 'tool_use', 'tool_result'
        - timestamp: ISO string
        - content: extracted content (varies by type)
        - file_path: (tool_use only, Write/Edit) deterministic file path
        - line_count: (tool_use only, Write) number of lines
    """
    entries = []
    if not transcript_path or not os.path.exists(transcript_path):
        return entries

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = obj.get("type")
                timestamp = obj.get("timestamp", "")

                if entry_type == "user":
                    entries.extend(_parse_user_entry(obj, timestamp))
                elif entry_type == "assistant":
                    entries.extend(_parse_assistant_entry(obj, timestamp))
                # Skip: progress, file-history-snapshot, system
    except Exception:
        pass

    return entries


def _parse_user_entry(obj, timestamp):
    """Extract user messages and tool results from user-type entries."""
    results = []
    message = obj.get("message", {})
    content = message.get("content", "")

    if isinstance(content, str):
        # Plain text user message
        text = content.strip()
        if text and not text.startswith("<local-command-"):
            results.append({
                "type": "user_message",
                "timestamp": timestamp,
                "content": text,
            })
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")

            if block_type == "text":
                text = block.get("text", "").strip()
                if text and not text.startswith("<local-command-"):
                    results.append({
                        "type": "user_message",
                        "timestamp": timestamp,
                        "content": text,
                    })

            elif block_type == "tool_result":
                tool_content = block.get("content", "")
                summary = _extract_tool_result_summary(tool_content)
                if summary:
                    results.append({
                        "type": "tool_result",
                        "timestamp": timestamp,
                        "tool_use_id": block.get("tool_use_id", ""),
                        "content": summary,
                    })

    return results


def _parse_assistant_entry(obj, timestamp):
    """Extract assistant text and tool uses from assistant-type entries.

    For tool_use entries, structured metadata (file_path, line_count) is
    extracted directly from tool_input — NOT parsed from summary strings.
    This ensures 100% deterministic, accurate file operation tracking.
    """
    results = []
    message = obj.get("message", {})
    content = message.get("content", [])

    if isinstance(content, str):
        text = content.strip()
        if text:
            results.append({
                "type": "assistant_text",
                "timestamp": timestamp,
                "content": _truncate(text, 2000),
            })
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")

            if block_type == "text":
                text = block.get("text", "").strip()
                if text:
                    results.append({
                        "type": "assistant_text",
                        "timestamp": timestamp,
                        "content": _truncate(text, 2000),
                    })

            elif block_type == "tool_use":
                tool_name = block.get("name", "unknown")
                tool_input = block.get("input", {})
                summary = _extract_tool_use_summary(tool_name, tool_input)

                entry = {
                    "type": "tool_use",
                    "timestamp": timestamp,
                    "tool_name": tool_name,
                    "content": summary,
                }

                # Structured metadata — deterministic, no string parsing
                if tool_name == "Write":
                    entry["file_path"] = tool_input.get("file_path", "")
                    file_content = tool_input.get("content", "")
                    entry["line_count"] = len(file_content.split("\n")) if file_content else 0
                elif tool_name == "Edit":
                    entry["file_path"] = tool_input.get("file_path", "")
                elif tool_name == "Bash":
                    entry["command"] = tool_input.get("command", "")
                    entry["description"] = tool_input.get("description", "")

                results.append(entry)

    return results


# =============================================================================
# Extraction Rules (per-tool summarization)
# =============================================================================

def _extract_tool_use_summary(tool_name, tool_input):
    """Apply per-tool extraction rules to keep snapshots compact."""
    if tool_name in ("Write",):
        path = tool_input.get("file_path", "unknown")
        content = tool_input.get("content", "")
        lines = content.split("\n")
        preview = "\n".join(lines[:3])
        return f"Write → {path} ({len(lines)} lines)\n  Preview: {_truncate(preview, 150)}"

    elif tool_name in ("Edit",):
        path = tool_input.get("file_path", "unknown")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        old_first = old.split("\n")[0] if old else ""
        new_first = new.split("\n")[0] if new else ""
        return f"Edit → {path}\n  {_truncate(old_first, 80)} → {_truncate(new_first, 80)}"

    elif tool_name in ("Read",):
        path = tool_input.get("file_path", "unknown")
        return f"Read → {path}"

    elif tool_name in ("Bash",):
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        return f"Bash: {_truncate(cmd, 200)}" + (f" ({desc})" if desc else "")

    elif tool_name in ("Task",):
        desc = tool_input.get("description", "")
        prompt = tool_input.get("prompt", "")
        agent_type = tool_input.get("subagent_type", "")
        return f"Task ({agent_type}): {desc}\n  Prompt: {_truncate(prompt, 200)}"

    elif tool_name in ("Glob",):
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        return f"Glob: {pattern}" + (f" in {path}" if path else "")

    elif tool_name in ("Grep",):
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        return f"Grep: {pattern}" + (f" in {path}" if path else "")

    elif tool_name in ("WebSearch",):
        query = tool_input.get("query", "")
        return f"WebSearch: {query}"

    elif tool_name in ("WebFetch",):
        url = tool_input.get("url", "")
        return f"WebFetch: {_truncate(url, 100)}"

    else:
        # Generic: show first 200 chars of input
        return f"{tool_name}: {_truncate(json.dumps(tool_input, ensure_ascii=False), 200)}"


def _extract_tool_result_summary(content):
    """Extract summary from tool_result content."""
    if isinstance(content, str):
        return _truncate(content, 300)
    elif isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        combined = "\n".join(texts)
        return _truncate(combined, 300)
    return ""


# =============================================================================
# SOT State Capture
# =============================================================================

def capture_sot(project_dir):
    """
    Read SOT file (state.yaml) if it exists.
    Hook is READ-ONLY for SOT — only captures content.
    """
    sot_paths = [
        os.path.join(project_dir, ".claude", "state.yaml"),
        os.path.join(project_dir, ".claude", "state.yml"),
        os.path.join(project_dir, ".claude", "state.json"),
    ]

    for sot_path in sot_paths:
        if os.path.exists(sot_path):
            try:
                with open(sot_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return {
                    "path": sot_path,
                    "content": _truncate(content, 3000),
                    "mtime": datetime.fromtimestamp(
                        os.path.getmtime(sot_path)
                    ).isoformat(),
                }
            except Exception:
                pass

    return None


# =============================================================================
# MD Snapshot Generation (Deterministic Data Only)
# =============================================================================

def generate_snapshot_md(session_id, trigger, project_dir, entries, work_log=None, sot_content=None):
    """Generate comprehensive MD snapshot from parsed entries.

    Design Principle (P1 + RLM):
      - Code produces ONLY deterministic, structured facts
      - NO heuristic inference (progress, decisions, pending actions)
      - Claude interprets meaning when reading the snapshot
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Classify entries
    user_messages = [e for e in entries if e["type"] == "user_message"]
    assistant_texts = [e for e in entries if e["type"] == "assistant_text"]
    tool_uses = [e for e in entries if e["type"] == "tool_use"]

    # Filtered user messages (exclude system-injected tags like <system-reminder>)
    user_msgs_filtered = [
        m for m in user_messages
        if not (m["content"].startswith("<") and ">" in m["content"][:50])
    ]

    # Build MD sections
    sections = []

    # Header
    sections.append(f"# Context Recovery — Session {session_id}")
    sections.append(f"> Saved: {now} | Trigger: {trigger}")
    sections.append(f"> Project: {project_dir}")
    sections.append(f"> Total entries: {len(entries)} | User msgs: {len(user_messages)} | Tool uses: {len(tool_uses)}")
    sections.append("")

    # Section 1: Current Task (first + last user message — verbatim)
    sections.append("## 현재 작업 (Current Task)")
    if user_messages:
        first_msg = user_messages[0]["content"]
        sections.append(_truncate(first_msg, 1500))
        # Latest context: show last user instruction if different from first
        if len(user_msgs_filtered) > 1:
            last_msg = user_msgs_filtered[-1]["content"]
            if last_msg != first_msg:
                sections.append("")
                sections.append(f"**마지막 사용자 지시:** {_truncate(last_msg, 500)}")
    else:
        sections.append("(사용자 메시지 없음)")
    sections.append("")

    # Section 2: SOT State (deterministic file read)
    sections.append("## SOT 상태 (Workflow State)")
    if sot_content:
        sections.append(f"파일: `{sot_content['path']}`")
        sections.append(f"수정 시각: {sot_content['mtime']}")
        sections.append("```yaml")
        sections.append(sot_content["content"])
        sections.append("```")
    else:
        sections.append("SOT 파일 없음 (state.yaml/state.json 미발견)")
    sections.append("")

    # Section 3: Modified Files (deterministic — from structured metadata)
    sections.append("## 수정된 파일 (Modified Files)")
    file_ops = _extract_file_operations(tool_uses, work_log)
    if file_ops:
        sections.append("| 파일 경로 | 도구 | 변경 요약 |")
        sections.append("|----------|------|---------|")
        for op in file_ops:
            sections.append(f"| `{op['path']}` | {op['tool']} | {op['summary']} |")
    else:
        sections.append("(파일 수정 기록 없음)")
    sections.append("")

    # Section 4: Statistics (positioned early — survives hard truncation)
    sections.append("## 대화 통계")
    transcript_size = _get_file_size(entries)
    estimated_tokens = int(transcript_size / CHARS_PER_TOKEN)
    sections.append(f"- 총 메시지: {len(user_msgs_filtered) + len(assistant_texts)}개")
    sections.append(f"- 도구 사용: {len(tool_uses)}회")
    sections.append(f"- 추정 토큰: ~{estimated_tokens:,}")
    sections.append(f"- 저장 트리거: {trigger}")
    if user_msgs_filtered:
        last_msg = _truncate(user_msgs_filtered[-1]["content"], 200)
        sections.append(f"- 마지막 사용자 메시지: \"{last_msg}\"")
    sections.append("")

    # Section 5: Commands Executed (verbatim from Bash tool_use entries)
    sections.append("## 실행된 명령 (Commands Executed)")
    bash_ops = [t for t in tool_uses if t.get("tool_name") == "Bash"]
    if bash_ops:
        for op in bash_ops[-10:]:  # Last 10 commands
            cmd = _truncate(op.get("command", ""), 150)
            desc = op.get("description", "")
            if cmd:
                sections.append(f"- `{cmd}`" + (f" ({desc})" if desc else ""))
            else:
                sections.append(f"- {op['content']}")
    else:
        sections.append("(명령 실행 기록 없음)")
    sections.append("")

    # Section 6: User Messages (verbatim — last N)
    sections.append("## 사용자 요청 이력 (User Messages)")
    if user_msgs_filtered:
        for i, msg in enumerate(user_msgs_filtered[-8:], 1):
            sections.append(f"{i}. {_truncate(msg['content'], 500)}")
    else:
        sections.append("(사용자 메시지 없음)")
    sections.append("")

    # Section 7: Claude Key Responses (verbatim — last N meaningful)
    sections.append("## Claude 핵심 응답 (Key Responses)")
    meaningful_texts = [
        t for t in assistant_texts
        if len(t["content"]) > 100  # Skip very short responses
    ]
    if meaningful_texts:
        for i, txt in enumerate(meaningful_texts[-5:], 1):
            sections.append(f"{i}. {_truncate(txt['content'], 500)}")
    else:
        sections.append("(Claude 응답 없음)")
    sections.append("")

    # Section 8: Work Log Summary (structured JSONL data)
    if work_log:
        sections.append("## 작업 로그 요약 (Work Log Summary)")
        sections.append(f"총 기록: {len(work_log)}개")
        for entry in work_log[-15:]:  # Last 15 entries
            ts = entry.get("timestamp", "")
            tool = entry.get("tool_name", "")
            summary = entry.get("summary", "")
            sections.append(f"- [{ts}] {tool}: {summary}")
        sections.append("")

    # Combine and enforce size limit
    full_md = "\n".join(sections)

    if len(full_md) > MAX_SNAPSHOT_CHARS:
        full_md = _compress_snapshot(full_md, sections)

    return full_md


# =============================================================================
# Deterministic File Operation Extraction
# =============================================================================

def _extract_file_operations(tool_uses, work_log=None):
    """Extract file modification records using structured metadata.

    Uses entry['file_path'] (set by _parse_assistant_entry) instead of
    parsing summary strings. This is 100% deterministic.
    """
    ops = []
    seen_paths = set()

    for tu in tool_uses:
        tool_name = tu.get("tool_name", "")

        if tool_name in ("Write", "Edit"):
            # Use structured metadata — NOT string parsing
            path = tu.get("file_path", "")

            if path and path not in seen_paths:
                seen_paths.add(path)

                if tool_name == "Write":
                    line_count = tu.get("line_count", 0)
                    summary = f"Write ({line_count} lines)"
                else:
                    summary = "Edit"

                ops.append({
                    "path": path,
                    "tool": tool_name,
                    "summary": summary,
                })

    # Supplement from work log (already structured)
    if work_log:
        for entry in work_log:
            path = entry.get("file_path", "")
            if path and path not in seen_paths:
                seen_paths.add(path)
                ops.append({
                    "path": path,
                    "tool": entry.get("tool_name", ""),
                    "summary": _truncate(entry.get("summary", ""), 100),
                })

    return ops


# =============================================================================
# Token Estimation (Multi-signal)
# =============================================================================

def estimate_tokens(transcript_path, entries=None):
    """
    Multi-signal token estimation.
    Returns (estimated_tokens, signals_dict)
    """
    signals = {}

    # Signal 1: File size
    file_size = 0
    if transcript_path and os.path.exists(transcript_path):
        file_size = os.path.getsize(transcript_path)
    signals["file_size_bytes"] = file_size
    tokens_from_size = int(file_size / CHARS_PER_TOKEN)

    # Signal 2: Message count (if entries available)
    if entries:
        user_count = sum(1 for e in entries if e["type"] == "user_message")
        assistant_count = sum(1 for e in entries if e["type"] == "assistant_text")
        tool_count = sum(1 for e in entries if e["type"] == "tool_use")
        signals["user_messages"] = user_count
        signals["assistant_messages"] = assistant_count
        signals["tool_uses"] = tool_count

        # Heuristic: each substantial exchange ≈ 3-5K tokens
        tokens_from_messages = (user_count + assistant_count) * 2000 + tool_count * 1500
    else:
        tokens_from_messages = tokens_from_size

    # Signal 3: Content character count
    if entries:
        total_chars = sum(len(e.get("content", "")) for e in entries)
        signals["total_content_chars"] = total_chars
        tokens_from_chars = int(total_chars / CHARS_PER_TOKEN)
    else:
        tokens_from_chars = tokens_from_size

    # Weighted average (file size is most reliable)
    estimated = int(
        tokens_from_size * 0.5 +
        tokens_from_messages * 0.25 +
        tokens_from_chars * 0.25
    )

    # Add system overhead
    estimated += SYSTEM_OVERHEAD_TOKENS

    signals["estimated_tokens"] = estimated
    signals["threshold_75"] = THRESHOLD_75_TOKENS
    signals["over_threshold"] = estimated > THRESHOLD_75_TOKENS

    return estimated, signals


# =============================================================================
# File Operations (Atomic + Locking)
# =============================================================================

def atomic_write(filepath, content):
    """Write content atomically: temp file → rename."""
    dirpath = os.path.dirname(filepath)
    os.makedirs(dirpath, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.rename(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def append_with_lock(filepath, content):
    """Append content with file locking (fcntl.flock)."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "a", encoding="utf-8") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(content)
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def load_work_log(snapshot_dir):
    """Load work log entries from JSONL."""
    log_path = os.path.join(snapshot_dir, "work_log.jsonl")
    entries = []
    if not os.path.exists(log_path):
        return entries

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    return entries


# =============================================================================
# Dedup Guard
# =============================================================================

def should_skip_save(snapshot_dir):
    """Check if a save was done within DEDUP_WINDOW_SECONDS."""
    latest_path = os.path.join(snapshot_dir, "latest.md")
    if os.path.exists(latest_path):
        age = time.time() - os.path.getmtime(latest_path)
        if age < DEDUP_WINDOW_SECONDS:
            return True
    return False


# =============================================================================
# Snapshot Cleanup
# =============================================================================

def cleanup_snapshots(snapshot_dir):
    """Remove old snapshots, keeping recent ones per trigger type."""
    try:
        files = []
        for f in os.listdir(snapshot_dir):
            if f.endswith(".md") and f != "latest.md":
                fpath = os.path.join(snapshot_dir, f)
                files.append((f, os.path.getmtime(fpath)))

        # Group by trigger type (last part of filename before .md)
        groups = {}
        for fname, mtime in files:
            # Format: YYYYMMDD_HHMMSS_trigger.md
            parts = fname.replace(".md", "").split("_")
            trigger = parts[-1] if len(parts) >= 3 else "unknown"
            if trigger not in groups:
                groups[trigger] = []
            groups[trigger].append((fname, mtime))

        # Keep only MAX per group (sorted by mtime, newest first)
        for trigger, group_files in groups.items():
            max_keep = MAX_SNAPSHOTS.get(trigger, DEFAULT_MAX_SNAPSHOTS)
            group_files.sort(key=lambda x: x[1], reverse=True)
            for fname, _ in group_files[max_keep:]:
                try:
                    os.unlink(os.path.join(snapshot_dir, fname))
                except OSError:
                    pass
    except Exception:
        pass


# =============================================================================
# Utility Helpers
# =============================================================================

def _truncate(text, max_len):
    """Truncate text to max_len, adding ellipsis if needed."""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _get_file_size(entries):
    """Estimate total character size from entries."""
    total = 0
    for e in entries:
        total += len(e.get("content", ""))
    return total


def _compress_snapshot(full_md, sections):
    """If snapshot exceeds MAX_SNAPSHOT_CHARS, compress less critical sections."""
    # Strategy: keep header, task, SOT, modified files, user messages
    # Truncate: commands, Claude responses, work log
    compressed_sections = []
    skip_next = False

    for section in sections:
        if "## 실행된 명령" in section:
            compressed_sections.append(section)
            compressed_sections.append("(크기 제한으로 축약됨)")
            skip_next = True
            continue
        if "## 작업 로그 요약" in section:
            compressed_sections.append(section)
            compressed_sections.append("(크기 제한으로 축약됨)")
            skip_next = True
            continue
        if skip_next and section.startswith("##"):
            skip_next = False
        if skip_next:
            continue
        compressed_sections.append(section)

    result = "\n".join(compressed_sections)
    if len(result) > MAX_SNAPSHOT_CHARS:
        return result[:MAX_SNAPSHOT_CHARS] + "\n\n(... 크기 초과로 잘림)"
    return result


def get_snapshot_dir(project_dir=None):
    """Get the context-snapshots directory path."""
    if not project_dir:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    return os.path.join(project_dir, ".claude", "context-snapshots")


def read_stdin_json():
    """Read and parse JSON from stdin (hook input)."""
    try:
        raw = sys.stdin.read()
        if raw.strip():
            return json.loads(raw)
    except (json.JSONDecodeError, Exception):
        pass
    return {}
