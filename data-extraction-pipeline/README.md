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
