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
    COMMON_CSV_PATH = os.path.join(WORKSPACE_ROOT, "CANoNFlake", "non_flaky_dataset.csv")

CUT_HEADERS = [
    "id",
    "test_id",
    "flaky_category",
    "repo_url",
    "flaky_commit",
    "fixed_commit",
    "flaky_test_code",
    "flaky_helper_methods_json",
    "flaky_failure_log",
    "flaky_code_under_test_json"
]

def convert_jsonl_to_csv(jsonl_path, csv_path):
    print(f"Reading JSONL from: {jsonl_path}")
    if not os.path.exists(jsonl_path):
        print(f"Error: JSONL file does not exist at {jsonl_path}")
        return
        
    records_count = 0
    with open(jsonl_path, mode='r', encoding='utf-8') as jsonl_file:
        with open(csv_path, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=CUT_HEADERS)
            writer.writeheader()
            
            for line in jsonl_file:
                if not line.strip():
                    continue
                row = json.loads(line)
                
                # Convert helper methods and code under test back to stringified JSON for CSV
                for json_col in ("flaky_helper_methods_json", "flaky_code_under_test_json"):
                    val = row.get(json_col)
                    if isinstance(val, (dict, list)):
                        # If empty, write empty string to match format, else serialize
                        if not val:
                            row[json_col] = ""
                        else:
                            row[json_col] = json.dumps(val, ensure_ascii=False)
                            
                writer.writerow(row)
                records_count += 1
                
    print(f"Successfully exported {records_count} records to CSV at: {csv_path}")

if __name__ == "__main__":
    csv_path = COMMON_CSV_PATH
    jsonl_path = csv_path.rsplit('.', 1)[0] + ".jsonl"
    convert_jsonl_to_csv(jsonl_path, csv_path)
