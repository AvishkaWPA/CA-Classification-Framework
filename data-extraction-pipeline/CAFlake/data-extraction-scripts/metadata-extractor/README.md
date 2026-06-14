# Stage 1: Metadata Extraction

This stage initializes the shared dataset `context_enriched_dataset.csv` by parsing primary test configurations and cross-referencing Git commit SHAs and repository links.

---

## Mechanism Overview

1. **Mapping Resolution**: Loads the remote Git repository URLs and commit SHAs for both flaky and fixed versions by combining the mapping details in `research-data/Reproducible_JIRA_info.csv` and `research-data/Reproducible_iDoFT_info.csv`.
2. **Category Mapping**: Normalizes flaky category abbreviations from `test_config.csv` into descriptive full names:
   * `id` &rarr; `Implementation Dependent`
   * `od` &rarr; `Order Dependent`
   * `nio` &rarr; `Non-Idempotent`
   * `td` &rarr; `Time Dependent`
   * Any other category &rarr; `""` (empty string)
3. **Identifier Assignment**: Assigns an incrementing integer `id` starting from `1` for all successfully mapped records.

---

## Example

### 1. Input Mapping Entry (`Reproducible_iDoFT_info.csv`):
```csv
Zip name,Project (Github Link),Flaky commit SHA,Fixed commit SHA
fastjson=97ee7b6,https://github.com/alibaba/fastjson,97ee7b63bfd1563d5071fa5a7a55806bb1c3cb85,0f4379b58cc54e8e4429770f32f8e1c86202a028
```

### 2. Input Test Configuration Entry (`test_config.csv`):
```csv
result_container,zip,test_type
fastjson97ee7b6test_for_issue5,fastjson=97ee7b6,id
```

### 3. Extracted Metadata Output (`context_enriched_dataset.csv`):
```csv
id,test_id,flaky_category,repo_url,flaky_commit,fixed_commit
1,fastjson97ee7b6test_for_issue5,Implementation Dependent,https://github.com/alibaba/fastjson,97ee7b63bfd1563d5071fa5a7a55806bb1c3cb85,0f4379b58cc54e8e4429770f32f8e1c86202a028
```
