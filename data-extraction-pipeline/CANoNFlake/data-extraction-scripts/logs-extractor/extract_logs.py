#!/usr/bin/env python3
import os
import sys
import argparse

# Allow importing config and utils from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import PROJECTS_DIR
from utils import (
    read_common_dataset,
    write_common_dataset,
    parse_trigger_file,
)

# Shared 12-column dataset schema
LOGS_HEADERS = [
    "id",
    "test_id",
    "isFlaky",
    "issue_category",
    "repo_url",
    "issue_commit",
    "flaky_commit",
    "fixed_commit",
    "test_code",
    "helper_methods_json",
    "failure_log",
    "code_under_test_json",
]

def run_logs_extraction(limit=None, force=False):
    rows = read_common_dataset()
    if not rows:
        print("No rows found in non_flaky_dataset.csv. Run Stage 1 and 2 first.")
        return

    processed = 0
    skipped_no_trigger = set()

    for row in rows:
        if limit is not None and processed >= limit:
            break

        # Skip if already filled and not forcing
        if row.get("failure_log", "").strip() and not force:
            continue

        test_id = row.get("test_id", "")
        parts = test_id.split("-")
        project = parts[0]
        bug_id = parts[1]
        method_index = int(parts[2]) if len(parts) >= 3 else 1

        trigger_path = os.path.join(PROJECTS_DIR, project, "trigger_tests", bug_id)
        if not os.path.exists(trigger_path):
            if (project, bug_id) not in skipped_no_trigger:
                print(f"  Warning: Trigger file not found for {project}-{bug_id}")
                skipped_no_trigger.add((project, bug_id))
            continue

        entries = parse_trigger_file(trigger_path)
        if not entries:
            print(f"  Warning: Empty or unparseable trigger file for {test_id}")
            continue

        idx = method_index - 1
        if idx < 0 or idx >= len(entries):
            print(f"  Warning: Method index {method_index} out of bounds for {test_id} (found {len(entries)} entries)")
            continue

        # Extract failure log
        test_class, test_method, failure_log = entries[idx]

        # Format exactly like CAFlake: "Failed Rounds: 1/1\n[stacktrace]"
        formatted_log = f"Failed Rounds: 1/1\n{failure_log}"

        row["failure_log"] = formatted_log
        processed += 1

        if processed % 100 == 0:
            print(f"  Processed {processed} logs...")

    write_common_dataset(rows, LOGS_HEADERS)
    print()
    print(f"Stage 3 complete. Extracted failure logs for {processed} records.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CANonFlake Stage 3: Failure Log Extractor (from Defects4J trigger_tests)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--limit", "-l",
        type=int, default=0,
        help="Limit number of records to process. 0 = no limit."
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force re-extraction of already-filled rows."
    )
    args = parser.parse_args()
    limit_val = None if args.limit <= 0 else args.limit
    run_logs_extraction(limit=limit_val, force=args.force)
