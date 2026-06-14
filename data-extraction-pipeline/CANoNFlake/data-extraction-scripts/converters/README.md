# Dataset Converters (JSONL ➔ CSV)

This directory contains format converters to export the `CANonFlake` dataset from native nested JSON Lines (`.jsonl`) format to flat CSV format.

## Available Scripts

### `convert_jsonl_to_csv.py`
Converts `non_flaky_dataset.jsonl` into `non_flaky_dataset.csv`.
*   **JSON Packing:** Restores flat string representations of the nested JSON columns (`helper_methods_json` and `code_under_test_json`) using `json.dumps`.
*   **Header Ordering:** Enforces the exact 12-column schema ordering required for dataset merges.

**Execution:**
```powershell
python data-extraction-scripts/converters/convert_jsonl_to_csv.py
```
