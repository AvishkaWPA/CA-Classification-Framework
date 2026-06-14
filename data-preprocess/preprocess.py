#!/usr/bin/env python3
import os
import re
import json
import csv
import argparse
import random

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
    to reduce token size. E.g. "org.apache...NumberUtils" -> "NumberUtils"
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
    
    parser = argparse.ArgumentParser(description="Dataset Preprocessor to generate a class-balanced dataset")
    parser.add_argument("--input", "-i", default=default_input, help="Path to input context_augmented_dataset.jsonl")
    parser.add_argument("--output-dir", "-o", default=script_dir, help="Directory to save output files")
    parser.add_argument("--seed", "-s", type=int, default=42, help="Random seed for reproducible balancing")
    args = parser.parse_args()
    
    print("=== Data Preprocessing & Balancing Pipeline ===")
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
    
    # Balancing classes via reproducible downsampling
    random.seed(args.seed)
    
    flaky_records = [r for r in records if int(r.get("isFlaky", 0)) == 1]
    non_flaky_records = [r for r in records if int(r.get("isFlaky", 0)) == 0]
    
    m = min(len(flaky_records), len(non_flaky_records))
    print(f"Balancing classes: minority class size is {m} (flaky={len(flaky_records)}, non-flaky={len(non_flaky_records)}).")
    
    if len(flaky_records) > len(non_flaky_records):
        sampled_flaky = random.sample(flaky_records, m)
        balanced_records = sampled_flaky + non_flaky_records
    else:
        sampled_non_flaky = random.sample(non_flaky_records, m)
        balanced_records = flaky_records + sampled_non_flaky
        
    # Re-sort by original id to preserve order
    balanced_records.sort(key=lambda x: x["id"])
    records = balanced_records
    print(f"Balanced dataset contains {len(records)} records ({m} flaky, {m} non-flaky).")
    
    # Save full cleaned and balanced dataset
    clean_jsonl = os.path.join(args.output_dir, "preprocessed_dataset.jsonl")
    clean_csv = os.path.join(args.output_dir, "preprocessed_dataset.csv")
    
    print(f"Writing balanced JSONL to: {clean_jsonl}")
    with open(clean_jsonl, "w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            
    print(f"Exporting balanced CSV to: {clean_csv}")
    export_to_csv(records, clean_csv)
    
    print("Preprocessing and class-balancing completed successfully.")

if __name__ == "__main__":
    main()
