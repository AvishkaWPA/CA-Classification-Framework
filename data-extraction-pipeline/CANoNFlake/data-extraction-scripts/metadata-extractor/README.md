# Stage 1 — Metadata Extractor

This module is responsible for the initial bootstrapping of the dataset. It extracts static metadata and populates the first 6 columns of the shared `non_flaky_dataset.csv`.

## How It Works

1. **Project Scan:** Scans all Defects4J framework folders under `framework/projects/` to discover active Java projects (e.g., Lang, Math, Chart, Cli).
2. **Active Bugs:** Reads the `active-bugs.csv` file for each project to get:
   - The bug ID.
   - The Git SHA of the buggy commit (`revision.id.buggy` mapped to `flaky_commit`).
   - The Git SHA of the fixed commit (`revision.id.fixed` mapped to `fixed_commit`).
3. **Failing Tests Identification:** Parses the `trigger_tests/` directory files for each bug to identify all individual failing test methods.
4. **Unique ID Construction:** 
   - Single-method bugs are named: `[Project]-[BugID]` (e.g., `Lang-1`).
   - Multi-method bugs are suffixed with a 1-based index: `[Project]-[BugID]-[Index]` (e.g., `Chart-14-1`, `Chart-14-2`).
5. **CSV Creation:** Pre-populates the 10-column schema with `flaky_category` set to `"Non-Flaky"`, the project's GitHub repository URL from `config.py`, and empty values for later extraction phases.

## Execution

To extract the metadata:
```powershell
python data-extraction-scripts/metadata-extractor/extract_metadata.py
```

### CLI Arguments:
*   `--limit`, `-l`: Limit the number of processed test cases (e.g., `--limit 10` for testing).
*   `--force`, `-f`: Overwrite existing CSV rows instead of checking for duplicates.
