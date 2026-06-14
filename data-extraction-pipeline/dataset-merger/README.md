# Dataset Merger Tool

This script combines the extracted **CAFlake** and **CANonFlake** datasets into a unified dataset for training binary classification models.

## How It Works

*   **Aligns & Concatenates:** Reads both `CAFlake/context_enriched_dataset.csv` and `CANonFlake/non_flaky_dataset.csv` (since they share the identical 10-column schema) and concatenates them.
*   **Assigns Binary Labels:** Computes a `label` column where:
    -   `1` represents flaky test failure samples (`flaky_category != "Non-Flaky"`).
    -   `0` represents deterministic, non-flaky test failure samples (`flaky_category == "Non-Flaky"`).
*   **Re-sequences IDs:** Overwrites the row `id` column to form a continuous, unique index from `1` to `N` across the merged dataset.
*   **Bi-Format Merging:** If the `.jsonl` files exist in both project folders, the script automatically parses, merges, and saves a nested JSON Lines (`.jsonl`) version of the combined dataset.

## Execution

Ensure that both extraction pipelines have run and produced their respective outputs, then run:

```powershell
python data-extraction-pipeline/dataset-merger/merge_datasets.py
```

## Output Location
The combined output will be written to:
*   `data-extraction-pipeline/binary_classification_dataset.csv`
*   `data-extraction-pipeline/binary_classification_dataset.jsonl` (if `.jsonl` sources are present)
