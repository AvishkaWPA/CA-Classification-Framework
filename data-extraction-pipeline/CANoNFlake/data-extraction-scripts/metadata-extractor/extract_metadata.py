#!/usr/bin/env python3
import os
import csv
import sys
import argparse

# Allow importing config and utils from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import PROJECTS_DIR, GITHUB_URLS
from utils import read_common_dataset, write_common_dataset, parse_trigger_file

# All 10 final columns — exact match with context_enriched_dataset.csv
# Later-stage columns are pre-populated as empty strings in Stage 1
METADATA_HEADERS = [
    "id",
    "test_id",
    "isFlaky",
    "issue_category",
    "repo_url",
    "issue_commit",
    "fixed_commit",
    "test_code",
    "helper_methods_json",
    "failure_log",
    "code_under_test_json",
]

def load_active_bugs(project_path):
    # Reads active-bugs.csv for a project.
    # Returns a list of dicts: {bug_id, buggy_commit, fixed_commit}
    bugs = []
    csv_path = os.path.join(project_path, "active-bugs.csv")
    if not os.path.exists(csv_path):
        return bugs
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bugs.append({
                "bug_id":        row["bug.id"].strip(),
                "buggy_commit":  row["revision.id.buggy"].strip(),
                "fixed_commit":  row["revision.id.fixed"].strip(),
            })
    return bugs

def build_test_id(project, bug_id, method_index, total_methods):
    # Builds a unique test_id string.
    # Single method bug  → "Lang-1"
    # Multi-method bug   → "Chart-14-1", "Chart-14-2", ...
    if total_methods == 1:
        return f"{project}-{bug_id}"
    return f"{project}-{bug_id}-{method_index}"

def run_metadata_extraction(limit=None, force=False):
    # Load what is already in the CSV (to support incremental runs)
    existing_rows = read_common_dataset()
    existing_ids = {row["test_id"] for row in existing_rows if "test_id" in row}

    all_projects = sorted([
        p for p in os.listdir(PROJECTS_DIR)
        if os.path.isdir(os.path.join(PROJECTS_DIR, p))
    ])

    print(f"Found {len(all_projects)} projects in {PROJECTS_DIR}")
    print()

    updated_rows = []
    global_id = 1
    processed_count = 0

    for project in all_projects:
        repo_url = GITHUB_URLS.get(project)
        if not repo_url:
            print(f"  Skipping {project}: no GitHub URL in config.")
            continue

        proj_path = os.path.join(PROJECTS_DIR, project)
        bugs = load_active_bugs(proj_path)
        trigger_dir = os.path.join(proj_path, "trigger_tests")

        print(f"Processing project: {project} ({len(bugs)} bugs)")

        for bug in bugs:
            if limit is not None and processed_count >= limit:
                break

            bug_id = bug["bug_id"]
            trigger_path = os.path.join(trigger_dir, bug_id)

            # Parse all failing methods from trigger_tests/[bug_id]
            entries = parse_trigger_file(trigger_path)
            if not entries:
                print(f"  Warning: No trigger test entries found for {project}-{bug_id}, skipping.")
                continue

            total_methods = len(entries)

            for method_index, (test_class, test_method, _failure_log) in enumerate(entries, start=1):
                if limit is not None and processed_count >= limit:
                    break

                test_id = build_test_id(project, bug_id, method_index, total_methods)

                # Skip if already extracted and not forcing overwrite
                if test_id in existing_ids and not force:
                    continue

                # Build row with exact 10-column schema matching context_enriched_dataset.csv
                # Later-stage columns left empty — filled by Stages 2, 3, 4
                row = {
                    "id":                       global_id,
                    "test_id":                  test_id,
                    "isFlaky":                  0,
                    "issue_category":           "Non-Flaky",
                    "repo_url":                 repo_url,
                    "issue_commit":             bug["buggy_commit"],
                    "fixed_commit":             bug["fixed_commit"],
                    "test_code":                "",
                    "helper_methods_json":      "",
                    "failure_log":              "",
                    "code_under_test_json":     "",
                }

                updated_rows.append(row)
                global_id += 1
                processed_count += 1

                print(f"  ({processed_count}{f'/{limit}' if limit else ''})"
                      f" {test_id}: {test_class}::{test_method}")

        if limit is not None and processed_count >= limit:
            break

    write_common_dataset(updated_rows, METADATA_HEADERS)
    print()
    print(f"Stage 1 complete. Extracted {len(updated_rows)} metadata records.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CANonFlake Stage 1: Metadata Extractor (from Defects4J)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=0,
        help="Limit the number of processed records. Set to 0 for no limit."
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force overwrite of already-extracted records."
    )
    args = parser.parse_args()

    limit_val = None if args.limit <= 0 else args.limit
    run_metadata_extraction(limit=limit_val, force=args.force)
