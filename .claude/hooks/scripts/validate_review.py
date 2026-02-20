#!/usr/bin/env python3
"""
Adversarial Review P1 Validation — validate_review.py

Standalone script called by Orchestrator after review sub-agent completes.
NOT a Hook — manually invoked during workflow execution.

Usage:
    python3 .claude/hooks/scripts/validate_review.py --step 3 --project-dir .

Output: JSON to stdout
    {"valid": true, "verdict": "PASS", "critical_count": 0, ...}

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
    validate_review_output,
    parse_review_verdict,
    calculate_pacs_delta,
    validate_review_sequence,
)


def main():
    parser = argparse.ArgumentParser(
        description="P1 Validation for Adversarial Review outputs"
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
        help="Also validate review→translation sequence"
    )
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    step = args.step

    # Core validation: Anti-Skip Guard for review output
    is_valid, verdict, issues_count, warnings = validate_review_output(
        project_dir, step
    )

    # Detailed verdict parsing
    review_path = os.path.join(
        project_dir, "review-logs", f"step-{step}-review.md"
    )
    verdict_data = parse_review_verdict(review_path)

    # pACS delta calculation
    pacs_data = calculate_pacs_delta(project_dir, step)

    # Build output
    output = {
        "valid": is_valid,
        "step": step,
        "verdict": verdict,
        "issues_count": issues_count,
        "critical_count": verdict_data["critical_count"],
        "warning_count": verdict_data["warning_count"],
        "suggestion_count": verdict_data["suggestion_count"],
        "reviewer_pacs": verdict_data["reviewer_pacs"],
        "pacs_dimensions": verdict_data["pacs_dimensions"],
        "generator_pacs": pacs_data["generator_score"],
        "pacs_delta": pacs_data["delta"],
        "needs_reconciliation": pacs_data["needs_reconciliation"],
        "warnings": warnings,
    }

    # Optional: sequence validation
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
