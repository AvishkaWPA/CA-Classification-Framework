import os
import csv
import json
import sys

# Set higher CSV field size limit to support large stack trace logs
csv.field_size_limit(2147483647)

# Append parent directory for config import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from config import COMMON_CSV_PATH
except ImportError:
    # Fallback to local path calculation if config cannot be imported
    WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    COMMON_CSV_PATH = os.path.join(WORKSPACE_ROOT, "CAFlake", "context_enriched_dataset.csv")

def convert_csv_to_jsonl(csv_path, jsonl_path):
    print(f"Reading CSV from: {csv_path}")
    if not os.path.exists(csv_path):
        print(f"Error: CSV file does not exist at {csv_path}")
        return
        
    records_count = 0
    with open(csv_path, mode='r', encoding='utf-8') as csv_file:
        reader = csv.DictReader(csv_file)
        
        with open(jsonl_path, mode='w', encoding='utf-8') as jsonl_file:
            for row in reader:
                # Convert the flaky_helper_methods_json and flaky_code_under_test_json
                # fields from stringified JSON back to raw JSON objects so the JSONL
                # contains clean nested structures instead of escaped strings.
                for json_col in ("flaky_helper_methods_json", "flaky_code_under_test_json"):
                    val = row.get(json_col, "").strip()
                    if val and val != "{}":
                        try:
                            row[json_col] = json.loads(val)
                        except json.JSONDecodeError:
                            # Keep as original string if parsing fails
                            pass
                    else:
                        row[json_col] = {}
                
                # Write record as a single JSON line
                jsonl_file.write(json.dumps(row, ensure_ascii=False) + '\n')
                records_count += 1
                
    print(f"Successfully converted {records_count} records to JSONL at: {jsonl_path}")

if __name__ == "__main__":
    csv_path = COMMON_CSV_PATH
    jsonl_path = csv_path.rsplit('.', 1)[0] + ".jsonl"
    convert_csv_to_jsonl(csv_path, jsonl_path)
