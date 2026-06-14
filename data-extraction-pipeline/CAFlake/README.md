# CAFlake — Context-Augmented Flaky Test Failure Dataset

## Overview

**CAFlake** is a structured dataset containing flaky test failure samples extracted from the [ReproFlake](https://github.com/PRL-PRG/ReproFlake) reproduction framework results. Together with its companion dataset, **CANonFlake**, both datasets form a balanced binary classification corpus for distinguishing **flaky test failures** from **genuine (non-flaky) test failures**.

| Dataset | Label | Source | Samples |
|---|---|---|---|
| `CAFlake/context_enriched_dataset.csv` | Flaky | ReproFlake containers | ~1,033 |
| `CANonFlake/non_flaky_dataset.csv` | Non-Flaky | Defects4J bugs | 1,638 |

> **Why ReproFlake?** ReproFlake reproduces documented flaky Java tests across multiple executions in Docker containers, classifying them into root causes (Implementation-Dependent, Order-Dependent, Non-Idempotent, Time-Dependent). CAFlake maps these verified flaky executions into structural context features.

---

## Output Schema

The final `context_enriched_dataset.csv` uses the exact same column schema as `CANonFlake/non_flaky_dataset.csv` so both files can be merged directly for classification.

| Column | Type | Filled By | Description |
|---|---|---|---|
| `id` | int | Stage 1 | Sequential row number |
| `test_id` | str | Stage 1 | Unique Defects4J/ReproFlake test identifier |
| `isFlaky` | int | Stage 1 | Binary classification label (`1` for flaky) |
| `issue_category` | str | Stage 1 | Category of flakiness: `Implementation Dependent`, `Order Dependent`, `Non-Idempotent`, `Time Dependent` |
| `repo_url` | str | Stage 1 | GitHub URL of the project |
| `issue_commit` | str | Stage 1 | Git SHA of the **buggy** (flaky) commit |
| `flaky_commit` | str | Stage 1 | Duplicate/alias of `issue_commit` |
| `fixed_commit` | str | Stage 1 | Git SHA of the **fixed** commit |
| `test_code` | str | Stage 2 | Full source of the failing test method |
| `helper_methods_json` | JSON str | Stage 2 | JSON map of helper methods called by the test |
| `failure_log` | str | Stage 3 | Deduplicated stack trace / failure output from flaky execution runs |
| `code_under_test_json` | JSON str | Stage 4 | JSON map of production methods covered and executed by the test |

---

## Pipeline

The dataset is built in **4 sequential stages**. Each stage reads `context_enriched_dataset.csv`, fills in its columns, and writes the file back.

```
ReproFlake
dataSource/reproFlake/
├── test_config.csv          ─── Stage 1 ──▶ id, test_id, isFlaky, issue_category,
├── research-data/           ─── Stage 1 ──▶ repo_url, issue_commit, flaky_commit, fixed_commit
├── result/[test_id]/        ─── Stage 3 ──▶ failure_log
│   └── surefire-reports/
└── data/[project].zip       ─── Stage 2 ──▶ test_code, helper_methods_json
                             ─── Stage 4 ──▶ code_under_test_json
```

### Stage 1 — Metadata Extraction ✅ Complete

**Script:** `data-extraction-scripts/metadata-extractor/extract_metadata.py`

**Requires:** `test_config.csv` and `research-data/` maps under `dataSource/reproFlake/`.

Parses config records and cross-references JIRA/iDoFT tables to extract commit SHAs, URLs, and basic test run statistics.

```powershell
python data-extraction-scripts/metadata-extractor/extract_metadata.py
```

---

### Stage 2 — Test Code Extraction ✅ Complete

**Script:** `data-extraction-scripts/code-extractor/extract_codes.py`

**Requires:** Project source zip files under `dataSource/reproFlake/data/`.

Locates test class files inside zipped project sources, parses out test method bodies using brace-matching, and recursively extracts referenced local helper methods called by the test.

```powershell
python data-extraction-scripts/code-extractor/extract_codes.py
```

**Output:** `test_code` and `helper_methods_json` filled.

---

### Stage 3 — Failure Log Extraction ✅ Complete

**Script:** `data-extraction-scripts/logs-extractor/extract_logs.py`

**Requires:** Surefire reports inside execution results at `dataSource/reproFlake/result/`.

Scans execution rounds inside the surefire reports directories. It extracts the raw stack trace failure output, deduplicates identical failure traces across rounds, and formats them with a `Failed Rounds: X/Y` header.

```powershell
python data-extraction-scripts/logs-extractor/extract_logs.py
```

**Output:** `failure_log` filled.

---

### Stage 4 — Code Under Test Extraction ✅ Complete

**Script:** `data-extraction-scripts/cut-extractor/extract_cut.py`

**Requires:** Project source zips + Stages 2 and 3 complete.

Reads Jacoco dynamic coverage mappings to identify covered class candidates, locates class source files in ZIP directories, and extracts the bodies of production methods executed by the test.

```powershell
python data-extraction-scripts/cut-extractor/extract_cut.py
```

**Output:** `code_under_test_json` filled.

---

## Setup and Running the Pipeline

To run the pipeline from scratch and regenerate the `context_enriched_dataset.csv` and `context_enriched_dataset.jsonl` files:

### 1. Prerequisites and Setup
Ensure **Python 3.x** and **pandas** are installed. Central data sources must be placed in `dataSource/reproFlake/`.

### 2. Running Extraction Stages
Execute the scripts sequentially from the module directory:

```powershell
# Step 1: Extract basic metadata
python data-extraction-scripts/metadata-extractor/extract_metadata.py

# Step 2: Extract test method and helper code
python data-extraction-scripts/code-extractor/extract_codes.py

# Step 3: Extract failure stack trace logs
python data-extraction-scripts/logs-extractor/extract_logs.py

# Step 4: Extract Code Under Test (CUT)
python data-extraction-scripts/cut-extractor/extract_cut.py
```

---

## Directory Structure

```
CAFlake/
├── README.md                              ← This file
├── context_enriched_dataset.csv          ← Shared CSV output
├── context_enriched_dataset.jsonl         ← Shared JSONL output
└── data-extraction-scripts/
    ├── config.py                          ← Path configurations
    ├── utils.py                           ← Shared utility library
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

*   **`test_id` mapping:** Connects test cases directly to their ReproFlake replication containers.
*   **Log Deduplication:** Because flaky tests fail non-deterministically, the log extraction scans multiple execution runs and groups duplicate stack traces together to prevent redundant inputs.
*   **Brace-Counting Parser:** Reuses the same Java/Groovy code parser as CANonFlake, stripping comments and string literals to accurately trace method boundaries.
