# CANonFlake — Non-Flaky Test Failure Dataset

## Overview

**CANonFlake** is a companion dataset to **CAFlake**, providing deterministic (non-flaky) test failure samples extracted from the [Defects4J](https://github.com/rjust/defects4j) benchmark. Together, both datasets form a balanced binary classification corpus for distinguishing **flaky test failures** from **genuine (non-flaky) test failures**.

| Dataset | Label | Source | Samples |
|---|---|---|---|
| `CAFlake/context_enriched_dataset.csv` | Flaky | ReproFlake containers | ~1,033 |
| `CANonFlake/non_flaky_dataset.csv` | Non-Flaky | Defects4J bugs | 1,779 |

> **Why Defects4J?** Every bug in Defects4J is verified to be *reproducible* and *deterministic* — it always fails on the buggy commit and always passes on the fixed commit. Bugs that exhibit non-deterministic (flaky) behaviour are explicitly deprecated. This guarantees clean non-flaky labels with zero execution required.

---

## Output Schema

The final `non_flaky_dataset.csv` uses the **exact same column schema** as `CAFlake/context_enriched_dataset.csv` so both files can be merged directly for classification.

| Column | Type | Filled By | Description |
|---|---|---|---|
| `id` | int | Stage 1 | Sequential row number |
| `test_id` | str | Stage 1 | Unique identifier e.g. `Lang-1`, `Chart-14-3` |
| `isFlaky` | int | Stage 1 | Binary classification label (`0` for non-flaky) |
| `issue_category` | str | Stage 1 | Always `"Non-Flaky"` |
| `repo_url` | str | Stage 1 | GitHub URL of the project |
| `issue_commit` | str | Stage 1 | Git SHA of the **buggy** commit |
| `flaky_commit` | str | Stage 1 | Duplicate/alias of `issue_commit` |
| `fixed_commit` | str | Stage 1 | Git SHA of the **fixed** commit |
| `test_code` | str | Stage 2 | Full source of the failing test method |
| `helper_methods_json` | JSON str | Stage 2 | JSON map of helper methods called by the test |
| `failure_log` | str | Stage 3 | Stack trace / failure output from the test run |
| `code_under_test_json` | JSON str | Stage 4 | JSON map of production methods exercised by the test |

> **Note on naming:** Column names match CAFlake's schema (e.g., duplicate `issue_commit` / `flaky_commit` is used to support both naming styles). The `isFlaky = 0` and `issue_category = "Non-Flaky"` distinguish the two classes.

---

## Pipeline

The dataset is built in **4 sequential stages**. Each stage reads `non_flaky_dataset.csv`, fills in its columns, and writes the file back.

```
Defects4J
framework/projects/[Project]/
├── active-bugs.csv          ─── Stage 1 ──▶ id, test_id, isFlaky, issue_category,
├── trigger_tests/[N]        ─── Stage 1 ──▶ repo_url, issue_commit, flaky_commit, fixed_commit
│                            ─── Stage 3 ──▶ failure_log
└── project_repos/[name].git ─── Stage 2 ──▶ test_code, helper_methods_json
                             ─── Stage 4 ──▶ code_under_test_json
```

### Stage 1 — Metadata Extraction ✅ Complete

**Script:** `data-extraction-scripts/metadata-extractor/extract_metadata.py`

**Requires:** Nothing (reads static CSV files only)

Reads `active-bugs.csv` and `trigger_tests/[N]` for all 17 Defects4J projects. Outputs one row per failing test method, pre-populating the 6 metadata columns and leaving later-stage columns empty.

```powershell
python data-extraction-scripts/metadata-extractor/extract_metadata.py
# Test with limit:
python data-extraction-scripts/metadata-extractor/extract_metadata.py --limit 20
# Force overwrite existing rows:
python data-extraction-scripts/metadata-extractor/extract_metadata.py --force
```

**Output:** 1,779 rows with `id`, `test_id`, `isFlaky`, `issue_category`, `repo_url`, `issue_commit`, `flaky_commit`, `fixed_commit` filled.

---

### Stage 2 — Test Code Extraction ✅ Complete

**Script:** `data-extraction-scripts/code-extractor/extract_codes.py`

**Requires:** Project Git repositories cloned into `project_repos/`

For each row, checks out the `flaky_commit` (buggy SHA) in the project's bare Git repo, locates the test class `.java` file using `dir-layout.csv`, and extracts the test method body and helper methods using brace-counting parser (reused from CAFlake).

```powershell
python data-extraction-scripts/code-extractor/extract_codes.py
```

**Output:** `test_code` and `helper_methods_json` filled.

---

### Stage 3 — Failure Log Extraction ✅ Complete

**Script:** `data-extraction-scripts/logs-extractor/extract_logs.py`

**Requires:** Nothing (pre-stored in `trigger_tests/` — no execution needed)

Re-reads `trigger_tests/[bug_id]` to extract the full stack trace for each test method. Uses `resolve_test_class_method()` to match the correct method block from the file using the `test_id`.

```powershell
python data-extraction-scripts/logs-extractor/extract_logs.py
```

**Output:** `failure_log` filled.

---

### Stage 4 — Code Under Test Extraction ✅ Complete

**Script:** `data-extraction-scripts/cut-extractor/extract_cut.py`

**Requires:** Project Git repos (same as Stage 2) + Stages 2 and 3 complete

Identifies production methods exercised by each test using a combination of:
1. **Stack trace parsing** — methods appearing in `failure_log`
2. **Static call analysis** — methods directly called in `test_code` and helper methods

Extracts the source bodies of those production methods from the buggy commit source tree.

```powershell
python data-extraction-scripts/cut-extractor/extract_cut.py
```

**Output:** `code_under_test_json` filled.

---

## Setup and Running the Pipeline

To run the pipeline from scratch and regenerate the `non_flaky_dataset.csv` and `non_flaky_dataset.jsonl` files, follow these steps:

### 1. Prerequisites and Setup
*   Ensure **Python 3.x** and **pandas** are installed.
*   The Defects4J framework folder must be present, with projects situated in `framework/projects/` and bare Git repositories cloned under `project_repos/`.

### 2. Running Extraction Stages
Execute the scripts sequentially from the `CANoNFlake` (or `defects4j/CANoNFlake`) directory:

```powershell
# Step 1: Bootstrap metadata from trigger tests and active bugs (Stage 1)
python data-extraction-scripts/metadata-extractor/extract_metadata.py

# Step 2: Extract test method and helper method bodies (Stage 2)
python data-extraction-scripts/code-extractor/extract_codes.py

# Step 3: Extract JUnit test failure stack trace logs (Stage 3)
python data-extraction-scripts/logs-extractor/extract_logs.py

# Step 4: Map and extract production code under test (Stage 4)
python data-extraction-scripts/cut-extractor/extract_cut.py
```


---

## Directory Structure

```
CANonFlake/
├── README.md                              ← This file
├── non_flaky_dataset.csv                  ← Shared CSV output
├── non_flaky_dataset.jsonl                 ← Shared JSONL output
└── data-extraction-scripts/
    ├── config.py                          ← D4J paths + GitHub URL table
    ├── utils.py                           ← Shared CSV I/O + trigger file parser
    ├── metadata-extractor/
    │   └── extract_metadata.py            ← Stage 1
    ├── code-extractor/
    │   └── extract_codes.py               ← Stage 2
    ├── logs-extractor/
    │   └── extract_logs.py                ← Stage 3
    ├── cut-extractor/
    │   └── extract_cut.py                 ← Stage 4
    └── converters/                        ← Format converters (JSONL ⇄ CSV)
        └── convert_jsonl_to_csv.py
```


---

## Key Design Notes

- **`test_id` encoding:** Single-method bugs use `[Project]-[bug_id]` (e.g., `Lang-1`). Multi-method bugs use `[Project]-[bug_id]-[index]` (e.g., `Chart-14-3`). The index is 1-based and identifies which entry in the `trigger_tests/[N]` file to use.

- **No `test_class`/`test_method` columns:** These are derived on-the-fly in each stage using `resolve_test_class_method(test_id, projects_dir)` from `utils.py` — keeping the CSV schema clean and identical to CAFlake.

- **Non-flaky guarantee:** All 854 Defects4J bugs are CI-verified reproducible. Bugs that showed flaky behaviour (e.g., `JacksonDatabind-65` — reason: `JVM11.flaky`) are explicitly deprecated in `active-bugs.csv` and excluded automatically.

- **Stage 3 requires no execution:** Defects4J pre-stores all failure logs in `trigger_tests/[N]`, so `flaky_failure_log` is extracted without re-running any tests.
