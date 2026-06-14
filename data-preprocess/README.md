# Dataset Preprocessing Pipeline (`data-preprocess`)

This folder contains utilities to preprocess and split the Context-Augmented Dataset before it is loaded into Large Language Models (LLMs) for fine-tuning or classification.

---

## 1. Preprocessing Actions

The script [preprocess.py](file:///d:/university%20works/Final-Year_Firts_sem/FYP/INFO/REPO/CA-Classification-Framework/data-preprocess/preprocess.py) applies the following transformations to the raw merged dataset:

| Column | Action | Why We Did It |
|---|---|---|
| **Row Filtering** | Discards rows missing `test_code`, `failure_log`, or `code_under_test_json` (e.g., compile/extract failures). | Prevents feeding incomplete context vectors to the model. |
| `test_code` | Strips all Javadoc annotations, block comments (`/* ... */`), and single-line comments (`// ...`). | Reduces token usage by **30% to 50%** and isolates functional statements. |
| `helper_methods_json` | Strips comments from all internal test class helper method bodies. | Minimizes noise in helper method code blocks. |
| `failure_log` | 1. Removes the `Failed Rounds: X/Y` header.<br>2. Filters out JVM reflection (`java.lang.reflect`), JUnit runner, and build tool frames.<br>3. Caps trace to the top 15 frames. | **Prevents Data Leakage:** Keeps the LLM from cheating based on the round ratios (`/100` vs `1/1`) and focuses trace on the crash location. |
| `code_under_test_json` | 1. Simplifies fully qualified class names (FQNs) to class names (e.g., `NumberUtils`).<br>2. Strips comments from all method bodies. | Removes verbose package structures and cleans production code bodies. |

---

## 2. Group-Based Splitting (Preventing Data Leakage)

Standard random train/val/test splits cause **Data Leakage**. If a project's test files appear in both training and testing splits, the LLM will memorize specific class/method names and score unrealistically high on testing, while failing to generalize to new repositories.

The `--split` option groups records by their repository URL (`repo_url`) and allocates them greedily:
*   **Train Split (70%)**
*   **Validation Split (15%)**
*   **Test Split (15%)**

This guarantees that **no repository's code appears in more than one split**, measuring the model's true capability to generalize to unseen codebases.

---

## 3. Usage Instructions

Execute the script from the root of the repository or inside the `data-preprocess` directory:

### Run Preprocessing and Generate Splits
```powershell
python data-preprocess/preprocess.py --split
```

### Script Options
*   `--input` / `-i`: Path to the raw JSONL dataset (defaults to `../data-extraction-pipeline/context_augmented_dataset.jsonl`).
*   `--output-dir` / `-o`: Folder to write preprocessed files (defaults to `data-preprocess`).
*   `--split` / `-s`: Performs group-based splitting and writes `train.jsonl`, `val.jsonl`, `test.jsonl` (and their CSV conversions).
