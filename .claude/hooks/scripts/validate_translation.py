#!/usr/bin/env python3
"""
Translation P1 Validation — validate_translation.py

Standalone script called by Orchestrator after translator sub-agent completes.
NOT a Hook — manually invoked during workflow execution.

Usage:
    python3 .claude/hooks/scripts/validate_translation.py --step 3 --project-dir .

Output: JSON to stdout
    {"valid": true, "warnings": [], "glossary_valid": true, ...}

Exit codes:
    0 — validation completed (check "valid" field for result)
    1 — argument error or fatal failure

P1 Compliance: All validation is deterministic (delegates to _context_lib).
SOT Compliance: Read-only — no file writes.
"""

import argparse
import json
import os
import sys

# Add script directory to path for shared library import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _context_lib import (
    validate_translation_output,
    check_glossary_freshness,
    verify_pacs_arithmetic,
    validate_review_sequence,
)


def main():
    parser = argparse.ArgumentParser(
        description="P1 Validation for Translation outputs"
    )
    parser.add_argument(
        "--step", type=int, required=True,
        help="Step number to validate"
    )
    parser.add_argument(
        "--project-dir", type=str, default=".",
        help="Project root directory (default: current directory)"
    )
    parser.add_argument(
        "--check-sequence", action="store_true",
        help="Also validate review→translation sequence (T8 + timestamp)"
    )
    parser.add_argument(
        "--check-pacs", action="store_true",
        help="Also validate translation pACS arithmetic (T9)"
    )
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    step = args.step

    # Core validation: T1-T7
    is_valid, warnings = validate_translation_output(project_dir, step)

    # T8: Glossary freshness
    glossary_valid, glossary_warning = check_glossary_freshness(project_dir, step)

    # Build output
    output = {
        "valid": is_valid and glossary_valid,
        "step": step,
        "translation_valid": is_valid,
        "glossary_valid": glossary_valid,
        "warnings": list(warnings),  # ensure list copy
    }

    if glossary_warning:
        output["glossary_warning"] = glossary_warning
        output["warnings"].append(glossary_warning)

    # Optional: T9 — pACS arithmetic check
    if args.check_pacs:
        pacs_path = os.path.join(
            project_dir, "pacs-logs", f"step-{step}-translation-pacs.md"
        )
        pacs_valid, pacs_warning = verify_pacs_arithmetic(pacs_path)
        output["pacs_arithmetic_valid"] = pacs_valid
        if pacs_warning:
            output["pacs_arithmetic_warning"] = pacs_warning
            output["warnings"].append(pacs_warning)
            if not pacs_valid:
                output["valid"] = False

    # Optional: sequence validation (review PASS before translation)
    if args.check_sequence:
        seq_valid, seq_warning = validate_review_sequence(project_dir, step)
        output["sequence_valid"] = seq_valid
        if seq_warning:
            output["sequence_warning"] = seq_warning
            output["warnings"].append(seq_warning)
            if not seq_valid:
                output["valid"] = False

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_output = {
            "valid": False,
            "error": str(e),
            "warnings": [f"Fatal error: {e}"],
        }
        print(json.dumps(error_output, indent=2, ensure_ascii=False))
        sys.exit(1)
