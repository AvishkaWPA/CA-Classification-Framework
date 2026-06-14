import os
import pandas as pd

def main():
    # Define paths relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pipeline_dir = os.path.dirname(script_dir) # data-extraction-pipeline root
    
    nonflaky_path = os.path.join(pipeline_dir, "CANoNFlake", "non_flaky_dataset.csv")
    flaky_path = os.path.join(pipeline_dir, "CAFlake", "context_enriched_dataset.csv")
    output_path = os.path.join(pipeline_dir, "binary_classification_dataset.csv")
    
    print("=== Dataset Merger ===")
    print(f"Reading non-flaky dataset from: {nonflaky_path}")
    if not os.path.exists(nonflaky_path):
        print(f"Error: Non-flaky dataset does not exist. Please run the CANoNFlake pipeline first.")
        return
        
    print(f"Reading flaky dataset from: {flaky_path}")
    if not os.path.exists(flaky_path):
        print(f"Error: Flaky dataset does not exist. Please run the CAFlake pipeline first.")
        return
        
    # Read datasets
    nonflaky_df = pd.read_csv(nonflaky_path, low_memory=False)
    flaky_df = pd.read_csv(flaky_path, low_memory=False)
    
    print(f"Loaded {len(nonflaky_df)} non-flaky samples.")
    print(f"Loaded {len(flaky_df)} flaky samples.")
    
    # Verify columns match
    nonflaky_cols = list(nonflaky_df.columns)
    flaky_cols = list(flaky_df.columns)
    if nonflaky_cols != flaky_cols:
        print("Warning: Columns do not match exactly in order or names.")
        print(f" - Non-flaky columns: {nonflaky_cols}")
        print(f" - Flaky columns: {flaky_cols}")
        
    # Combine datasets
    combined = pd.concat([flaky_df, nonflaky_df], ignore_index=True)
    
    # Set label: 1 for flaky (flaky_category != "Non-Flaky"), 0 for non-flaky
    combined["label"] = (combined["flaky_category"] != "Non-Flaky").astype(int)
    
    # Re-sequence id to be unique and continuous from 1 to N
    combined["id"] = range(1, len(combined) + 1)
    
    # Save the output CSV
    print(f"Writing combined dataset to: {output_path}")
    combined.to_csv(output_path, index=False)
    
    # Print statistics
    print("\n--- Merging Statistics ---")
    print(f"Total combined rows: {len(combined)}")
    flaky_count = (combined["label"] == 1).sum()
    nonflaky_count = (combined["label"] == 0).sum()
    print(f" - Flaky samples (label=1): {flaky_count} ({flaky_count / len(combined) * 100:.2f}%)")
    print(f" - Non-flaky samples (label=0): {nonflaky_count} ({nonflaky_count / len(combined) * 100:.2f}%)")
    
    # Output file paths for jsonl if they exist
    nonflaky_jsonl = nonflaky_path.rsplit('.', 1)[0] + ".jsonl"
    flaky_jsonl = flaky_path.rsplit('.', 1)[0] + ".jsonl"
    output_jsonl = output_path.rsplit('.', 1)[0] + ".jsonl"
    
    if os.path.exists(nonflaky_jsonl) and os.path.exists(flaky_jsonl):
        print(f"\nFound JSONL formats. Creating combined JSONL at: {output_jsonl}")
        # Merge JSONLs
        records_count = 0
        with open(output_jsonl, "w", encoding="utf-8") as f_out:
            # Read flaky jsonl
            with open(flaky_jsonl, "r", encoding="utf-8") as f_flaky:
                for line in f_flaky:
                    if line.strip():
                        import json
                        row = json.loads(line)
                        row["label"] = 1
                        row["id"] = str(records_count + 1)
                        f_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        records_count += 1
            # Read non-flaky jsonl
            with open(nonflaky_jsonl, "r", encoding="utf-8") as f_nonflaky:
                for line in f_nonflaky:
                    if line.strip():
                        import json
                        row = json.loads(line)
                        row["label"] = 0
                        row["id"] = str(records_count + 1)
                        f_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        records_count += 1
        print(f"Successfully converted {records_count} records to JSONL.")

if __name__ == "__main__":
    main()
