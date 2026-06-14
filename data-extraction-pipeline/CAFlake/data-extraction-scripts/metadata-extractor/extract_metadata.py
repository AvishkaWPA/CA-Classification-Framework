#!/usr/bin/env python3
import os
import csv
import sys
import argparse

# Allow importing config and utils from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import TEST_CONFIG_PATH, RESULT_DIR
from utils import (
    read_common_dataset,
    write_common_dataset,
    load_git_metadata,
    FLAKY_CATEGORY_FULL_NAMES
)

METADATA_HEADERS = [
    "id",
    "test_id",
    "flaky_category",
    "repo_url",
    "flaky_commit",
    "fixed_commit"
]

def run_metadata_extraction(limit=None):
    if not os.path.exists(TEST_CONFIG_PATH):
        print(f"Error: test_config.csv not found at {TEST_CONFIG_PATH}")
        return
        
    git_meta_map = load_git_metadata()
    print(f"Loaded git metadata mappings for {len(git_meta_map)} projects.")
    
    with open(TEST_CONFIG_PATH, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        test_configs = list(reader)
    
    print(f"Found {len(test_configs)} tests in test_config.csv.")
    
    existing_rows = read_common_dataset()
    dataset_by_id = {row["test_id"]: row for row in existing_rows if "test_id" in row}
    
    processed_count = 0
    updated_rows = []
    
    for idx, config in enumerate(test_configs):
        if limit is not None and processed_count >= limit:
            break
            
        test_id = config.get("result_container", "").strip()
        zip_name = config.get("zip", "").strip()
        test_type = config.get("test_type", "").strip()
        
        test_result_dir = os.path.join(RESULT_DIR, test_id)
        if not os.path.exists(test_result_dir):
            found = False
            if os.path.exists(RESULT_DIR):
                for d in os.listdir(RESULT_DIR):
                    if d.lower() == test_id.lower():
                        test_result_dir = os.path.join(RESULT_DIR, d)
                        found = True
                        break
            if not found:
                continue
                
        print(f"Processing Metadata ({processed_count+1}/{limit if limit else len(test_configs)}): {test_id}...")
        
        meta = git_meta_map.get(test_id, git_meta_map.get(zip_name, {"repo_url": "", "flaky_commit": "", "fixed_commit": ""}))
        row = dataset_by_id.get(test_id, {col: "" for col in METADATA_HEADERS})
        full_category = FLAKY_CATEGORY_FULL_NAMES.get(test_type.lower(), "")
        
        row.update({
            "id": processed_count + 1,
            "test_id": test_id,
            "flaky_category": full_category,
            "repo_url": meta["repo_url"],
            "flaky_commit": meta["flaky_commit"],
            "fixed_commit": meta["fixed_commit"]
        })
        
        filtered_row = {col: row.get(col, "") for col in METADATA_HEADERS}
        updated_rows.append(filtered_row)
        processed_count += 1
        
    write_common_dataset(updated_rows, METADATA_HEADERS)
    print(f"Successfully processed and updated {len(updated_rows)} metadata records in common CSV.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CAFlake Stage 1: Metadata Extractor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=0,
        help="Limit the number of processed test cases. Set to 0 for no limit."
    )
    args = parser.parse_args()
    
    limit_val = None if args.limit <= 0 else args.limit
    run_metadata_extraction(limit=limit_val)
