# CAFlake Dataset Extraction Commands

This document contains a reference list of all execution commands required to run the data extraction pipeline and format converter scripts.

---

## 🚀 Pipeline Steps (Run in Order)

Always run all commands from the **workspace root directory** (where `test_config.csv` resides).

### Stage 1: Metadata Extraction
Extracts basic metadata, repository URL, and flaky/fixed commit SHAs from JIRA/iDoFT tables.
```bash
python CAFlake/data-extraction-scripts/metadata-extractor/extract_metadata.py
```

### Stage 2: Flaky Test Code & Helper Methods Extraction
Locates test method bodies inside project source ZIPs, resolves class extends hierarchies, and extracts helper methods.
```bash
python CAFlake/data-extraction-scripts/code-extractor/extract_codes.py
```

### Stage 3: Failure Logs Extraction
Extracts failure stack traces and diagnostic logs from surefire reports or round results.
```bash
python CAFlake/data-extraction-scripts/logs-extractor/extract_logs.py
```

### Stage 4: Code Under Test (CUT) Extraction
Extracts production methods executed or called by the flaky test using dynamic coverage (Jacoco XML), stack traces, and static AST resolution.
```bash
python CAFlake/data-extraction-scripts/cut-extractor/extract_cut.py
```
*Optional flags:*
*   `--force` or `-f`: Overwrite already extracted CUT entries in the dataset.
*   `--limit <num>` or `-l <num>`: Process only up to a set number of records.

---

## 🔄 Format Converters

To prevent text truncation and layout shifting in traditional spreadsheets (like Microsoft Excel), you can convert the dataset format using these scripts.

### Convert CSV to JSON Lines (`.jsonl`)
Converts the CSV dataset into a clean JSON Lines format, restoring nested stringified JSON fields to native JSON objects.
```bash
python CAFlake/data-extraction-scripts/converters/convert_csv_to_jsonl.py
```

### Export JSON Lines back to CSV (`.csv`)
Regenerates the standard CSV dataset from the JSON Lines file.
```bash
python CAFlake/data-extraction-scripts/converters/convert_jsonl_to_csv.py
```
