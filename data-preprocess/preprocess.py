#!/usr/bin/env python3
import os
import re
import json
import csv
import argparse
from collections import defaultdict

def strip_comments_and_javadoc(code: str) -> str:
    """
    Removes Javadoc, block, and line comments from Java code to reduce token size.
    """
    if not code:
        return ""
    # Remove Javadoc and block comments (/* ... */)
    code = re.sub(r'/\*\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    # Remove inline comments (// ...)
    code = re.sub(r'//.*', '', code)
    # Remove redundant empty lines
    lines = [line for line in code.splitlines() if line.strip()]
    return "\n".join(lines)

def simplify_json_keys(nested_json: dict) -> dict:
    """
    Simplifies fully qualified class names (FQNs) to simple class names
    to reduce token size.
    """
    if not nested_json or not isinstance(nested_json, dict):
        return {}
    simplified = {}
    for fqn, methods in nested_json.items():
        simple_name = fqn.split(".")[-1]
        simplified[simple_name] = methods
    return simplified

def clean_and_trim_stack_trace(trace: str, keep_frames: int = 15) -> str:
    """
    Strips 'Failed Rounds: X/Y' header to prevent data leakage.
    Filters out reflection and framework frames, keeping only the exception details
    and application/test frames. Caps at `keep_frames` frames.
    """
    if not trace:
        return ""
    lines = trace.splitlines()
    filtered_lines = []
    
    # Noise packages to filter
    noise_prefixes = (
        "\tat sun.reflect",
        "\tat java.lang.reflect",
        "\tat org.junit",
        "\tat junit.framework",
        "\tat org.mockito",
        "\tat org.gradle",
        "\tat org.apache.maven.surefire"
    )
    
    for line in lines:
        stripped = line.strip()
        # Remove 'Failed Rounds:' lines
        if stripped.startswith("Failed Rounds:"):
            continue
        # Remove JVM/Framework reflection frames
        if stripped.startswith("at "):
            if any(line.startswith(p) for p in noise_prefixes):
                continue
        filtered_lines.append(line)
        
    # Cap frames
    if len(filtered_lines) > keep_frames:
        filtered_lines = filtered_lines[:keep_frames] + ["\t... [truncated framework frames]"]
        
    return "\n".join(filtered_lines)

def preprocess_row(row: dict) -> dict:
    """
    Applies comment removal, package simplification, and log cleaning to a single record.
    """
    # Clean test code
    row["test_code"] = strip_comments_and_javadoc(row.get("test_code", ""))
    
    # Clean helper methods
    helpers = row.get("helper_methods_json", {})
    if isinstance(helpers, str):
        try:
            helpers = json.loads(helpers)
        except Exception:
            helpers = {}
    if isinstance(helpers, dict):
        cleaned_helpers = {}
        for m_name, body in helpers.items():
            cleaned_helpers[m_name] = strip_comments_and_javadoc(body)
        row["helper_methods_json"] = cleaned_helpers
    else:
        row["helper_methods_json"] = {}
        
    # Clean failure log
    row["failure_log"] = clean_and_trim_stack_trace(row.get("failure_log", ""))
    
    # Clean code under test
    cut = row.get("code_under_test_json", {})
    if isinstance(cut, str):
        try:
            cut = json.loads(cut)
        except Exception:
            cut = {}
    if isinstance(cut, dict):
        simplified_cut = simplify_json_keys(cut)
        cleaned_cut = {}
        for cls_name, methods in simplified_cut.items():
            cleaned_methods = {}
            for m_name, body in methods.items():
                cleaned_methods[m_name] = strip_comments_and_javadoc(body)
            cleaned_cut[cls_name] = cleaned_methods
        row["code_under_test_json"] = cleaned_cut
    else:
        row["code_under_test_json"] = {}
        
    return row

def perform_group_split(records: list):
    """
    Groups records by repo_url and distributes them to train/val/test splits
    (70% / 15% / 15%) in a stratified manner to prevent data leakage.
    """
    # Group records by repo_url
    repo_groups = defaultdict(list)
    for r in records:
        repo_groups[r.get("repo_url", "unknown")].append(r)
        
    # Sort repos by total size descending
    sorted_repos = sorted(repo_groups.items(), key=lambda x: len(x[1]), reverse=True)
    
    train_records = []
    val_records = []
    test_records = []
    
    target_train_ratio = 0.70
    target_val_ratio = 0.15
    target_test_ratio = 0.15
    
    total_samples = len(records)
    
    # Greedy allocation of groups
    for repo, group in sorted_repos:
        curr_total = len(train_records) + len(val_records) + len(test_records)
        if curr_total == 0:
            train_records.extend(group)
            continue
            
        train_p = len(train_records) / total_samples
        val_p = len(val_records) / total_samples
        test_p = len(test_records) / total_samples
        
        # Calculate deficits relative to targets
        train_deficit = target_train_ratio - train_p
        val_deficit = target_val_ratio - val_p
        test_deficit = target_test_ratio - test_p
        
        # Allocate to split with largest deficit
        max_deficit = max(train_deficit, val_deficit, test_deficit)
        if max_deficit == train_deficit:
            train_records.extend(group)
        elif max_deficit == val_deficit:
            val_records.extend(group)
        else:
            test_records.extend(group)
            
    print(f"\n--- Group-Based Split Statistics ---")
    print(f"Total Rows: {total_samples}")
    print(f"  - Train Split: {len(train_records)} rows ({len(train_records)/total_samples*100:.2f}%)")
    print(f"  - Val Split:   {len(val_records)} rows ({len(val_records)/total_samples*100:.2f}%)")
    print(f"  - Test Split:  {len(test_records)} rows ({len(test_records)/total_samples*100:.2f}%)")
    
    # Assert no overlaps
    train_ids = {r["id"] for r in train_records}
    val_ids = {r["id"] for r in val_records}
    test_ids = {r["id"] for r in test_records}
    assert len(train_ids & val_ids) == 0, "Overlap found between train and val"
    assert len(train_ids & test_ids) == 0, "Overlap found between train and test"
    assert len(val_ids & test_ids) == 0, "Overlap found between val and test"
    print("Verification complete: No data leakage (overlap) between train/val/test splits.")
    
    return train_records, val_records, test_records

def export_to_csv(records: list, output_csv_path: str):
    """
    Saves records back to CSV format, stringifying nested JSON fields.
    """
    headers = [
        "id", "test_id", "isFlaky", "issue_category", "repo_url",
        "issue_commit", "flaky_commit", "fixed_commit",
        "test_code", "helper_methods_json", "failure_log", "code_under_test_json"
    ]
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in records:
            csv_row = {}
            for col in headers:
                val = row.get(col, "")
                if col in ("helper_methods_json", "code_under_test_json") and isinstance(val, (dict, list)):
                    csv_row[col] = json.dumps(val, ensure_ascii=False) if val else ""
                else:
                    csv_row[col] = val
            writer.writerow(csv_row)

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_input = os.path.abspath(os.path.join(script_dir, "..", "data-extraction-pipeline", "context_augmented_dataset.jsonl"))
    
    parser = argparse.ArgumentParser(description="Dataset Preprocessor for LLM-based classification")
    parser.add_argument("--input", "-i", default=default_input, help="Path to input context_augmented_dataset.jsonl")
    parser.add_argument("--output-dir", "-o", default=script_dir, help="Directory to save output files")
    parser.add_argument("--split", "-s", action="store_true", help="Generate train/val/test stratified splits")
    args = parser.parse_args()
    
    print("=== Data Preprocessing Pipeline ===")
    print(f"Reading input JSONL: {args.input}")
    if not os.path.exists(args.input):
        print(f"Error: Input file does not exist at {args.input}. Please run the extraction pipeline merger first.")
        return
        
    records = []
    filtered_count = 0
    
    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            
            # Discard row if missing test code, failure logs, or CUT
            test_code = row.get("test_code", "").strip()
            failure_log = row.get("failure_log", "").strip()
            cut = row.get("code_under_test_json")
            
            # Unpack CUT if stringified
            if isinstance(cut, str):
                try:
                    cut = json.loads(cut)
                except Exception:
                    cut = {}
                    
            if not test_code or not failure_log or not cut:
                filtered_count += 1
                continue
                
            processed_row = preprocess_row(row)
            records.append(processed_row)
            
    print(f"Loaded and preprocessed {len(records)} records (filtered out {filtered_count} incomplete records).")
    
    # Save full cleaned dataset
    clean_jsonl = os.path.join(args.output_dir, "preprocessed_dataset.jsonl")
    clean_csv = os.path.join(args.output_dir, "preprocessed_dataset.csv")
    
    print(f"Writing full cleaned dataset to: {clean_jsonl}")
    with open(clean_jsonl, "w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            
    print(f"Exporting full cleaned CSV to: {clean_csv}")
    export_to_csv(records, clean_csv)
    
    # Perform splitting if requested
    if args.split:
        train, val, test = perform_group_split(records)
        
        # Save JSONLs
        for name, split_records in [("train", train), ("val", val), ("test", test)]:
            jsonl_out = os.path.join(args.output_dir, f"{name}.jsonl")
            csv_out = os.path.join(args.output_dir, f"{name}.csv")
            
            print(f"Saving split [{name}] to {jsonl_out}")
            with open(jsonl_out, "w", encoding="utf-8") as f:
                for row in split_records:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            
            print(f"Exporting split [{name}] CSV to {csv_out}")
            export_to_csv(split_records, csv_out)
            
    print("Preprocessing completed successfully.")

if __name__ == "__main__":
    main()
