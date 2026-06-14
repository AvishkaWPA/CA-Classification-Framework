import os
import json
import csv

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pipeline_dir = os.path.dirname(script_dir) # data-extraction-pipeline root
    
    nonflaky_jsonl = os.path.join(pipeline_dir, "CANoNFlake", "non_flaky_dataset.jsonl")
    flaky_jsonl = os.path.join(pipeline_dir, "CAFlake", "context_enriched_dataset.jsonl")
    output_jsonl = os.path.join(pipeline_dir, "context_augmented_dataset.jsonl")
    output_csv = os.path.join(pipeline_dir, "context_augmented_dataset.csv")
    
    print("=== Dataset Merger (JSONL-First) ===")
    print(f"Reading non-flaky JSONL from: {nonflaky_jsonl}")
    if not os.path.exists(nonflaky_jsonl):
        print(f"Error: Non-flaky dataset does not exist. Please run the CANoNFlake pipeline first.")
        return
        
    print(f"Reading flaky JSONL from: {flaky_jsonl}")
    if not os.path.exists(flaky_jsonl):
        print(f"Error: Flaky dataset does not exist. Please run the CAFlake pipeline first.")
        return
        
    records = []
    flaky_count = 0
    nonflaky_count = 0
    
    # Read CAFlake (flaky)
    with open(flaky_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                row["id"] = len(records) + 1
                records.append(row)
                flaky_count += 1
                
    # Read CANoNFlake (non-flaky)
    with open(nonflaky_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                row["id"] = len(records) + 1
                records.append(row)
                nonflaky_count += 1
                
    print(f"Loaded {nonflaky_count} non-flaky samples.")
    print(f"Loaded {flaky_count} flaky samples.")
    
    # Save output JSONL
    print(f"Writing merged JSONL to: {output_jsonl}")
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            
    # Print statistics
    print("\n--- Merging Statistics ---")
    print(f"Total combined rows: {len(records)}")
    print(f" - Flaky samples (isFlaky=1): {flaky_count} ({flaky_count / len(records) * 100:.2f}%)")
    print(f" - Non-flaky samples (isFlaky=0): {nonflaky_count} ({nonflaky_count / len(records) * 100:.2f}%)")
    
    # Export to CSV
    print(f"\nExporting to CSV at: {output_csv}")
    
    # 12-column headers
    headers = [
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
        "code_under_test_json"
    ]
    
    with open(output_csv, "w", newline="", encoding="utf-8") as f_csv:
        writer = csv.DictWriter(f_csv, fieldnames=headers)
        writer.writeheader()
        
        for row in records:
            # Copy row to avoid modifying original records list
            csv_row = {}
            for col in headers:
                val = row.get(col, "")
                # Convert helper methods and code under test back to stringified JSON for CSV
                if col in ("helper_methods_json", "code_under_test_json") and isinstance(val, (dict, list)):
                    if not val:
                        csv_row[col] = ""
                    else:
                        csv_row[col] = json.dumps(val, ensure_ascii=False)
                else:
                    csv_row[col] = val
            writer.writerow(csv_row)
            
    print("Export complete.")

if __name__ == "__main__":
    main()
