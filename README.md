# CA-Classification-Framework

Welcome to the **Context Augment (CA) Flaky Test Classification Framework**. This repository contains the complete pipelines to extract, analyze, and build contextual datasets of both **flaky** (`CAFlake`) and **non-flaky** (`CANonFlake`) Java test failures.

Together, these pipelines form a unified binary classification corpus used to train and evaluate models for identifying flaky tests.

---

## Getting Started: Clone & Data Setup

Because the raw datasets and source repositories are extremely large (multiple gigabytes), they are not checked into Git history. Instead, this repository uses a central `dataSource` directory to access raw assets.

Follow these steps to populate the required data sources before running the extraction pipelines:

### 1. Set Up the Defects4J Data Source (`dataSource/defects4j/`)
The `CANonFlake` pipeline extracts deterministic test failures from the Defects4J benchmark. 
Place or clone the following contents into `data-extraction-pipeline/dataSource/defects4j/`:
*   **Defects4J Framework:** The clone of the [Defects4J Repository](https://github.com/rjust/defects4j). Specifically, it must contain `framework/projects/` with metadata files and `trigger_tests/` stack traces.
*   **Bare Git Repositories:** Clone or extract the target project Git repositories into a folder named `project_repos/` (so that bare repos exist at paths like `project_repos/commons-lang.git`, `project_repos/jfreechart.git`, etc.).

### 2. Set Up the ReproFlake Data Source (`dataSource/reproFlake/`)
The `CAFlake` pipeline extracts flaky test failures from the ReproFlake framework results.
Place the following contents into `data-extraction-pipeline/dataSource/reproFlake/`:
*   **`data/`**: Original maven project zip files.
*   **`result/`**: Verification outputs and execution results from ReproFlake.
*   **`test_config.csv`**: Baseline configurations and test suite info.
*   **`research-data/`**: Directory containing the mapped tables `Reproducible_JIRA_info.csv` and `Reproducible_iDoFT_info.csv`.

---

## Directory Structure

```
CA-Classification-Framework/
├── README.md                              ← This file (setup & data source guide)
└── data-extraction-pipeline/              ← Main pipeline folder
    ├── README.md                          ← Pipeline execution & merge instructions
    ├── dataSource/                        ← Central raw directory (content git-ignored)
    │   ├── defects4j/                     
    │   └── reproFlake/                    
    ├── CAFlake/                           ← Flaky test context extractor
    ├── CANonFlake/                        ← Non-flaky test context extractor
    └── dataset-merger/                    ← Merging & binary labeling script
```

## Running the Pipelines

Once your `dataSource/` folder is populated, refer to the [Pipeline Execution Guide](data-extraction-pipeline/README.md) inside the pipeline folder to start data extraction and construct the final binary classification dataset.
