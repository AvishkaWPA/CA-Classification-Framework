# Dataset Converters (CSV ⇄ JSONL)

This directory contains format converters to toggle the `CANonFlake` dataset between flat CSV format and nested JSON Lines (`.jsonl`) format.

## Available Scripts

### 1. `convert_csv_to_jsonl.py`
Converts `non_flaky_dataset.csv` into `non_flaky_dataset.jsonl`.
*   **JSON Unpacking:** During conversion, the stringified JSON columns (`flaky_helper_methods_json` and `flaky_code_under_test_json`) are automatically parsed using `json.loads` back into nested JSON objects/dictionaries. This ensures the output JSONL has clean nested structures instead of escaped strings.
*   **Default Null Handling:** Null or empty fields in the CSV are represented as empty dictionaries `{}` in the JSONL to match the CAFlake baseline.
*   **Data Types:** Maps the row `id` as a string type.

**Execution:**
```powershell
python data-extraction-scripts/converters/convert_csv_to_jsonl.py
```

---

### 2. `convert_jsonl_to_csv.py`
Converts `non_flaky_dataset.jsonl` back into `non_flaky_dataset.csv`.
*   **JSON Packing:** Restores flat string representations of the nested JSON columns (`flaky_helper_methods_json` and `flaky_code_under_test_json`) using `json.dumps`.
*   **Header Ordering:** Enforces the exact 10-column schema ordering required for dataset merges.

**Execution:**
```powershell
python data-extraction-scripts/converters/convert_jsonl_to_csv.py
```
