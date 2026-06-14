# Data Extraction Pipeline

This directory orchestrates the full data extraction pipeline for **CAFlake** and **CANonFlake**, culminating in a combined dataset for binary classification.

## Directory Structure

```
data-extraction-pipeline/
├── README.md                          ← This file
├── dataSource/                        ← Central raw dataset folder (git-ignored)
│   ├── defects4j/                     ← Place Defects4J repository content here
│   └── reproFlake/                    ← Place ReproFlake data/result directories here
├── CAFlake/                           ← CAFlake flaky test case extractor
│   ├── data-extraction-scripts/       
│   └── context_enriched_dataset.csv   
├── CANonFlake/                        ← CANonFlake deterministic test case extractor
│   ├── data-extraction-scripts/       
│   ├── non_flaky_dataset.csv          
│   └── non_flaky_dataset.jsonl        
└── dataset-merger/
    ├── merge_datasets.py              ← Concatenation and labeling script
    └── README.md                      
```

---

## Dataset Extraction Methodology

This section details how the pipelines statically and dynamically extract context-enriched features to build the classification datasets.

```mermaid
graph TD
    subgraph CAFlake (Flaky Dataset)
        D1[test_config.csv] --> C1[1. Metadata Extraction]
        C1 --> C2[2. Test Code Extraction]
        C2 --> C3[3. Failure Log Extraction]
        C3 --> C4[4. Code Under Test Extraction]
        zips1[data/*.zip] --> C2
        surefire1[surefire-reports] --> C3
        coverage1[coverage_results.csv] --> C4
    end

    subgraph CANonFlake (Non-Flaky Dataset)
        D2[active-bugs.csv / trigger_tests] --> N1[1. Metadata Extraction]
        N1 --> N2[2. Test Code Extraction]
        N2 --> N3[3. Failure Log Extraction]
        N3 --> N4[4. Code Under Test Extraction]
        git[Bare Git Repos] --> N2
        git --> N4
    end
```

### Stage 1: Metadata Extraction
*   **CAFlake:** Parses `test_config.csv` and cross-references JIRA/iDoFT info tables (`Reproducible_JIRA_info.csv`, `Reproducible_iDoFT_info.csv`) to map git commit SHAs, project URLs, and execution metrics (passes, failures, errors).
*   **CANonFlake:** Parses Defects4J's `active-bugs.csv` and `trigger_tests` directory files. It extracts the buggy commit SHA (`flaky_commit`) and fixed commit SHA (`fixed_commit`), mapping the repository URL from a static config table.

### Stage 2: Test & Helper Code Extraction
*   **CAFlake:** Locates target test files inside project source ZIPs under `data/`. It parses test method bodies using a comment-stripped Java/Groovy brace-counting parser. It recursively walks up the inheritance hierarchy (`extends ...`) to find helper methods invoked inside the test method body and writes them to `flaky_helper_methods_json`.
*   **CANonFlake:** Uses the bare Git repository of the project to check out the test class file at the `fixed_commit` (since Defects4J patches remove the failing test from buggy commits). It extracts the test method body using brace-matching. For inherited helpers or older SVN-based repositories, it falls back to parsing the `.test.patch` diff files to reconstruct test method bodies.

### Stage 3: Failure Log Extraction
*   **CAFlake:** Scans execution rounds inside the project's surefire reports (`result/[test_id]/result/Flaky/surefire-reports/reports-[round]/`). It reads the `[ClassName].txt` reports, extracts the JUnit stack traces, deduplicates identical failure messages/traces across rounds, and formats them prefixed with `Failed Rounds: X/Y`.
*   **CANonFlake:** Statically parses the Defects4J `trigger_tests/` logs. It isolates the stack trace corresponding to the specific test method and formats it with a `Failed Rounds: 1/1` prefix to align with CAFlake's formatting.

### Stage 4: Code Under Test (CUT) Extraction
*   **CAFlake:** Reads Jacoco dynamic coverage results (`coverage_results.csv`), maps covered classes to ZIP main sources (resolving inner classes and constructors), and extracts the production method source code bodies coverage-tested by the test.
*   **CANonFlake:** Resolves the production classes and methods using a multi-phase parser: (1) parsing the stack trace frames in the failure log, (2) statically analyzing calls/constructors inside the test and helper code, (3) recursively looking up test class imports, or (4) matching files by name within the package. Target methods are checked out from the `flaky_commit` (buggy SHA) in the project's bare Git repo and parsed recursively.

---

## Workflow Execution Steps

Ensure all required raw data is situated in `dataSource/` first (see the [Main README](../README.md)).

### 1. Execute CAFlake Extraction
Navigate to the root of `CA-Classification-Framework` and run the extraction scripts inside `CAFlake/data-extraction-scripts/`:
```powershell
# Run Stage 1: Metadata extraction
python data-extraction-pipeline/CAFlake/data-extraction-scripts/metadata-extractor/extract_metadata.py

# Run Stage 2: Code extraction
python data-extraction-pipeline/CAFlake/data-extraction-scripts/code-extractor/extract_codes.py

# Run Stage 3: Failure log extraction
python data-extraction-pipeline/CAFlake/data-extraction-scripts/logs-extractor/extract_logs.py

# Run Stage 4: Code under test extraction
python data-extraction-pipeline/CAFlake/data-extraction-scripts/cut-extractor/extract_cut.py
```

### 2. Execute CANonFlake Extraction
Run the extraction scripts inside `CANoNFlake/data-extraction-scripts/`:
```powershell
# Run Stage 1: Metadata extraction
python data-extraction-pipeline/CANoNFlake/data-extraction-scripts/metadata-extractor/extract_metadata.py

# Run Stage 2: Code extraction
python data-extraction-pipeline/CANoNFlake/data-extraction-scripts/code-extractor/extract_codes.py

# Run Stage 3: Failure log extraction
python data-extraction-pipeline/CANoNFlake/data-extraction-scripts/logs-extractor/extract_logs.py

# Run Stage 4: Code under test extraction
python data-extraction-pipeline/CANoNFlake/data-extraction-scripts/cut-extractor/extract_cut.py

# Step 5: Clean rows lacking Code Under Test (missing CUT values) and convert CSV to JSONL format
python data-extraction-pipeline/CANoNFlake/data-extraction-scripts/converters/convert_csv_to_jsonl.py
```

### 3. Merge Datasets
To combine the extracted datasets and output `binary_classification_dataset.csv` (and `.jsonl`):
```powershell
python data-extraction-pipeline/dataset-merger/merge_datasets.py
```
This merges the datasets, assigns target binary labels (`1` for flaky, `0` for non-flaky), and formats the final row identifiers.
