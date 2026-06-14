# Dataset Preprocessing Pipeline (`data-preprocess`)

This folder contains utilities to preprocess and class-balance the Context-Augmented Dataset before it is loaded into Large Language Models (LLMs) for binary classification checks.

---

## 1. Preprocessing & Balancing Actions

The script [preprocess.py](file:///d:/university%20works/Final-Year_Firts_sem/FYP/INFO/REPO/CA-Classification-Framework/data-preprocess/preprocess.py) applies the following transformations to the raw merged dataset:

| Column / Step | Action | Why We Did It |
|---|---|---|
| **Row Filtering** | Discards rows missing `test_code`, `failure_log`, or `code_under_test_json` (e.g., compile/extract failures). | Prevents feeding incomplete context vectors to the model. |
| `test_code` | Strips all Javadoc annotations, block comments (`/* ... */`), and single-line comments (`// ...`). | Reduces token usage by **30% to 50%** and isolates functional statements. |
| `helper_methods_json` | Strips comments from all internal test class helper method bodies. | Minimizes noise in helper method code blocks. |
| `failure_log` | 1. Removes the `Failed Rounds: X/Y` header.<br>2. Filters out JVM reflection (`java.lang.reflect`), JUnit runner, and build tool frames.<br>3. Caps trace to the top 15 frames. | **Prevents Data Leakage:** Keeps the LLM from cheating based on the round ratios (`/100` vs `1/1`) and focuses trace on the crash location. |
| `code_under_test_json` | 1. Simplifies fully qualified class names (FQNs) to class names (e.g., `NumberUtils`).<br>2. Strips comments from all method bodies. | Removes verbose package structures and cleans production code bodies. |
| **Class Balancing** | Performs reproducible downsampling (`random.seed(42)`) of the majority class (non-flaky) to exactly match the count of the minority class (flaky). | **Prevents Class Bias:** Guarantees a perfect 50/50 balance (2,088 total rows: 1,044 flaky, 1,044 non-flaky) so that predictions aren't skewed. |

---

## 2. Usage Instructions

Execute the script from the root of the repository or inside the `data-preprocess` directory:

```powershell
python data-preprocess/preprocess.py
```

### Script Options
*   `--input` / `-i`: Path to the raw JSONL dataset (defaults to `../data-extraction-pipeline/context_augmented_dataset.jsonl`).
*   `--output-dir` / `-o`: Folder to write preprocessed files (defaults to `data-preprocess`).
*   `--seed` / `-s`: Random seed for reproducible balancing (defaults to `42`).

### Output Files
*   `preprocessed_dataset.jsonl`: Perfectly balanced, comment-free, unescaped JSON Lines dataset.
*   `preprocessed_dataset.csv`: Matching flat CSV version (JSON fields stringified).
