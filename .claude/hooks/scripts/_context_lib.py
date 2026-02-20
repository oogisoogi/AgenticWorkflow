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
import re
import sys
import time
import fcntl
import subprocess
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
# Snapshot size target (characters) — Quality First (절대 기준 1)
# Read tool handles up to 2000 lines. 100KB preserves decision context.
MAX_SNAPSHOT_CHARS = 100_000
# Dedup guard window (seconds) — reduced to avoid missing rapid changes
DEDUP_WINDOW_SECONDS = 5
# Stop hook uses wider window to reduce noise (~60→~10 saves/hour)
STOP_DEDUP_WINDOW_SECONDS = 30
# Max snapshots to retain per trigger type
MAX_SNAPSHOTS = {
    "precompact": 3,
    "sessionend": 3,
    "threshold": 2,
    "stop": 5,
}
DEFAULT_MAX_SNAPSHOTS = 3
# Knowledge Archive limits (Area 1: Cross-Session Knowledge Archive)
MAX_KNOWLEDGE_INDEX_ENTRIES = 200
MAX_SESSION_ARCHIVES = 20
# E5 Empty Snapshot Guard — section header constants
# These constants are the single definition for section headers used in both
# generate_snapshot_md() and is_rich_snapshot(). Changing a constant here
# automatically updates both the snapshot generator and the E5 Guard detector.
E5_RICH_CONTENT_MARKER = "### 수정 중이던 파일"
E5_COMPLETION_STATE_MARKER = "## 결정론적 완료 상태"
E5_DESIGN_DECISIONS_MARKER = "## 주요 설계 결정"
# A1: Multi-signal rich content markers for E5 Guard
# is_rich_snapshot() checks `marker in content` (substring match).
# Full headers in snapshot include English suffix, e.g.:
#   "## 결정론적 완료 상태 (Deterministic Completion State)"
E5_RICH_SIGNALS = [
    E5_RICH_CONTENT_MARKER,         # "### 수정 중이던 파일"
    E5_COMPLETION_STATE_MARKER,     # "## 결정론적 완료 상태"
    E5_DESIGN_DECISIONS_MARKER,     # "## 주요 설계 결정"
]

# --- Truncation limits (Quality First — 절대 기준 1) ---
# Edit preview: "왜" 그 편집을 했는지 의도 파악 가능한 길이
EDIT_PREVIEW_CHARS = 1000
# Error result: 에러 메시지 전체 보존 (stack trace + context)
ERROR_RESULT_CHARS = 3000
# Normal tool result — Bash 출력, 테스트 결과 등 실행 맥락 보존
NORMAL_RESULT_CHARS = 1500
# Write preview — 생성된 파일의 의도 파악 가능한 길이 (첫 8줄)
WRITE_PREVIEW_CHARS = 500
# Generic tool input preview
GENERIC_INPUT_CHARS = 200
# Bash command preview
BASH_CMD_CHARS = 200
# Task prompt preview
TASK_PROMPT_CHARS = 200
# SOT content capture
SOT_CAPTURE_CHARS = 3000
# Anti-Skip Guard minimum output size (bytes)
MIN_OUTPUT_SIZE = 100

# --- SOT file paths (single definition — 절대 기준 2) ---
SOT_FILENAMES = ("state.yaml", "state.yml", "state.json")

# --- Tool result error detection patterns (shared by check_ulw_compliance + extract_completion_state) ---
TOOL_ERROR_PATTERNS = [
    "Error:", "error:", "FAILED", "failed",
    "not found", "Permission denied", "No such file",
]

# --- Path tag extraction constants (A3: language-independent search tags) ---
_PATH_SKIP_NAMES = frozenset({
    "src", "lib", "dist", "build", "node_modules", "venv", ".git",
    "tests", "test", "__pycache__", ".claude", "scripts", "hooks",
})
_EXT_TAGS = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "react", ".jsx": "react", ".md": "markdown",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json",
    ".sh": "shell", ".css": "css", ".html": "html",
    ".rs": "rust", ".go": "golang", ".java": "java",
}


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
                is_error = block.get("is_error", False)
                summary = _extract_tool_result_summary(tool_content)
                if summary:
                    results.append({
                        "type": "tool_result",
                        "timestamp": timestamp,
                        "tool_use_id": block.get("tool_use_id", ""),
                        "is_error": is_error,
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
                "content": _truncate(text, 5000),
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
                        "content": _truncate(text, 5000),
                    })

            elif block_type == "tool_use":
                tool_name = block.get("name", "unknown")
                tool_input = block.get("input", {})
                summary = _extract_tool_use_summary(tool_name, tool_input)

                entry = {
                    "type": "tool_use",
                    "timestamp": timestamp,
                    "tool_name": tool_name,
                    "tool_use_id": block.get("id", ""),
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
                elif tool_name == "Read":
                    entry["file_path"] = tool_input.get("file_path", "")

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
        return f"Write → {path} ({len(lines)} lines)\n  Preview: {_truncate(preview, WRITE_PREVIEW_CHARS)}"

    elif tool_name in ("Edit",):
        path = tool_input.get("file_path", "unknown")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        # B-1: 첫 5줄 × EDIT_PREVIEW_CHARS — "왜" 그 편집을 했는지 의도+맥락 보존
        old_preview = "\n".join(old.split("\n")[:5]) if old else ""
        new_preview = "\n".join(new.split("\n")[:5]) if new else ""
        return (f"Edit → {path}\n"
                f"  OLD: {_truncate(old_preview, EDIT_PREVIEW_CHARS)}\n"
                f"  NEW: {_truncate(new_preview, EDIT_PREVIEW_CHARS)}")

    elif tool_name in ("Read",):
        path = tool_input.get("file_path", "unknown")
        return f"Read → {path}"

    elif tool_name in ("Bash",):
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        return f"Bash: {_truncate(cmd, BASH_CMD_CHARS)}" + (f" ({desc})" if desc else "")

    elif tool_name in ("Task",):
        desc = tool_input.get("description", "")
        prompt = tool_input.get("prompt", "")
        agent_type = tool_input.get("subagent_type", "")
        return f"Task ({agent_type}): {desc}\n  Prompt: {_truncate(prompt, TASK_PROMPT_CHARS)}"

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
        # Generic: show first GENERIC_INPUT_CHARS of input
        return f"{tool_name}: {_truncate(json.dumps(tool_input, ensure_ascii=False), GENERIC_INPUT_CHARS)}"


def _extract_tool_result_summary(content):
    """Extract summary from tool_result content.

    C-3: Error recovery narrative — error-containing results get expanded
    truncation limit (ERROR_RESULT_CHARS) to preserve diagnostic context.
    """
    _ERROR_PATTERNS = ("error", "Error", "ERROR", "failed", "Failed", "FAILED",
                       "traceback", "Traceback", "exception", "Exception")

    def _limit_for(text):
        if any(pat in text for pat in _ERROR_PATTERNS):
            return ERROR_RESULT_CHARS  # B-2: 에러 메시지 전체 보존 (stack trace 포함)
        return NORMAL_RESULT_CHARS

    if isinstance(content, str):
        return _truncate(content, _limit_for(content))
    elif isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        combined = "\n".join(texts)
        return _truncate(combined, _limit_for(combined))
    return ""


# =============================================================================
# SOT State Capture
# =============================================================================

def sot_paths(project_dir):
    """Build SOT file path list from SOT_FILENAMES constant (A-3: single definition)."""
    return [os.path.join(project_dir, ".claude", fn) for fn in SOT_FILENAMES]


def capture_sot(project_dir):
    """
    Read SOT file (state.yaml) if it exists.
    Hook is READ-ONLY for SOT — only captures content.
    """
    for sot_path in sot_paths(project_dir):
        if os.path.exists(sot_path):
            try:
                with open(sot_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return {
                    "path": sot_path,
                    "content": _truncate(content, SOT_CAPTURE_CHARS),
                    "mtime": datetime.fromtimestamp(
                        os.path.getmtime(sot_path)
                    ).isoformat(),
                }
            except Exception:
                pass

    return None


# =============================================================================
# Autopilot State (Read-Only — SOT Compliance)
# =============================================================================

def read_autopilot_state(project_dir):
    """Read autopilot state from SOT (state.yaml). Read-only.

    Returns dict with autopilot fields if enabled, None otherwise.

    IMPORTANT: Does NOT use capture_sot() — reads state.yaml directly
    without truncation. capture_sot() truncates to 3000 chars (for snapshot
    display), which can cut the autopilot section in large SOT files.

    Schema compatibility: Supports both AGENTS.md schema (workflow.autopilot)
    and flat schema (top-level autopilot). AGENTS.md §5.1 is authoritative.

    P1 Compliance: All fields are deterministic extractions from YAML/regex.
    SOT Compliance: Read-only file access.
    """
    # Direct file read — uses sot_paths() for consistency (A-3)
    # Only YAML files (not JSON) — autopilot regex patterns assume YAML format
    # CQ-1: Renamed to avoid shadowing the sot_paths() function
    yaml_sot_paths = [p for p in sot_paths(project_dir) if not p.endswith(".json")]

    content = ""
    for sot_path in yaml_sot_paths:
        if os.path.exists(sot_path):
            try:
                with open(sot_path, "r", encoding="utf-8") as f:
                    content = f.read()
                break
            except Exception:
                continue

    if not content:
        return None

    # Try PyYAML first (precise structured parsing)
    try:
        import yaml
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            # Schema compatibility: check both locations
            # AGENTS.md §5.1 schema: workflow.autopilot.enabled
            # Flat schema: autopilot.enabled (top-level)
            wf = data.get("workflow", {})
            if not isinstance(wf, dict):
                wf = {}
            ap = wf.get("autopilot") or data.get("autopilot")
            if not isinstance(ap, dict) or not ap.get("enabled"):
                return None
            return {
                "enabled": True,
                "activated_at": ap.get("activated_at", ""),
                "auto_approved_steps": ap.get("auto_approved_steps", []),
                "current_step": wf.get("current_step", 0),
                "workflow_name": wf.get("name", ""),
                "workflow_status": wf.get("status", ""),
                "outputs": wf.get("outputs", {}),
            }
    except Exception:
        pass

    # Regex fallback (when PyYAML is not available)
    # Matches both "autopilot:\n  enabled: true" at any nesting level
    enabled_match = re.search(
        r'autopilot\s*:\s*\n\s+enabled\s*:\s*(true|yes)',
        content, re.IGNORECASE
    )
    if not enabled_match:
        return None

    state = {
        "enabled": True,
        "activated_at": "",
        "auto_approved_steps": [],
        "current_step": 0,
        "workflow_name": "",
        "workflow_status": "",
        "outputs": {},
    }

    for field, pattern in [
        ("activated_at", r'activated_at\s*:\s*["\']?(.+?)["\']?\s*$'),
        ("current_step", r'current_step\s*:\s*(\d+)'),
        ("workflow_name", r'name\s*:\s*["\']?(.+?)["\']?\s*$'),
        ("workflow_status", r'status\s*:\s*["\']?(.+?)["\']?\s*$'),
    ]:
        m = re.search(pattern, content, re.MULTILINE)
        if m:
            val = m.group(1).strip()
            state[field] = int(val) if field == "current_step" else val

    # Extract auto_approved_steps list
    steps_match = re.search(r'auto_approved_steps\s*:\s*\[([^\]]*)\]', content)
    if steps_match:
        steps_str = steps_match.group(1)
        state["auto_approved_steps"] = [
            int(s.strip()) for s in steps_str.split(",")
            if s.strip().isdigit()
        ]

    # Extract outputs map
    outputs_section = re.search(
        r'outputs\s*:\s*\n((?:\s+step-\d+\s*:.+\n?)*)', content
    )
    if outputs_section:
        for m in re.finditer(
            r'(step-\d+)\s*:\s*["\']?(.+?)["\']?\s*$',
            outputs_section.group(1), re.MULTILINE
        ):
            state["outputs"][m.group(1)] = m.group(2).strip()

    return state


def validate_step_output(project_dir, step_number, outputs_map):
    """Anti-Skip Guard: validate that a step's output exists and has meaningful content.

    Deterministic validation (P1 compliant):
      - File existence check (os.path.exists)
      - Minimum size check (os.path.getsize >= MIN_OUTPUT_SIZE)

    Returns: (is_valid, reason_string)
    """
    key = f"step-{step_number}"

    if key not in outputs_map:
        return (False, f"Step {step_number}: output path not recorded in SOT outputs")

    output_path = outputs_map[key]

    # Resolve relative paths against project_dir
    if not os.path.isabs(output_path):
        output_path = os.path.join(project_dir, output_path)

    if not os.path.exists(output_path):
        return (False, f"Step {step_number}: output file not found: {output_path}")

    try:
        size = os.path.getsize(output_path)
    except OSError:
        return (False, f"Step {step_number}: cannot read output file: {output_path}")

    if size == 0:
        return (False, f"Step {step_number}: output file is empty: {output_path}")

    if size < MIN_OUTPUT_SIZE:
        return (False, f"Step {step_number}: output too small ({size} bytes, min {MIN_OUTPUT_SIZE}): {output_path}")

    return (True, f"Step {step_number}: OK — {output_path} ({size:,} bytes)")


def validate_sot_schema(ap_state):
    """SOT Schema Validation: structural integrity of autopilot state dict.

    P1 Compliance: All checks are deterministic (type, range, format).
    SOT Compliance: Read-only — validates in-memory dict, no file I/O.
    No duplication: file existence is validate_step_output()'s responsibility.

    Args:
        ap_state: dict from read_autopilot_state(), or None

    Returns: list of warning strings (empty list = all checks passed)
    """
    if not ap_state or not isinstance(ap_state, dict):
        return []

    warnings = []

    # S1: current_step — must be int >= 0
    cs = ap_state.get("current_step")
    if cs is not None:
        if not isinstance(cs, int):
            warnings.append(
                f"SOT schema: current_step is {type(cs).__name__}, expected int"
            )
        elif cs < 0:
            warnings.append(f"SOT schema: current_step is {cs}, must be >= 0")

    # S2: outputs — must be dict
    outputs = ap_state.get("outputs")
    if outputs is not None and not isinstance(outputs, dict):
        warnings.append(
            f"SOT schema: outputs is {type(outputs).__name__}, expected dict"
        )

    # S3: outputs keys — must follow step-N or step-N-ko format
    if isinstance(outputs, dict):
        for key in outputs:
            if not isinstance(key, str) or not key.startswith("step-"):
                warnings.append(f"SOT schema: invalid output key '{key}'")
                continue
            # Extract step number — allow step-N and step-N-ko (translation)
            suffix = key[5:]  # after "step-"
            parts = suffix.split("-", 1)
            if not parts[0].isdigit():
                warnings.append(
                    f"SOT schema: output key '{key}' has non-numeric step number"
                )

    # S4: No output recorded for future steps (step number > current_step)
    if isinstance(cs, int) and isinstance(outputs, dict):
        for key in outputs:
            if isinstance(key, str) and key.startswith("step-"):
                suffix = key[5:]
                parts = suffix.split("-", 1)
                if parts[0].isdigit():
                    step_num = int(parts[0])
                    if step_num > cs:
                        warnings.append(
                            f"SOT schema: output '{key}' for future step "
                            f"(current_step={cs})"
                        )

    # S5: workflow_status — must be recognized value
    status = ap_state.get("workflow_status", "")
    if status:
        valid_statuses = {"running", "completed", "error", "paused"}
        if status not in valid_statuses:
            warnings.append(
                f"SOT schema: unrecognized workflow_status '{status}'"
            )

    # S6: auto_approved_steps — items must be int, within plausible range
    approved = ap_state.get("auto_approved_steps", [])
    if isinstance(approved, list):
        for item in approved:
            if not isinstance(item, int):
                warnings.append(
                    f"SOT schema: auto_approved_steps contains non-int: {item}"
                )
            elif isinstance(cs, int) and item > cs:
                warnings.append(
                    f"SOT schema: auto_approved_steps contains future step "
                    f"{item} (current_step={cs})"
                )

    return warnings


# =============================================================================
# Active Team State (Read-Only — SOT Compliance, RLM Layer 2)
# =============================================================================

def read_active_team_state(project_dir):
    """Read active_team state from SOT (state.yaml). Read-only.

    Returns dict with active_team fields if a team is active, None otherwise.
    This enables 2-Layer RLM: Layer 1 (auto snapshots) + Layer 2 (team summaries in SOT).

    Schema (from claude-code-patterns.md §SOT 갱신 프로토콜):
      active_team:
        name: "team-name"
        status: "partial" | "all_completed"
        tasks_completed: ["task-1", ...]
        tasks_pending: ["task-2", ...]
        completed_summaries:
          task-1:
            agent: "@researcher"
            model: "sonnet"
            output: "path/to/output.md"
            summary: "brief description"

    P1 Compliance: All fields are deterministic extractions from YAML/regex.
    SOT Compliance: Read-only file access.
    """
    # A-3: use sot_paths() — YAML only (regex parsing)
    # B-1: Renamed to avoid shadowing the sot_paths() function (same fix as CQ-1)
    yaml_sot_paths = [p for p in sot_paths(project_dir) if not p.endswith(".json")]

    content = ""
    for sot_path in yaml_sot_paths:
        if os.path.exists(sot_path):
            try:
                with open(sot_path, "r", encoding="utf-8") as f:
                    content = f.read()
                break
            except Exception:
                continue

    if not content:
        return None

    # Try PyYAML first (precise structured parsing)
    try:
        import yaml
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            # Check both nested (workflow.active_team) and flat (active_team)
            wf = data.get("workflow", {})
            if not isinstance(wf, dict):
                wf = {}
            at = wf.get("active_team") or data.get("active_team")
            if not isinstance(at, dict) or not at.get("name"):
                return None
            return {
                "name": at.get("name", ""),
                "status": at.get("status", "unknown"),
                "tasks_completed": at.get("tasks_completed", []),
                "tasks_pending": at.get("tasks_pending", []),
                "completed_summaries": at.get("completed_summaries", {}),
            }
    except Exception:
        pass

    # Regex fallback (when PyYAML is not available)
    name_match = re.search(
        r'active_team\s*:\s*\n\s+name\s*:\s*["\']?(.+?)["\']?\s*$',
        content, re.MULTILINE
    )
    if not name_match:
        return None

    state = {
        "name": name_match.group(1).strip(),
        "status": "unknown",
        "tasks_completed": [],
        "tasks_pending": [],
        "completed_summaries": {},
    }

    status_match = re.search(
        r'active_team\s*:.*?status\s*:\s*["\']?(\w+)["\']?',
        content, re.DOTALL
    )
    if status_match:
        state["status"] = status_match.group(1).strip()

    # Extract task lists (YAML inline array format)
    for field in ["tasks_completed", "tasks_pending"]:
        m = re.search(rf'{field}\s*:\s*\[([^\]]*)\]', content)
        if m:
            items = [s.strip().strip("\"'") for s in m.group(1).split(",") if s.strip()]
            state[field] = items

    return state


# =============================================================================
# ULW (Ultrawork) Mode Detection
# =============================================================================

def detect_ulw_mode(entries):
    """Detect ULW (Ultrawork) mode activation from user messages.

    Scans transcript entries for the "ulw" keyword in user messages.
    Uses word-boundary regex to prevent false positives from variable names,
    file paths, or URLs (e.g., "resultw", "/usr/local/ulwrap").

    Args:
        entries: List of parsed transcript entries.

    Returns:
        dict with {active, detected_in, source_message, message_index} or None.

    P1 Compliance: Deterministic regex match on verbatim user messages.
    """
    # Word-boundary pattern: not preceded/followed by alphanumeric, underscore, slash, dot, hyphen
    ULW_PATTERN = re.compile(
        r'(?<![a-zA-Z0-9_/\-\.])ulw(?![a-zA-Z0-9_/\-\.])',
        re.IGNORECASE,
    )

    user_messages = [
        (i, e) for i, e in enumerate(entries)
        if e.get("type") == "user_message"
        and not (e.get("content", "").startswith("<") and ">" in e.get("content", "")[:50])
    ]

    for idx, (msg_index, entry) in enumerate(user_messages):
        content = entry.get("content", "")
        if ULW_PATTERN.search(content):
            return {
                "active": True,
                "detected_in": "first" if idx == 0 else "subsequent",
                "source_message": content[:500],
                "message_index": msg_index,
            }

    return None


def check_ulw_compliance(entries):
    """ULW 모드 활성 시 5개 실행 규칙의 준수 여부를 결정론적으로 검증.

    All checks are pure counting and pattern matching — P1 compliant.
    No heuristic inference. No AI judgment.

    Checks:
      1. Auto Task Tracking: TaskCreate used? (threshold: 5+ tool uses)
      2. Progress Reporting: TaskUpdate used? (when TaskCreate exists)
      3. Completion Verification: TaskList used? (when TaskCreate exists)
      4. Error Recovery: post-error tool actions exist?
      5. Sisyphus Mode: indirect — incomplete tasks at session end

    Args:
        entries: List of parsed transcript entries.

    Returns:
        dict with compliance metrics and warnings, or None if ULW inactive.
    """
    ulw_state = detect_ulw_mode(entries)
    if not ulw_state:
        return None

    # Filter: only count entries AFTER ULW activation point
    # Prevents false positives when ULW is activated in a "subsequent" message
    ulw_start_idx = ulw_state["message_index"]
    post_ulw_entries = entries[ulw_start_idx:]

    tool_uses = [e for e in post_ulw_entries if e.get("type") == "tool_use"]
    tool_results = [e for e in post_ulw_entries if e.get("type") == "tool_result"]

    compliance = {
        "active": True,
        "task_creates": 0,
        "task_updates": 0,
        "task_lists": 0,
        "total_tool_uses": len(tool_uses),
        "errors_detected": 0,
        "post_error_actions": 0,
        "warnings": [],
    }

    # Count task management tool uses
    for tu in tool_uses:
        name = tu.get("tool_name", "")
        if name == "TaskCreate":
            compliance["task_creates"] += 1
        elif name == "TaskUpdate":
            compliance["task_updates"] += 1
        elif name == "TaskList":
            compliance["task_lists"] += 1

    # Detect errors and post-error recovery attempts
    # Uses module-level TOOL_ERROR_PATTERNS (DRY — shared with extract_completion_state)
    last_error_global_idx = -1

    for i, entry in enumerate(post_ulw_entries):
        if entry.get("type") == "tool_result":
            is_error = entry.get("is_error", False)
            content = entry.get("content", "")[:500]
            if is_error or any(sig in content for sig in TOOL_ERROR_PATTERNS):
                compliance["errors_detected"] += 1
                last_error_global_idx = i

    # Count tool uses that occurred AFTER the last error (recovery attempts)
    if last_error_global_idx >= 0:
        for i, entry in enumerate(post_ulw_entries):
            if i > last_error_global_idx and entry.get("type") == "tool_use":
                compliance["post_error_actions"] += 1

    # Generate deterministic warnings
    # W1: No task tracking despite significant tool usage
    if compliance["task_creates"] == 0 and compliance["total_tool_uses"] >= 5:
        compliance["warnings"].append(
            "ULW_NO_TASKS: 도구 {}회 사용, TaskCreate 0회 — Auto Task Tracking 미준수".format(
                compliance["total_tool_uses"]
            )
        )

    # W2: Tasks created but never updated (no progress reporting)
    if compliance["task_creates"] > 0 and compliance["task_updates"] == 0:
        compliance["warnings"].append(
            "ULW_NO_PROGRESS: TaskCreate {}회, TaskUpdate 0회 — Progress Reporting 미준수".format(
                compliance["task_creates"]
            )
        )

    # W3: Tasks created but never listed (no completion verification)
    if compliance["task_creates"] > 0 and compliance["task_lists"] == 0:
        compliance["warnings"].append(
            "ULW_NO_VERIFY: TaskCreate {}회, TaskList 0회 — 완료 검증 미수행".format(
                compliance["task_creates"]
            )
        )

    # W4: Errors detected but no subsequent actions (no error recovery)
    if compliance["errors_detected"] > 0 and compliance["post_error_actions"] == 0:
        compliance["warnings"].append(
            "ULW_NO_RECOVERY: 에러 {}건 감지, 후속 조치 0건 — Error Recovery 미준수".format(
                compliance["errors_detected"]
            )
        )

    return compliance


# =============================================================================
# Git State Capture (E2 — Ground Truth)
# =============================================================================

def capture_git_state(project_dir, max_diff_chars=8000):
    """Git 변경 상태의 결정론적 캡처 (읽기 전용, SOT 준수).

    3개 시그널을 캡처하여 모든 시나리오에서 ground-truth 제공:
    1. git status --porcelain  (현재 작업 트리 상태)
    2. git diff HEAD            (커밋되지 않은 변경)
    3. git log --oneline --stat -5  (최근 커밋 — post-commit 시나리오 대응)

    P1 Compliance: All fields are subprocess stdout captures (deterministic).
    SOT Compliance: git commands are read-only.
    """
    result = {"status": "", "diff_stat": "", "diff_content": "", "recent_commits": ""}

    def _run_git(args, max_chars=2000):
        try:
            proc = subprocess.run(
                ["git"] + args,
                cwd=project_dir, capture_output=True, text=True, timeout=5
            )
            return proc.stdout.strip()[:max_chars] if proc.returncode == 0 else ""
        except Exception:
            return ""

    result["status"] = _run_git(["status", "--porcelain"])
    result["diff_stat"] = _run_git(["diff", "--stat", "HEAD"])
    result["diff_content"] = _run_git(["diff", "HEAD"], max_chars=max_diff_chars)
    result["recent_commits"] = _run_git(
        ["log", "--oneline", "--stat", "-5"], max_chars=3000
    )

    return result


# =============================================================================
# Deterministic Completion State (E7 — Hallucination Prevention)
# =============================================================================

def extract_completion_state(entries, project_dir):
    """결정론적 완료 상태 추출 — Claude 해석 불필요.

    P1 Compliance: All fields are deterministic extractions from
    transcript entries + filesystem checks. Zero heuristic inference.

    Hallucination prevention: Claude reads FACTS, not guesses.
    - Tool call success/failure via tool_use_id ↔ tool_result matching
    - File existence via os.path.exists() at save time
    - Quantitative metrics via counting
    """
    tool_uses = [e for e in entries if e["type"] == "tool_use"]
    tool_results = [e for e in entries if e["type"] == "tool_result"]

    # 1. Tool call counts (deterministic aggregation)
    tool_counts = {}
    for tu in tool_uses:
        name = tu.get("tool_name", "unknown")
        tool_counts[name] = tool_counts.get(name, 0) + 1

    # 2. Build tool_result lookup by tool_use_id
    result_by_id = {}
    for tr in tool_results:
        tid = tr.get("tool_use_id", "")
        if not tid:
            continue
        content = tr.get("content", "")
        is_error = tr.get("is_error", False)
        # Supplementary error pattern matching (defensive — in case is_error is missing)
        # Uses module-level TOOL_ERROR_PATTERNS (DRY — shared with check_ulw_compliance)
        has_error_pattern = any(p in content for p in TOOL_ERROR_PATTERNS) if not is_error else False
        result_by_id[tid] = is_error or has_error_pattern

    # 3. Edit/Write success/failure counts (matched via tool_use_id)
    edit_success = 0
    edit_fail = 0
    write_success = 0
    write_fail = 0
    bash_success = 0
    bash_fail = 0

    for tu in tool_uses:
        tid = tu.get("tool_use_id", "")
        name = tu.get("tool_name", "")
        is_err = result_by_id.get(tid, False)

        if name == "Edit":
            if is_err:
                edit_fail += 1
            else:
                edit_success += 1
        elif name == "Write":
            if is_err:
                write_fail += 1
            else:
                write_success += 1
        elif name == "Bash":
            if is_err:
                bash_fail += 1
            else:
                bash_success += 1

    # 4. File existence verification (filesystem check at save time)
    file_verification = []
    modified_paths = []
    seen_paths = set()
    for tu in tool_uses:
        if tu.get("tool_name") in ("Edit", "Write"):
            path = tu.get("file_path", "")
            if path and path not in seen_paths:
                seen_paths.add(path)
                modified_paths.append(path)
                exists = os.path.exists(path)
                mtime = ""
                if exists:
                    try:
                        mtime = datetime.fromtimestamp(
                            os.path.getmtime(path)
                        ).strftime("%H:%M:%S")
                    except Exception:
                        pass
                file_verification.append({
                    "path": path,
                    "exists": exists,
                    "mtime": mtime,
                })

    # 5. Session timeline (deterministic timestamps)
    timestamps = [e.get("timestamp", "") for e in entries if e.get("timestamp")]
    first_ts = timestamps[0] if timestamps else ""
    last_ts = timestamps[-1] if timestamps else ""

    return {
        "tool_counts": tool_counts,
        "edit_success": edit_success,
        "edit_fail": edit_fail,
        "write_success": write_success,
        "write_fail": write_fail,
        "bash_success": bash_success,
        "bash_fail": bash_fail,
        "file_verification": file_verification,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "total_tool_calls": len(tool_uses),
        "total_results": len(tool_results),
    }


# =============================================================================
# Conversation Phase Detection (C-5)
# =============================================================================

def _classify_phase(tool_uses):
    """Classify a set of tool uses into a single phase.

    P1 Compliance: Deterministic classification based on tool proportions.
    Returns: 'research', 'planning', 'implementation', 'orchestration', or 'unknown'
    """
    if not tool_uses:
        return "unknown"

    read_tools = sum(1 for t in tool_uses if t.get("tool_name") in
                     ("Read", "Grep", "Glob", "WebSearch", "WebFetch"))
    write_tools = sum(1 for t in tool_uses if t.get("tool_name") in
                      ("Edit", "Write", "Bash"))
    plan_tools = sum(1 for t in tool_uses if t.get("tool_name") in
                     ("AskUserQuestion", "EnterPlanMode", "ExitPlanMode"))
    task_tools = sum(1 for t in tool_uses if t.get("tool_name") in
                     ("Task", "TaskCreate", "TaskUpdate", "TeamCreate", "SendMessage"))

    total = len(tool_uses)

    if plan_tools > 0 and plan_tools >= write_tools:
        return "planning"
    if task_tools > total * 0.3:
        return "orchestration"
    if read_tools > total * 0.6:
        return "research"
    if write_tools > total * 0.4:
        return "implementation"
    if read_tools > write_tools:
        return "research"
    return "implementation"


def detect_conversation_phase(tool_uses):
    """Detect current conversation phase from tool usage patterns.

    P1 Compliance: Deterministic classification based on tool proportions.
    Returns: 'research', 'planning', 'implementation', 'orchestration', or 'unknown'
    """
    return _classify_phase(tool_uses)


def detect_phase_transitions(tool_uses, window_size=20):
    """B-4: Detect phase transitions within a session.

    Splits tool_uses into sliding windows and classifies each,
    identifying where the phase changed (e.g., research → implementation).

    P1 Compliance: Deterministic — window-based classification.
    Returns: list of (phase, start_index, end_index) tuples.
    """
    if not tool_uses or len(tool_uses) < window_size:
        return [(_classify_phase(tool_uses), 0, len(tool_uses))]

    phases = []
    current_phase = None
    phase_start = 0

    for i in range(0, len(tool_uses), window_size // 2):  # 50% overlap
        window = tool_uses[i:i + window_size]
        phase = _classify_phase(window)

        if phase != current_phase:
            if current_phase is not None:
                phases.append((current_phase, phase_start, i))
            current_phase = phase
            phase_start = i

    # Add final phase
    if current_phase is not None:
        phases.append((current_phase, phase_start, len(tool_uses)))

    return phases if phases else [("unknown", 0, len(tool_uses))]


# =============================================================================
# Per-File Diff Stats (C-4)
# =============================================================================

def _get_per_file_diff_stats(project_dir):
    """Get per-file line change counts from git diff --numstat.

    P1 Compliance: deterministic subprocess output.
    Returns: dict of {filepath: (added, removed)} or empty dict.
    """
    try:
        proc = subprocess.run(
            ["git", "diff", "--numstat", "HEAD"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if proc.returncode != 0:
            return {}
        result = {}
        for line in proc.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                added, removed, filepath = parts[0], parts[1], parts[2]
                result[filepath] = (added, removed)
        return result
    except Exception:
        return {}


# =============================================================================
# Next Step Extraction (CM-3)
# =============================================================================

def _extract_next_step(assistant_texts):
    """CM-3: Extract forward-looking statement from last assistant response.

    Captures the next action Claude was about to take, enabling task-based
    session resumption instead of summary-based guessing.

    P1 Compliance: Regex-based deterministic extraction.
    Returns: str or None (first match from last response, max 500 chars).
    """
    if not assistant_texts:
        return None

    # Search last 3 assistant responses (reverse order) for forward-looking patterns
    # CM-F: Expanded from 200→500 chars to preserve structured action plans
    _NEXT_STEP_PATTERN = re.compile(
        r'(?:다음으로|이제|그 다음|그 후|Next,?|Now |Then )'
        r'\s*(.{10,500}?)(?:\.\s|\n\n|$)',
        re.MULTILINE,
    )
    for entry in reversed(assistant_texts[-3:]):
        content = entry.get("content", "")
        match = _NEXT_STEP_PATTERN.search(content)
        if match:
            return match.group(0).strip()[:500]
    return None


# =============================================================================
# Decision Extraction (C-1)
# =============================================================================

def _extract_decisions(assistant_texts):
    """Extract structured design decisions from assistant responses.

    Detects:
    1. Explicit markers: <!-- DECISION: ... -->
    2. Structured patterns: **Decision:** / **결정:** / **선택:**
    3. Implicit intent patterns: "~하겠습니다", "선택 이유:", "approach:"
    4. Rationale patterns: "이유:", "근거:", "Rationale:", "because"

    P1 Compliance: Regex-based deterministic extraction.
    Returns: list of decision strings (max 15).
    """
    decisions = []
    # Pattern 1: HTML comment markers
    marker_pattern = re.compile(r'<!--\s*DECISION:\s*(.+?)\s*-->', re.DOTALL)
    # Pattern 2: Bold markers
    bold_pattern = re.compile(
        r'\*\*(?:Decision|결정|선택|채택|판단)\s*(?::|：)\*\*\s*(.+?)(?:\n|$)',
        re.IGNORECASE
    )
    # Pattern 3: Implicit intent (Korean) — "~하겠습니다" preceded by context
    # CM-2: Filter noise — routine action declarations are not design decisions
    _INTENT_NOISE = re.compile(
        r'읽겠습니다|확인하겠습니다|시작하겠습니다|살펴보겠습니다|'
        r'진행하겠습니다|분석하겠습니다|검토하겠습니다|파악하겠습니다|'
        r'Let me read|Let me check|I\'ll start|I\'ll look',
        re.IGNORECASE,
    )
    # B-2: Non-greedy .{10,120}? to prevent capturing unrelated preceding text
    intent_pattern = re.compile(
        r'(?:^|\n)\s*[-*]?\s*(.{10,120}?(?:하겠습니다|로 결정|을 선택|를 채택|접근 방식|approach))',
        re.MULTILINE
    )
    # Pattern 4: Rationale markers
    rationale_pattern = re.compile(
        r'(?:선택\s*이유|근거|Rationale|Reason(?:ing)?)\s*(?::|：)\s*(.+?)(?:\n|$)',
        re.IGNORECASE
    )
    # CM-A + E-2: Comparison/selection patterns — captures "A instead of B" decisions
    comparison_pattern = re.compile(
        r'(.{5,80}?)\s+(?:대신|보다는?|rather than|instead of|over)\s+(.{5,80}?)(?:\.|,|\n|$)',
        re.IGNORECASE | re.MULTILINE
    )
    # CM-A + E-2: Trade-off/architecture direction patterns
    tradeoff_pattern = re.compile(
        r'(?:trade-?off|장단점|pros?\s*(?:and|&)\s*cons?|단점은|downside)\s*(?::|：|은|는)?\s*(.+?)(?:\n|$)',
        re.IGNORECASE
    )
    # CM-A + E-2: Explicit choice verb patterns (English)
    choice_pattern = re.compile(
        r'(?:chose|opted for|selected|decided to|went with|picked)\s+(.{10,150}?)(?:\.|,|\n|$)',
        re.IGNORECASE
    )

    for entry in assistant_texts:
        content = entry.get("content", "")
        for match in marker_pattern.finditer(content):
            decisions.append(("[explicit] " + match.group(1).strip())[:300])
        for match in bold_pattern.finditer(content):
            decisions.append(("[decision] " + match.group(1).strip())[:300])
        for match in intent_pattern.finditer(content):
            matched_text = match.group(1).strip()
            # CM-2: Skip routine action declarations (noise)
            if _INTENT_NOISE.search(matched_text):
                continue
            decisions.append(("[intent] " + matched_text)[:300])
        for match in rationale_pattern.finditer(content):
            decisions.append(("[rationale] " + match.group(1).strip())[:300])
        # CM-A + E-2: New high-signal decision patterns
        for match in comparison_pattern.finditer(content):
            decisions.append(("[decision] " + match.group(0).strip())[:300])
        for match in tradeoff_pattern.finditer(content):
            decisions.append(("[rationale] " + match.group(0).strip())[:300])
        for match in choice_pattern.finditer(content):
            decisions.append(("[decision] " + match.group(0).strip())[:300])

    # Dedup while preserving order
    seen = set()
    unique = []
    for d in decisions:
        if d not in seen:
            seen.add(d)
            unique.append(d)

    # CM-2: Stratified slot allocation — [intent] capped at 3 slots (noise reduction)
    # Remaining 12 slots guaranteed for high-signal decisions ([explicit]/[decision]/[rationale])
    _DECISION_PRIORITY = {"[explicit]": 0, "[decision]": 1, "[rationale]": 2, "[intent]": 3}
    # B-3: Safer tag extraction — use find() on prefix only to avoid false matches
    # from ']' characters in the decision content itself
    def _get_decision_tag(d):
        if d.startswith("["):
            end = d.find("]")
            if 0 < end < 20:  # Tags are short ([explicit], [intent], etc.)
                return d[:end + 1]
        return ""
    unique.sort(key=lambda d: _DECISION_PRIORITY.get(_get_decision_tag(d), 4))

    # Separate high-signal from intent, cap intent at 3
    high_signal = [d for d in unique if not d.startswith("[intent]")]
    intent_only = [d for d in unique if d.startswith("[intent]")]
    result = high_signal[:12] + intent_only[:3]
    return result[:15]


# =============================================================================
# MD Snapshot Generation (Deterministic Data Only)
# =============================================================================

def generate_snapshot_md(session_id, trigger, project_dir, entries, work_log=None, sot_content=None):
    """Generate comprehensive MD snapshot from parsed entries.

    Design Principle (P1 + RLM):
      - Code produces ONLY deterministic, structured facts
      - NO heuristic inference (progress, decisions, pending actions)
      - Claude interprets meaning when reading the snapshot

    v3 Enhancements:
      - E7: Deterministic Completion State (hallucination prevention)
      - E2: Git state capture (ground truth, post-commit aware)
      - E3: Per-edit detail preservation (aggregation loss prevention)
      - E4: Claude response priority selection + section promotion

    Section survival priority (truncation order):
      1-9: IMMORTAL  (Header, Task, SOT, Autopilot*, ULW*, Team*, Decisions*, Resume, Completion State, Git)
      10-13: CRITICAL  (Modified Files, Referenced Files, User Messages, Claude Responses)
      14-16: SACRIFICABLE (Statistics, Commands, Work Log)
      (* = conditional sections, only present when active)
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

    # Pre-compute structured data (used by multiple sections)
    file_ops = _extract_file_operations(tool_uses, work_log)
    read_ops = _extract_read_operations(tool_uses)
    completion_state = extract_completion_state(entries, project_dir)
    git_state = capture_git_state(project_dir)
    conversation_phase = detect_conversation_phase(tool_uses)  # C-5
    diff_stats = _get_per_file_diff_stats(project_dir)  # C-4
    decisions = _extract_decisions(assistant_texts)  # C-1

    # Build MD sections
    sections = []

    # ━━━ SURVIVAL PRIORITY 1: IMMORTAL ━━━

    # Header
    sections.append(f"# Context Recovery — Session {session_id}")
    sections.append(f"> Saved: {now} | Trigger: {trigger}")
    sections.append(f"> Project: {project_dir}")
    sections.append(f"> Total entries: {len(entries)} | User msgs: {len(user_messages)} | Tool uses: {len(tool_uses)}")
    sections.append(f"> Phase: {conversation_phase}")  # C-5: conversation phase detection
    sections.append("")

    # Section 1: Current Task (first + last user message — verbatim)
    # CM-6: IMMORTAL — user messages are the ground truth for task context
    sections.append("## 현재 작업 (Current Task)")
    sections.append("<!-- IMMORTAL: 사용자 작업 지시 — 세션 복원의 핵심 맥락 -->")
    # CM-C: Filter system commands (/clear, /help, etc.) — show real task, not commands
    _SYSTEM_CMD = re.compile(
        r'^\s*<command-name>|^\s*/(?:clear|help|compact|init|resume|review|login|logout|mcp|config)\b',
        re.IGNORECASE | re.MULTILINE,
    )
    real_user_msgs = [m for m in user_messages if not _SYSTEM_CMD.search(m.get("content", ""))]
    if real_user_msgs:
        first_msg = real_user_msgs[0]["content"]
        sections.append(_truncate(first_msg, 3000))
        # Last instruction from filtered (non-continuation) messages
        real_filtered = [m for m in user_msgs_filtered if not _SYSTEM_CMD.search(m.get("content", ""))]
        if real_filtered and len(real_filtered) > 1:
            last_msg = real_filtered[-1]["content"]
            if last_msg != first_msg:
                sections.append("")
                sections.append(f"**최근 지시 (Latest Instruction):** {_truncate(last_msg, 1500)}")
    elif user_messages:
        # Fallback: all messages are system commands, show the first one anyway
        sections.append(_truncate(user_messages[0]["content"], 3000))
    else:
        sections.append("(사용자 메시지 없음)")

    # CM-3: Next Step extraction — last assistant's forward-looking statement
    next_step = _extract_next_step(assistant_texts)
    if next_step:
        sections.append("")
        sections.append(f"**다음 단계 (Next Step):** {next_step}")
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

    # Section 2.5: Autopilot State (IMMORTAL — conditional, only when active)
    try:
        ap_state = read_autopilot_state(project_dir)
        if ap_state:
            sections.append("## Autopilot 상태 (Autopilot State)")
            sections.append("<!-- IMMORTAL: 세션 복원 시 반드시 보존 -->")
            sections.append("")
            sections.append(f"- **활성화**: Yes")
            if ap_state.get("activated_at"):
                sections.append(f"- **활성화 시각**: {ap_state['activated_at']}")
            sections.append(f"- **워크플로우**: {ap_state.get('workflow_name', 'N/A')}")
            sections.append(f"- **현재 단계**: Step {ap_state.get('current_step', '?')}")
            sections.append(f"- **상태**: {ap_state.get('workflow_status', 'N/A')}")
            approved = ap_state.get("auto_approved_steps", [])
            if approved:
                sections.append(f"- **자동 승인된 단계**: {approved}")
            sections.append("")

            # SOT schema validation (P1 — structural integrity)
            schema_warnings = validate_sot_schema(ap_state)
            if schema_warnings:
                sections.append("### SOT 스키마 검증 (Schema Validation)")
                for warning in schema_warnings:
                    sections.append(f"  [WARN] {warning}")
                sections.append("")

            # Per-step output validation (Anti-Skip Guard)
            outputs = ap_state.get("outputs", {})
            if outputs:
                sections.append("### 단계별 산출물 검증 (Anti-Skip Guard)")
                for step_num in sorted(
                    int(k.replace("step-", "")) for k in outputs.keys()
                    if k.startswith("step-")
                ):
                    is_valid, reason = validate_step_output(
                        project_dir, step_num, outputs
                    )
                    mark = "[OK]" if is_valid else "[FAIL]"
                    sections.append(f"  {mark} {reason}")
                sections.append("")
    except Exception:
        pass  # Non-blocking — autopilot section is supplementary

    # Section 2.6: Active Team State (IMMORTAL — conditional, only when team active)
    try:
        team_state = read_active_team_state(project_dir)
        if team_state:
            sections.append("## Agent Team 상태 (Active Team State)")
            sections.append("<!-- IMMORTAL: 세션 복원 시 반드시 보존 — RLM Layer 2 -->")
            sections.append("")
            sections.append(f"- **팀 이름**: {team_state['name']}")
            sections.append(f"- **상태**: {team_state['status']}")
            completed = team_state.get("tasks_completed", [])
            pending = team_state.get("tasks_pending", [])
            if completed:
                sections.append(f"- **완료 Task**: {completed}")
            if pending:
                sections.append(f"- **대기 Task**: {pending}")
            sections.append("")

            # Completed summaries (RLM Layer 2 — team work summaries)
            summaries = team_state.get("completed_summaries", {})
            if summaries:
                sections.append("### Teammate 작업 요약 (RLM Layer 2)")
                for task_id, info in summaries.items():
                    if isinstance(info, dict):
                        agent = info.get("agent", "?")
                        model = info.get("model", "?")
                        output = info.get("output", "?")
                        summary = info.get("summary", "")
                        sections.append(f"- **{task_id}** ({agent}, {model}): {output}")
                        if summary:
                            sections.append(f"  - {summary}")
                sections.append("")
    except Exception:
        pass  # Non-blocking — team section is supplementary

    # Section 2.65: ULW State (IMMORTAL — conditional, only when active)
    try:
        ulw_state = detect_ulw_mode(entries)
        if ulw_state:
            sections.append("## ULW 상태 (Ultrawork Mode State)")
            sections.append("<!-- IMMORTAL: 세션 복원 시 반드시 보존 -->")
            sections.append("")
            sections.append(f"- **활성화**: Yes")
            sections.append(f"- **감지 위치**: {ulw_state['detected_in']} user message (index {ulw_state['message_index']})")
            sections.append(f"- **원본 지시**: {_truncate(ulw_state['source_message'], 500)}")
            sections.append("")
            sections.append("### ULW 실행 규칙 (Execution Rules)")
            sections.append("1. **Sisyphus Mode**: 모든 Task가 100% 완료될 때까지 멈추지 않음")
            sections.append("2. **Auto Task Tracking**: 요청을 TaskCreate로 분해 → TaskUpdate로 추적 → TaskList로 검증")
            sections.append("3. **Error Recovery**: 에러 발생 시 대안을 시도하고, 대안도 실패하면 사용자에게 보고")
            sections.append("4. **No Partial Completion**: '일부만 완료'는 미완료와 동일 — 전체 완료까지 계속")
            sections.append("5. **Progress Reporting**: 각 Task 완료 시 TaskUpdate로 상태 갱신")
            sections.append("")

            # ULW Compliance Guard — deterministic rule compliance check
            ulw_compliance = check_ulw_compliance(entries)
            if ulw_compliance:
                sections.append("### 준수 상태 (Compliance Guard)")
                sections.append(f"- TaskCreate: {ulw_compliance['task_creates']}회")
                sections.append(f"- TaskUpdate: {ulw_compliance['task_updates']}회")
                sections.append(f"- TaskList: {ulw_compliance['task_lists']}회")
                sections.append(f"- 총 도구 사용: {ulw_compliance['total_tool_uses']}회")
                if ulw_compliance["errors_detected"] > 0:
                    sections.append(f"- 에러 감지: {ulw_compliance['errors_detected']}건")
                    sections.append(f"- 에러 후 조치: {ulw_compliance['post_error_actions']}건")
                warnings = ulw_compliance.get("warnings", [])
                if warnings:
                    sections.append("")
                    sections.append("**⚠ 규칙 위반 감지:**")
                    for w in warnings:
                        sections.append(f"- {w}")
                else:
                    sections.append("")
                    sections.append("✅ 모든 규칙 준수")
                sections.append("")
    except Exception:
        pass  # Non-blocking — ULW section is supplementary

    # Section 2.7: Design Decisions (C-1 — IMMORTAL, conditional)
    if decisions:
        sections.append(f"{E5_DESIGN_DECISIONS_MARKER} (Design Decisions)")
        sections.append("<!-- IMMORTAL: 세션 복원 시 '왜' 그 결정을 했는지 보존 -->")
        sections.append("")
        for i, dec in enumerate(decisions, 1):
            sections.append(f"{i}. {dec}")
        sections.append("")

    # Section 3: Resume Protocol (deterministic — P1 compliant)
    sections.append("## 복원 지시 (Resume Protocol)")
    sections.append("<!-- Python 결정론적 생성 — P1 준수 -->")
    sections.append("")
    if file_ops:
        sections.append(E5_RICH_CONTENT_MARKER)
        for op in file_ops:
            # C-4: per-file change summary from git diff
            diff_suffix = ""
            if diff_stats:
                # Match by basename or relative path
                rel_path = os.path.relpath(op['path'], project_dir) if os.path.isabs(op['path']) else op['path']
                stats = diff_stats.get(rel_path)
                if not stats:
                    # Try 2-level suffix match (dir/file) to reduce false matches
                    parent = os.path.basename(os.path.dirname(op['path']))
                    basename = os.path.basename(op['path'])
                    suffix_2 = os.path.join(parent, basename) if parent else basename
                    for dp, ds in diff_stats.items():
                        if dp.endswith(suffix_2):
                            stats = ds
                            break
                    # Final fallback: basename-only (accept ambiguity)
                    if not stats:
                        for dp, ds in diff_stats.items():
                            if dp.endswith(basename):
                                stats = ds
                                break
                if stats:
                    diff_suffix = f" (+{stats[0]}/-{stats[1]})"
            sections.append(f"- `{op['path']}` ({op['tool']}, {op['summary']}){diff_suffix}")
    if read_ops:
        sections.append("### 참조하던 파일")
        for op in read_ops[:10]:
            sections.append(f"- `{op['path']}` (Read, {op['count']}회)")
    transcript_size = _get_file_size(entries)
    estimated_tokens = int(transcript_size / CHARS_PER_TOKEN)
    last_tool = ""
    if tool_uses:
        last_tu = tool_uses[-1]
        last_tool_name = last_tu.get("tool_name", "")
        last_tool_path = last_tu.get("file_path", "")
        last_tool = last_tool_name
        if last_tool_path:
            last_tool += f" → {last_tool_path}"
    sections.append("### 세션 정보")
    sections.append(f"- 종료 트리거: {trigger}")
    sections.append(f"- 추정 토큰: ~{estimated_tokens:,}")
    if last_tool:
        sections.append(f"- 마지막 도구: {last_tool}")
    sections.append("")

    # Section 4: Deterministic Completion State (E7 — hallucination prevention)
    sections.append(f"{E5_COMPLETION_STATE_MARKER} (Deterministic Completion State)")
    sections.append("<!-- Python 결정론적 생성 — Claude 해석 불필요, 직접 참조 -->")
    sections.append("")
    cs = completion_state
    sections.append("### 도구 호출 결과")
    # Show major tools with success/failure for Edit/Write/Bash
    for tk in ["Edit", "Write", "Bash", "Read", "Task", "Grep", "Glob"]:
        count = cs["tool_counts"].get(tk, 0)
        if count > 0:
            if tk == "Edit":
                sections.append(
                    f"- Edit: {count}회 호출 → {cs['edit_success']} 성공, {cs['edit_fail']} 실패"
                )
            elif tk == "Write":
                sections.append(
                    f"- Write: {count}회 호출 → {cs['write_success']} 성공, {cs['write_fail']} 실패"
                )
            elif tk == "Bash":
                sections.append(
                    f"- Bash: {count}회 호출 → {cs['bash_success']} 성공, {cs['bash_fail']} 실패"
                )
            else:
                sections.append(f"- {tk}: {count}회 호출")
    # Other tools not in the main list
    other_tools = {
        k: v for k, v in cs["tool_counts"].items()
        if k not in ("Edit", "Write", "Bash", "Read", "Task", "Grep", "Glob")
    }
    for name, count in sorted(other_tools.items()):
        sections.append(f"- {name}: {count}회 호출")
    sections.append("")

    if cs["file_verification"]:
        sections.append("### 파일 상태 검증 (저장 시점)")
        sections.append("| 파일 | 존재 | 최종수정 |")
        sections.append("|------|------|---------|")
        for fv in cs["file_verification"]:
            exists_mark = "✓" if fv["exists"] else "✗"
            short_path = os.path.basename(fv["path"])
            sections.append(f"| `{short_path}` | {exists_mark} | {fv['mtime']} |")
        sections.append("")

    if cs["first_timestamp"] or cs["last_timestamp"]:
        sections.append("### 세션 타임라인")
        if cs["first_timestamp"]:
            sections.append(f"- 시작: {cs['first_timestamp']}")
        if cs["last_timestamp"]:
            sections.append(f"- 종료: {cs['last_timestamp']}")
        sections.append("")

    # A6: 최근 도구 호출 시간순 기록 — 에러-복구 패턴 보존
    recent_tools = [
        e for e in entries
        if e.get("type") == "tool_use" and e.get("tool_name")
    ][-10:]  # 마지막 10개
    if recent_tools:
        # Pre-build error lookup: O(n) once instead of O(10n) nested scan
        result_errors = {}
        for e2 in entries:
            if e2.get("type") == "tool_result":
                tid = e2.get("tool_use_id", "")
                if tid and e2.get("is_error"):
                    result_errors[tid] = True
        sections.append("### 최근 도구 활동 (시간순)")
        for rt in recent_tools:
            tool = rt.get("tool_name", "?")
            fp = rt.get("file_path", "")
            ts = rt.get("timestamp", "")[-8:]  # HH:MM:SS
            short_fp = os.path.basename(fp) if fp else ""
            tu_id = rt.get("tool_use_id", "")
            result_tag = " ← ERROR" if result_errors.get(tu_id) else ""
            suffix = f" → `{short_fp}`" if short_fp else ""
            sections.append(f"- [{ts}] {tool}{suffix}{result_tag}")
        sections.append("")

    # Section 5: Git Changes (E2 — ground truth, post-commit aware)
    if any(git_state.values()):
        sections.append("## Git 변경 상태 (Git Changes)")
        if git_state["status"]:
            sections.append("### Working Tree")
            sections.append(f"```\n{git_state['status']}\n```")
        elif not git_state["diff_stat"]:
            sections.append("### Working Tree")
            sections.append("```\nclean (변경 없음)\n```")
        if git_state["diff_stat"]:
            sections.append("### Uncommitted Changes")
            sections.append(f"```\n{git_state['diff_stat']}\n```")
        if git_state["diff_content"]:
            sections.append("### Diff Detail")
            sections.append(f"```diff\n{git_state['diff_content']}\n```")
        if git_state["recent_commits"]:
            sections.append("### Recent Commits")
            sections.append(f"```\n{git_state['recent_commits']}\n```")
        sections.append("")

    # ━━━ SURVIVAL PRIORITY 2: CRITICAL ━━━

    # Section 6: Modified Files with per-edit details (E3)
    sections.append("## 수정된 파일 (Modified Files)")
    if file_ops:
        for op in file_ops:
            sections.append(f"### `{op['path']}` ({op['tool']}, {op['summary']})")
            if op.get("details"):
                for j, detail in enumerate(op["details"], 1):
                    sections.append(f"  {j}. {_truncate(detail, 200)}")
            sections.append("")
    else:
        sections.append("(파일 수정 기록 없음)")
    sections.append("")

    # Section 7: Referenced Files
    sections.append("## 참조된 파일 (Referenced Files)")
    if read_ops:
        sections.append("| 파일 경로 | 횟수 |")
        sections.append("|----------|------|")
        for op in read_ops[:20]:
            sections.append(f"| `{op['path']}` | {op['count']} |")
    else:
        sections.append("(파일 참조 기록 없음)")
    sections.append("")

    # Section 8: User Messages (verbatim — last N)
    sections.append("## 사용자 요청 이력 (User Messages)")
    if user_msgs_filtered:
        for i, msg in enumerate(user_msgs_filtered[-12:], 1):
            sections.append(f"{i}. {_truncate(msg['content'], 800)}")
    else:
        sections.append("(사용자 메시지 없음)")
    sections.append("")

    # Section 9: Claude Key Responses (E4 — priority selection, promoted)
    sections.append("## Claude 핵심 응답 (Key Responses)")
    meaningful_texts = [
        t for t in assistant_texts
        if len(t["content"]) > 100
    ]
    if meaningful_texts:
        # Priority markers for structured progress reports
        PRIORITY_MARKERS = [
            "Done", "완료", "PASS", "FAIL", "TODO",
            "남은", "진행", "요약", "검증", "수정 완료",
            "## ", "| ", "```",
        ]

        def _priority_score(t):
            content = t["content"]
            score = sum(1 for m in PRIORITY_MARKERS if m in content)
            if len(content) > 500:
                score += 1
            if len(content) > 1000:
                score += 1
            return score

        # Last 3 responses always preserved (most recent context)
        last_3 = meaningful_texts[-3:]
        last_3_ids = set(id(t) for t in last_3)
        # From remaining, select top 5 by priority score
        remaining = [
            t for t in meaningful_texts
            if id(t) not in last_3_ids
        ]
        remaining.sort(key=_priority_score, reverse=True)
        top_priority = remaining[:5]
        # Merge and output in original chronological order
        selected_ids = set(id(t) for t in last_3 + top_priority)
        selected_responses = [t for t in meaningful_texts if id(t) in selected_ids]
        for i, txt in enumerate(selected_responses, 1):
            content = txt["content"]
            if len(content) > 2500:
                # A5: Structure-preserving compression — keep header + conclusion
                # Split: first 1200 chars (intro/structure) + last 1000 chars (conclusion)
                head = content[:1200]
                tail = content[-1000:]
                omitted = len(content) - 2200
                sections.append(f"{i}. {head}\n  [...{omitted}자 생략...]\n  {tail}")
            else:
                sections.append(f"{i}. {content}")
    else:
        sections.append("(Claude 응답 없음)")
    sections.append("")

    # ━━━ SURVIVAL PRIORITY 3: SACRIFICABLE ━━━

    # Section 10: Statistics
    sections.append("## 대화 통계")
    sections.append(f"- 총 메시지: {len(user_msgs_filtered) + len(assistant_texts)}개")
    sections.append(f"- 도구 사용: {len(tool_uses)}회")
    sections.append(f"- 추정 토큰: ~{estimated_tokens:,}")
    sections.append(f"- 저장 트리거: {trigger}")
    if user_msgs_filtered:
        last_msg = _truncate(user_msgs_filtered[-1]["content"], 200)
        sections.append(f"- 마지막 사용자 메시지: \"{last_msg}\"")
    sections.append("")

    # Section 11: Commands Executed
    sections.append("## 실행된 명령 (Commands Executed)")
    bash_ops = [t for t in tool_uses if t.get("tool_name") == "Bash"]
    if bash_ops:
        for op in bash_ops[-20:]:
            cmd = _truncate(op.get("command", ""), 150)
            desc = op.get("description", "")
            if cmd:
                sections.append(f"- `{cmd}`" + (f" ({desc})" if desc else ""))
            else:
                sections.append(f"- {op['content']}")
    else:
        sections.append("(명령 실행 기록 없음)")
    sections.append("")

    # Section 12: Work Log Summary
    if work_log:
        sections.append("## 작업 로그 요약 (Work Log Summary)")
        sections.append(f"총 기록: {len(work_log)}개")
        for entry in work_log[-25:]:
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

    E3 Enhancement: Preserves per-edit details (not just aggregated summary).
    Each edit's OLD→NEW context is stored in 'details' list, preventing
    information loss from aggregation.
    """
    # Track operations per path (preserve insertion order)
    path_order = []
    ops_by_path = {}

    for tu in tool_uses:
        tool_name = tu.get("tool_name", "")

        if tool_name in ("Write", "Edit"):
            # Use structured metadata — NOT string parsing
            path = tu.get("file_path", "")
            if not path:
                continue

            if path not in ops_by_path:
                path_order.append(path)
                ops_by_path[path] = {
                    "count": 0, "last_tool": "", "last_summary": "",
                    "details": [],  # E3: per-edit detail preservation
                }

            record = ops_by_path[path]
            record["count"] += 1
            record["last_tool"] = tool_name

            if tool_name == "Write":
                line_count = tu.get("line_count", 0)
                record["last_summary"] = f"Write ({line_count} lines)"
                record["details"].append(f"Write ({line_count} lines)")
            else:
                record["last_summary"] = "Edit"
                # Extract OLD→NEW detail from content (set by _extract_tool_use_summary)
                content = tu.get("content", "Edit")
                lines = content.split("\n")
                detail_parts = []
                for line in lines[1:3]:  # OLD/NEW lines
                    stripped = line.strip()
                    if stripped:
                        detail_parts.append(stripped)
                detail_str = " | ".join(detail_parts) if detail_parts else "Edit"
                record["details"].append(detail_str)

    # Build result list in insertion order
    ops = []
    for path in path_order:
        record = ops_by_path[path]
        if record["count"] > 1:
            summary = f"{record['last_summary']}, {record['count']}회 수정"
        else:
            summary = record["last_summary"]
        ops.append({
            "path": path,
            "tool": record["last_tool"],
            "summary": summary,
            "details": record["details"],  # E3: per-edit details
        })

    # Supplement from work log (already structured)
    if work_log:
        for entry in work_log:
            path = entry.get("file_path", "")
            if path and path not in ops_by_path:
                ops_by_path[path] = True  # Mark as seen
                ops.append({
                    "path": path,
                    "tool": entry.get("tool_name", ""),
                    "summary": _truncate(entry.get("summary", ""), 100),
                    "details": [],
                })

    return ops


def _extract_read_operations(tool_uses):
    """Extract Read operations with frequency count.

    Deterministic extraction from tool_use entries.
    Tracks which files Claude was consulting during the session.
    Used for Resume Protocol and Knowledge Archive.
    """
    read_counts = {}
    for tu in tool_uses:
        if tu.get("tool_name") == "Read":
            path = tu.get("file_path", "")
            if path:
                read_counts[path] = read_counts.get(path, 0) + 1

    # Sort by frequency (most read first), then alphabetically
    return sorted(
        [{"path": p, "count": c} for p, c in read_counts.items()],
        key=lambda x: (-x["count"], x["path"]),
    )


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

def should_skip_save(snapshot_dir, trigger=None):
    """Check if a save was done within dedup window.

    SessionEnd is exempt: /clear is an explicit user action,
    so the save must always happen regardless of dedup window.
    Stop hook uses wider window (30s) to reduce noise.
    """
    if trigger in ("sessionend",):
        return False
    latest_path = os.path.join(snapshot_dir, "latest.md")
    if os.path.exists(latest_path):
        age = time.time() - os.path.getmtime(latest_path)
        # Stop hook uses wider window (30s) to reduce noise
        window = STOP_DEDUP_WINDOW_SECONDS if trigger == "stop" else DEDUP_WINDOW_SECONDS
        if age < window:
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


def _append_compression_audit(content, audit):
    """A5: Append compression audit trail as HTML comment.

    P1 Compliance: Deterministic metadata only.
    Format: single-line HTML comment (invisible in rendered MD, greppable).
    """
    if not audit:
        return content
    final_size = len(content)
    trail = " ".join(audit)
    return content + f"\n<!-- compression-audit: {trail} | final:{final_size}ch/{MAX_SNAPSHOT_CHARS}ch -->"


def _compress_snapshot(full_md, sections):
    """Quality-focused compression (절대 기준 1: 품질 우선).

    Compression priority (sacrifice order — last resort first):
      Phase 1: Deduplicate redundant entries
      Phase 2: Reduce commands section (SACRIFICABLE)
      Phase 3: Reduce work log (SACRIFICABLE)
      Phase 4: Reduce statistics section (SACRIFICABLE)
      Phase 5: Compress Git diff detail (keep stat + commits, drop full diff)
      Phase 6: Compress Claude responses (keep conclusions)
      Phase 7: Hard truncate only as absolute last resort

    Always preserved (IMMORTAL):
      Header, Current Task, SOT, Autopilot State*, ULW State*,
      Team State*, Design Decisions*, Resume Protocol,
      Deterministic Completion State, Git Changes (stat+commits)
      (* = conditional sections, only present when active)

    High priority (CRITICAL):
      Modified Files, Referenced Files, User Messages, Claude Responses
    """
    # A5: Compression audit trail
    audit = []
    original_size = sum(len(s) + 1 for s in sections)  # +1 for \n

    # Phase 1: Deduplicate — remove consecutive identical entries
    deduped_sections = _dedup_sections(sections)
    result = "\n".join(deduped_sections)
    p1_removed = original_size - len(result)
    if p1_removed > 0:
        audit.append(f"P1-dedup:-{p1_removed}ch")
    if len(result) <= MAX_SNAPSHOT_CHARS:
        return _append_compression_audit(result, audit)

    # Phase 2: Compress commands (keep first 3 + last 5)
    prev_size = len(result)
    compressed = _compress_section_entries(
        deduped_sections, "## 실행된 명령", keep_first=3, keep_last=5
    )
    result = "\n".join(compressed)
    p2_removed = prev_size - len(result)
    if p2_removed > 0:
        audit.append(f"P2-cmds:-{p2_removed}ch")
    if len(result) <= MAX_SNAPSHOT_CHARS:
        return _append_compression_audit(result, audit)

    # Phase 3: Compress work log (keep last 10)
    prev_size = len(result)
    compressed = _compress_section_entries(
        compressed, "## 작업 로그 요약", keep_first=0, keep_last=10
    )
    result = "\n".join(compressed)
    p3_removed = prev_size - len(result)
    if p3_removed > 0:
        audit.append(f"P3-wlog:-{p3_removed}ch")
    if len(result) <= MAX_SNAPSHOT_CHARS:
        return _append_compression_audit(result, audit)

    # Phase 4: Remove statistics section entirely (regeneratable)
    prev_size = len(result)
    compressed = _remove_section(compressed, "## 대화 통계")
    result = "\n".join(compressed)
    p4_removed = prev_size - len(result)
    if p4_removed > 0:
        audit.append(f"P4-stats:-{p4_removed}ch")
    if len(result) <= MAX_SNAPSHOT_CHARS:
        return _append_compression_audit(result, audit)

    # Phase 5: Compress Git diff detail (keep stat + commits, drop full diff)
    prev_size = len(result)
    compressed = _remove_section(compressed, "### Diff Detail")
    result = "\n".join(compressed)
    p5_removed = prev_size - len(result)
    if p5_removed > 0:
        audit.append(f"P5-diff:-{p5_removed}ch")
    if len(result) <= MAX_SNAPSHOT_CHARS:
        return _append_compression_audit(result, audit)

    # Phase 6: Compress Claude responses (preserve conclusion — last 300 chars)
    prev_size = len(result)
    compressed = _compress_responses(compressed)
    result = "\n".join(compressed)
    p6_removed = prev_size - len(result)
    if p6_removed > 0:
        audit.append(f"P6-resp:-{p6_removed}ch")
    if len(result) <= MAX_SNAPSHOT_CHARS:
        return _append_compression_audit(result, audit)

    # Phase 7: IMMORTAL-aware hard truncate (absolute last resort)
    # CM-E: Preserve IMMORTAL sections, truncate non-IMMORTAL from bottom up
    immortal_lines = []
    other_lines = []
    in_immortal_section = False
    for line in compressed:
        if "<!-- IMMORTAL:" in line:
            in_immortal_section = True
        if line.startswith("## ") and "IMMORTAL" not in line and in_immortal_section:
            in_immortal_section = False
        if in_immortal_section or line.startswith("# Context Recovery"):
            immortal_lines.append(line)
        else:
            other_lines.append(line)

    immortal_text = "\n".join(immortal_lines)
    other_text = "\n".join(other_lines)
    audit.append(f"P7-truncate:immortal={len(immortal_text)}ch,other={len(other_text)}ch")
    budget = MAX_SNAPSHOT_CHARS - len(immortal_text) - 100
    if budget > 0:
        truncated = immortal_text + "\n" + other_text[:budget] + \
            "\n\n(... 크기 초과로 잘림 — 전체 내역은 sessions/ 아카이브 참조)"
        return _append_compression_audit(truncated, audit)
    # Even IMMORTAL exceeds limit — truncate IMMORTAL itself (preserving start)
    # Reflection fix: Use immortal_text, not Phase 6 result, to avoid
    # cutting mixed content that defeats IMMORTAL-first purpose
    truncated = immortal_text[:MAX_SNAPSHOT_CHARS] + \
        "\n\n(... IMMORTAL 자체가 한계 초과로 잘림 — 전체 내역은 sessions/ 아카이브 참조)"
    return _append_compression_audit(truncated, audit)


def _dedup_sections(sections):
    """Remove consecutive duplicate entries within list-style sections."""
    result = []
    prev_line = None
    for line in sections:
        # Skip consecutive identical list items
        if line.startswith("- ") and line == prev_line:
            continue
        result.append(line)
        prev_line = line
    return result


def _compress_section_entries(sections, section_header, keep_first=0, keep_last=5):
    """Compress a specific section's list entries, keeping first N + last N."""
    result = []
    in_section = False
    section_entries = []

    for line in sections:
        if section_header in line:
            in_section = True
            result.append(line)
            continue
        if in_section and line.startswith("##"):
            # End of section — emit compressed entries
            _emit_compressed_entries(result, section_entries, keep_first, keep_last)
            section_entries = []
            in_section = False
            result.append(line)
            continue
        if in_section and line.startswith("- "):
            section_entries.append(line)
            continue
        if in_section and not line.strip():
            section_entries.append(line)
            continue
        if in_section:
            # Non-list content in section (e.g., "총 기록: N개")
            result.append(line)
            continue
        result.append(line)

    # If section was the last one
    if section_entries:
        _emit_compressed_entries(result, section_entries, keep_first, keep_last)

    return result


def _emit_compressed_entries(result, entries, keep_first, keep_last):
    """Emit first N + last N entries with omission marker."""
    # Filter out blank lines for counting
    items = [e for e in entries if e.strip()]
    blanks_after = [e for e in entries if not e.strip()]

    total = len(items)
    if total <= keep_first + keep_last:
        result.extend(entries)
        return

    if keep_first > 0:
        result.extend(items[:keep_first])
    omitted = total - keep_first - keep_last
    result.append(f"  (...{omitted}개 항목 생략...)")
    result.extend(items[-keep_last:])
    if blanks_after:
        result.append("")


def _remove_section(sections, section_header):
    """Remove an entire section (header to next ## header) from sections list."""
    result = []
    in_section = False
    for line in sections:
        if section_header in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            in_section = False
            result.append(line)
            continue
        # When removing a ### subsection, stop at the next sibling ### header
        if in_section and section_header.startswith("### ") and line.startswith("### ") and section_header not in line:
            in_section = False
            result.append(line)
            continue
        if in_section and line.startswith("### ") and not section_header.startswith("### "):
            # Sub-section within removed ## section — also remove
            continue
        if not in_section:
            result.append(line)
    return result


def _compress_responses(sections):
    """Compress Claude responses: structure-aware compression (C-7).

    Preserves structural markers (headers, lists, code blocks, tables)
    while dropping verbose prose. More generous limits for structured content.
    """
    result = []
    in_section = False

    for line in sections:
        if "## Claude 핵심 응답" in line:
            in_section = True
            result.append(line)
            continue
        if in_section and line.startswith("##"):
            in_section = False
            result.append(line)
            continue
        if in_section and line and line[0].isdigit() and ". " in line[:5]:
            # Numbered response — structure-aware compression
            if len(line) > 500:
                result.append(_structure_aware_compress_line(line))
            else:
                result.append(line)
            continue
        result.append(line)

    return result


def _structure_aware_compress_line(text, max_prefix=120, max_conclusion=400):
    """Compress a single long text line, preserving structural markers (C-7).

    Structure-rich content (headers, lists, tables) gets more generous limits.
    """
    structural_markers = ("## ", "### ", "- ", "* ", "| ", "```", "1. ", "2. ")
    has_structure = any(m in text for m in structural_markers)

    if has_structure:
        # Structured content: keep more context
        prefix = text[:max_prefix]
        conclusion = text[-max_conclusion:]
        return f"{prefix} (...구조 보존...) {conclusion}"
    else:
        # Plain prose: standard compression
        prefix = text[:80]
        conclusion = text[-300:]
        return f"{prefix} (...) {conclusion}"


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


# =============================================================================
# E5 Guard Helper (A1: Multi-Signal Rich Content Detection)
# =============================================================================

def is_rich_snapshot(content):
    """Multi-signal rich content detection for E5 Empty Snapshot Guard.

    P1 Compliance: Deterministic — size threshold + marker counting.
    Returns True if snapshot is "rich" (should not be overwritten by empty one).

    Signals (any 2 of the following):
      1. Content length >= 3KB (aligned with E6 MIN_QUALITY_SIZE)
      2-4. Presence of E5_RICH_SIGNALS markers
    """
    if not content:
        return False

    signal_count = 0

    # Signal 1: Size threshold (aligned with E6 MIN_QUALITY_SIZE = 3000)
    if len(content.encode("utf-8")) >= 3000:
        signal_count += 1

    # Signals 2-4: Section markers
    for marker in E5_RICH_SIGNALS:
        if marker in content:
            signal_count += 1

    return signal_count >= 2


# =============================================================================
# E5 Guard + Knowledge Archive — Consolidated Helpers
# =============================================================================

def update_latest_with_guard(snapshot_dir, md_content, entries):
    """Atomically update latest.md with E5 Empty Snapshot Guard.

    Returns True if latest.md was updated, False if existing rich snapshot
    was protected from overwrite by an empty one.

    P1 Compliance: Deterministic (tool_use count + is_rich_snapshot).
    SOT Compliance: No SOT access.
    """
    latest_path = os.path.join(snapshot_dir, "latest.md")
    new_tool_count = sum(1 for e in entries if e.get("type") == "tool_use")

    if os.path.exists(latest_path) and new_tool_count == 0:
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
            if is_rich_snapshot(existing_content):
                return False
        except Exception:
            pass

    atomic_write(latest_path, md_content)
    return True


def archive_and_index_session(
    snapshot_dir, md_content, session_id, trigger,
    project_dir, entries, transcript_path,
):
    """Archive snapshot + extract knowledge-index facts + cleanup.

    Consolidates the 3-step archive pattern used by all save triggers:
      1. Archive snapshot to sessions/ directory
      2. Extract session facts → knowledge-index.jsonl
      3. Rotate archives and index

    P1 Compliance: All operations deterministic.
    SOT Compliance: Read-only SOT access (via extract_session_facts).
    Timestamp format: ISO-like %Y-%m-%dT%H%M%S (unified across all triggers).
    """
    # Step 1: Archive to sessions/ (isolated — failure does NOT block Step 2)
    # RLM rationale: archive is backup; knowledge-index is the RLM-critical asset.
    # If sessions/ mkdir or write fails, Step 2 must still record the session.
    try:
        sessions_dir = os.path.join(snapshot_dir, "sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
        archive_name = f"{ts}_{session_id[:8]}.md"
        archive_path = os.path.join(sessions_dir, archive_name)
        atomic_write(archive_path, md_content)
    except Exception:
        pass  # Non-blocking — Step 2 (RLM-critical) proceeds independently

    # Step 2: Extract session facts → knowledge-index.jsonl (RLM-critical)
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

    # Step 3: Rotate archives and index (each cleanup is internally protected)
    cleanup_session_archives(snapshot_dir)
    cleanup_knowledge_index(snapshot_dir)


# =============================================================================
# Path Tag Extraction (A3: Language-Independent Search Tags)
# =============================================================================

def extract_path_tags(file_paths):
    """Extract language-independent search tags from file paths.

    P1 Compliance: Deterministic string processing only.
    Returns: sorted unique list of tag strings (max 20).

    Tag sources:
      - CamelCase splitting: "AuthService.py" → ["auth", "service"]
      - snake_case splitting: "user_auth.py" → ["user", "auth"]
      - Extension mapping: ".py" → "python"
    """
    tags = set()
    for fp in file_paths:
        if not fp:
            continue
        parts = Path(fp).parts
        for part in parts:
            name = Path(part).stem  # filename without extension
            if name.startswith(".") or name in _PATH_SKIP_NAMES:
                continue
            # CamelCase splitting: "AuthService" → ["Auth", "Service"]
            # Also handles: "getHTTPResponse" → ["get", "HTTP", "Response"]
            subtokens = re.findall(r'[A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z]|$)', name)
            for st in subtokens:
                lower = st.lower()
                if len(lower) >= 3:  # skip noise ("a", "db", "io")
                    tags.add(lower)
        # Extension tag
        ext = os.path.splitext(fp)[1].lower()
        if ext in _EXT_TAGS:
            tags.add(_EXT_TAGS[ext])
    return sorted(tags)[:20]


# =============================================================================
# Knowledge-Index Schema Validation (P1: Hallucination Prevention)
# =============================================================================

# RLM-critical keys that MUST exist in every knowledge-index entry.
# If extract_session_facts() is modified and accidentally drops a key,
# this validation fills safe defaults — writing incomplete data is better
# than writing nothing (RLM visibility > field completeness).
_KI_REQUIRED_DEFAULTS = {
    "session_id": "",
    "timestamp": "",
    "user_task": "",
    "modified_files": [],
    "read_files": [],
    "tools_used": {},
    "final_status": "unknown",
    "tags": [],
    "phase": "",
    "completion_summary": {},
}


def _validate_session_facts(facts):
    """P1 Hallucination Prevention: Ensure RLM-critical keys exist before write.

    Deterministic schema enforcement — fills missing keys with safe defaults.
    Prevents malformed knowledge-index entries from breaking RLM queries like:
      Grep "tags.*python" knowledge-index.jsonl
      Grep "final_status.*success" knowledge-index.jsonl

    Returns: facts dict with all required keys guaranteed present.
    """
    for key, default_val in _KI_REQUIRED_DEFAULTS.items():
        if key not in facts:
            # Create new mutable instances to avoid shared references
            if isinstance(default_val, list):
                facts[key] = []
            elif isinstance(default_val, dict):
                facts[key] = {}
            else:
                facts[key] = default_val
    return facts


# =============================================================================
# Knowledge Archive (Area 1: Cross-Session Knowledge Archive)
# =============================================================================

def _classify_error_patterns(entries):
    """CM-1: Classify error patterns from tool results for cross-session learning.

    P1 Compliance: Regex-based deterministic classification.
    A2 Enhancement: File-aware, window-limited resolution matching.
    Returns: list of {"type": str, "tool": str, "file": str, "resolution": dict|None} (max 5).
    """
    tool_results = [e for e in entries if e["type"] == "tool_result"]
    tool_uses = [e for e in entries if e["type"] == "tool_use"]

    # Build tool_use_id → tool_name mapping
    id_to_tool = {tu.get("tool_use_id", ""): tu.get("tool_name", "") for tu in tool_uses}
    id_to_file = {tu.get("tool_use_id", ""): tu.get("file_path", "") for tu in tool_uses}

    # CM-B + E-1: Expanded error taxonomy — reduces "unknown" classification from ~80% to ~30%
    ERROR_TAXONOMY = [
        ("file_not_found", re.compile(r"No such file|FileNotFoundError|ENOENT|not found", re.I)),
        ("permission", re.compile(r"Permission denied|EACCES|PermissionError|EPERM", re.I)),
        ("syntax", re.compile(r"SyntaxError|syntax error|parse error|unexpected token", re.I)),
        ("timeout", re.compile(r"timed? ?out|TimeoutError|deadline exceeded|ETIMEDOUT", re.I)),
        ("dependency", re.compile(r"ModuleNotFoundError|ImportError|Cannot find module|require\(\) failed", re.I)),
        # B-4: Added re.DOTALL — "old_string ... not found" may span multiple lines
        ("edit_mismatch", re.compile(r"old_string.*not found|not unique|no match|string not found in file", re.I | re.DOTALL)),
        # E-1: New patterns (Reflection: tightened to reduce false positives)
        ("type_error", re.compile(r"TypeError|type error|undefined is not a function|\w+ is not a function(?! of\b)", re.I)),
        ("value_error", re.compile(r"ValueError|invalid (?:value|argument|literal)|value.{0,30}out of range", re.I)),
        ("connection", re.compile(r"ConnectionError|ECONNREFUSED|ECONNRESET|network error|fetch failed", re.I)),
        ("memory", re.compile(r"MemoryError|out of memory|heap (?:space|memory|allocation|overflow)|ENOMEM|allocation failed", re.I)),
        ("git_error", re.compile(r"fatal:.*git|merge conflict|CONFLICT|not a git repository", re.I | re.DOTALL)),
        ("command_not_found", re.compile(r"command not found|not recognized|is not recognized", re.I)),
    ]

    # A2: Build position map for resolution matching (file-aware, window-limited)
    entry_id_to_pos = {}
    for i, e in enumerate(entries):
        entry_id_to_pos[id(e)] = i

    patterns = []
    for tr in tool_results:
        if not tr.get("is_error", False):
            continue
        content = tr.get("content", "")[:500]
        tid = tr.get("tool_use_id", "")
        error_type = "unknown"
        for etype, regex in ERROR_TAXONOMY:
            if regex.search(content):
                error_type = etype
                break

        # A2: Resolution matching — find successful follow-up within 5 entries
        resolution = None
        error_file = os.path.basename(id_to_file.get(tid, ""))
        err_pos = entry_id_to_pos.get(id(tr), -1)
        if err_pos >= 0:
            for next_e in entries[err_pos + 1 : err_pos + 6]:
                if next_e.get("type") != "tool_result":
                    continue
                if next_e.get("is_error", False):
                    continue
                next_tid = next_e.get("tool_use_id", "")
                next_tool = id_to_tool.get(next_tid, "")
                next_file = os.path.basename(id_to_file.get(next_tid, ""))
                # File-aware: same file must match (or error had no file context)
                if next_tool in ("Edit", "Write", "Bash") and (
                    not error_file or next_file == error_file
                ):
                    resolution = {"tool": next_tool, "file": next_file}
                    break

        patterns.append({
            "type": error_type,
            "tool": id_to_tool.get(tid, ""),
            "file": error_file,
            "resolution": resolution,
        })

    return patterns[:5]


def _extract_pacs_from_sot(project_dir):
    """CM-1: Extract pACS min-score from SOT (read-only).

    P1 Compliance: Deterministic YAML/regex extraction.
    SOT Compliance: Read-only access.
    Returns: int or None.
    """
    if not project_dir:
        return None
    try:
        import yaml
        for sp in sot_paths(project_dir):
            if os.path.exists(sp) and not sp.endswith(".json"):
                with open(sp, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f.read())
                if isinstance(data, dict):
                    wf = data.get("workflow", {})
                    if isinstance(wf, dict):
                        pacs = wf.get("pacs", {})
                        if isinstance(pacs, dict) and "min_score" in pacs:
                            return pacs["min_score"]
    except Exception:
        pass
    return None


def extract_session_facts(session_id, trigger, project_dir, entries, token_estimate=0):
    """Extract deterministic session facts for knowledge-index.jsonl.

    P1 Compliance: All fields are deterministic extractions.
    No semantic inference, no heuristic judgment.
    """
    user_messages = [e for e in entries if e["type"] == "user_message"]
    tool_uses = [e for e in entries if e["type"] == "tool_use"]

    # First user message (C-2: expanded to 300 chars for richer cross-session context)
    user_task = ""
    if user_messages:
        # Skip system-injected messages
        for msg in user_messages:
            content = msg.get("content", "")
            if not (content.startswith("<") and ">" in content[:50]):
                user_task = content[:300]
                break

    # Last user instruction (deterministic) — 품질 최적화
    # 긴 세션에서 마지막 지시가 "현재 작업 상태"를 더 정확히 반영한다.
    last_instruction = ""
    if user_messages:
        for msg in reversed(user_messages):
            content = msg.get("content", "")
            if not (content.startswith("<") and ">" in content[:50]):
                if content[:300] != user_task:  # 첫 메시지와 동일하면 생략
                    last_instruction = content[:300]
                break

    # Modified files — unique paths from Write/Edit
    modified_files = sorted(set(
        tu.get("file_path", "") for tu in tool_uses
        if tu.get("tool_name") in ("Write", "Edit") and tu.get("file_path")
    ))

    # B2: Per-file modification metadata — tool type + edit count for change magnitude
    file_detail = {}
    for tu in tool_uses:
        tool_name = tu.get("tool_name", "")
        fp = tu.get("file_path", "")
        if tool_name in ("Write", "Edit") and fp:
            if fp not in file_detail:
                file_detail[fp] = {"tool": tool_name, "edits": 0}
            file_detail[fp]["edits"] += 1
            # Write overwrites; if both Write and Edit occurred, record Write
            if tool_name == "Write":
                file_detail[fp]["tool"] = "Write"

    # Read files — unique paths from Read
    read_files = sorted(set(
        tu.get("file_path", "") for tu in tool_uses
        if tu.get("tool_name") == "Read" and tu.get("file_path")
    ))

    # Tool usage counts (deterministic)
    tools_used = {}
    for tu in tool_uses:
        name = tu.get("tool_name", "unknown")
        tools_used[name] = tools_used.get(name, 0) + 1

    # CM-D + E-3: Tool sequence — consecutive distinct tool names (run-length compressed)
    # Captures work patterns like "Read→Read→Edit→Bash→Read→Edit" → "Read(2)→Edit→Bash→Read→Edit"
    tool_sequence_parts = []
    prev_tool = None
    count = 0
    for tu in tool_uses:
        name = tu.get("tool_name", "unknown")
        if name == prev_tool:
            count += 1
        else:
            if prev_tool:
                tool_sequence_parts.append(f"{prev_tool}({count})" if count > 1 else prev_tool)
            prev_tool = name
            count = 1
    if prev_tool:
        tool_sequence_parts.append(f"{prev_tool}({count})" if count > 1 else prev_tool)
    tool_sequence = "→".join(tool_sequence_parts[-30:])  # Last 30 segments to cap size

    # B-3: Phase detection — current dominant phase
    phase = detect_conversation_phase(tool_uses)

    # B-3: Primary language detection (deterministic — file extension counting)
    ext_counts = {}
    all_files = modified_files + read_files
    for fp in all_files:
        ext = os.path.splitext(fp)[1].lower()
        if ext:
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
    primary_language = ""
    if ext_counts:
        primary_language = max(ext_counts, key=ext_counts.get)

    # B-3: Phase transitions (multi-phase detection, with tool_count per phase)
    transitions = detect_phase_transitions(tool_uses)
    if len(transitions) > 1:
        phase_flow = " → ".join(
            f"{t[0]}({t[2]-t[1]})" for t in transitions
        )
    else:
        phase_flow = phase

    facts = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "project": project_dir,
        "user_task": user_task,
        "modified_files": modified_files,
        "modified_files_detail": file_detail,  # B2: per-file tool + edit count
        "read_files": read_files,
        "tools_used": tools_used,
        "trigger": trigger,
        "token_estimate": token_estimate,
        "phase": phase,
        "phase_flow": phase_flow,
        "primary_language": primary_language,
        "tool_sequence": tool_sequence,  # CM-D + E-3: work pattern analysis
    }

    # A4: Search tags — language-independent path-derived keywords for RLM probing
    all_paths = modified_files + read_files
    search_tags = extract_path_tags(all_paths)
    if search_tags:
        facts["tags"] = search_tags

    if last_instruction:
        facts["last_instruction"] = last_instruction

    # E7 + E2: Completion state and git summary (deterministic, reuses existing functions)
    completion = extract_completion_state(entries, project_dir)
    git_state = capture_git_state(project_dir, max_diff_chars=500)

    facts["completion_summary"] = {
        "total_tool_calls": completion["total_tool_calls"],
        "edit_success": completion["edit_success"],
        "edit_fail": completion["edit_fail"],
        "bash_success": completion["bash_success"],
        "bash_fail": completion["bash_fail"],
    }
    facts["git_summary"] = git_state.get("status", "")[:200]

    # E-4: final_status — deterministic session outcome classification
    total_fails = completion["edit_fail"] + completion["bash_fail"]
    total_success = completion["edit_success"] + completion["bash_success"]
    if total_fails == 0 and total_success > 0:
        facts["final_status"] = "success"
    elif total_fails > 0 and total_success > total_fails:
        facts["final_status"] = "incomplete"  # Some failures but mostly succeeded
    elif total_fails > 0:
        facts["final_status"] = "error"
    else:
        facts["final_status"] = "unknown"  # No edits/bash at all (read-only session)

    # Session duration (deterministic timestamp difference)
    timestamps = [e.get("timestamp", "") for e in entries if e.get("timestamp")]
    if len(timestamps) >= 2:
        facts["session_duration_entries"] = len(timestamps)

    # CM-1: Cross-session knowledge enrichment fields
    # 1. Design decisions — top 5 high-signal decisions for RLM probing
    assistant_texts = [e for e in entries if e["type"] == "assistant_text"]
    all_decisions = _extract_decisions(assistant_texts)
    high_signal = [d for d in all_decisions if not d.startswith("[intent]")]
    facts["design_decisions"] = high_signal[:5]

    # 2. Error patterns — classified Bash/Edit failures for cross-session learning
    error_patterns = _classify_error_patterns(entries)
    if error_patterns:
        facts["error_patterns"] = error_patterns

    # 3. pACS min-score — SOT에서 추출 (있는 경우, read-only)
    pacs_min = _extract_pacs_from_sot(project_dir)
    if pacs_min is not None:
        facts["pacs_min"] = pacs_min

    # 4. ULW mode detection — tag session for RLM cross-session queries
    ulw_state = detect_ulw_mode(entries)
    if ulw_state:
        facts["ulw_active"] = True

    return facts


def replace_or_append_session_facts(ki_path, facts):
    """Append session facts to knowledge-index.jsonl with session_id dedup.

    If an entry with the same session_id already exists, replaces it
    (later saves have more complete data — e.g., sessionend after threshold).

    A-1: Reads under shared lock, writes via atomic temp→rename under exclusive lock.
         Even if the process crashes mid-write, the original file is never corrupted.
    A-2: Empty/missing session_id skips dedup (appends as new unique entry).
    A-3: Empty session_id triggers UUID fallback to prevent unbounded dedup bypass.

    P1 Compliance: All operations are deterministic (JSON read/filter/write).
    SOT Compliance: Only called from save_context.py and _trigger_proactive_save.
    """
    session_id = facts.get("session_id", "")

    # A-3: Empty session_id fallback — generate UUID to enable dedup on retry
    if not session_id or session_id == "unknown":
        import uuid
        session_id = f"auto-{uuid.uuid4().hex[:12]}"
        facts["session_id"] = session_id

    # P1 Schema Validation: Ensure RLM-critical keys exist before write
    facts = _validate_session_facts(facts)

    parent_dir = os.path.dirname(ki_path)
    os.makedirs(parent_dir, exist_ok=True)

    # Use a dedicated lock file to separate read/write locking from the data file.
    # This avoids the truncate-then-write vulnerability entirely.
    lock_path = ki_path + ".lock"

    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            # Read existing entries (file may not exist yet)
            lines = []
            if os.path.exists(ki_path):
                try:
                    with open(ki_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except Exception:
                    pass

            # Filter out existing entry with same session_id (dedup)
            kept = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                    if entry.get("session_id") == session_id:
                        continue  # Remove old entry — will be replaced
                except json.JSONDecodeError:
                    kept.append(stripped + "\n")
                    continue
                kept.append(stripped + "\n")

            # Append new entry
            kept.append(json.dumps(facts, ensure_ascii=False) + "\n")

            # A-1: Atomic write — temp file + rename. If crash happens,
            # either old file or new file exists, never a half-written state.
            atomic_write(ki_path, "".join(kept))
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    except Exception:
        # Non-blocking fallback: append-only (no dedup, but no data loss)
        try:
            with open(ki_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(facts, ensure_ascii=False) + "\n")
        except Exception:
            pass


def cleanup_knowledge_index(snapshot_dir):
    """Rotate knowledge-index.jsonl to keep MAX_KNOWLEDGE_INDEX_ENTRIES entries.

    Deterministic: keeps the most recent N entries, removes oldest.
    """
    ki_path = os.path.join(snapshot_dir, "knowledge-index.jsonl")
    if not os.path.exists(ki_path):
        return

    try:
        lines = []
        with open(ki_path, "r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]

        if len(lines) <= MAX_KNOWLEDGE_INDEX_ENTRIES:
            return

        # Keep only the most recent entries
        trimmed = lines[-MAX_KNOWLEDGE_INDEX_ENTRIES:]
        atomic_write(ki_path, "".join(trimmed))
    except Exception:
        pass


def cleanup_session_archives(snapshot_dir):
    """Rotate session archives to keep MAX_SESSION_ARCHIVES files.

    Keeps most recent by modification time.
    """
    sessions_dir = os.path.join(snapshot_dir, "sessions")
    if not os.path.isdir(sessions_dir):
        return

    try:
        files = []
        for f in os.listdir(sessions_dir):
            if f.endswith(".md"):
                fpath = os.path.join(sessions_dir, f)
                files.append((fpath, os.path.getmtime(fpath)))

        if len(files) <= MAX_SESSION_ARCHIVES:
            return

        # Sort by mtime, newest first — remove oldest
        files.sort(key=lambda x: x[1], reverse=True)
        for fpath, _ in files[MAX_SESSION_ARCHIVES:]:
            try:
                os.unlink(fpath)
            except OSError:
                pass
    except Exception:
        pass
