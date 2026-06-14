# Stage 3 — Failure Log Extractor

This module extracts and formats the stack traces / failure outputs of the failing tests.

## How It Works

1. **Static Parsing (No Test Execution):** Defects4J pre-runs and captures test outputs, storing them in the `trigger_tests/[bug_id]` text files inside each project folder. This allows extracting failure logs statically without compiling or executing Java code.
2. **Index Alignment:** Resolves the method's index from the `test_id` suffix (e.g. `Chart-14-3` retrieves the 3rd failing test case block within the `trigger_tests/14` file).
3. **Trigger File Parser:** Extracts the failing test class name, test method name, and the raw JUnit stack trace output.
4. **CAFlake Format Adaptation:** Prepends a `"Failed Rounds: 1/1\n"` prefix to the stack trace block to mirror the exact failure log representation in CAFlake.

## Execution

```powershell
python data-extraction-scripts/logs-extractor/extract_logs.py
```

### CLI Arguments:
*   `--limit`, `-l`: Limit the number of processed test cases.
*   `--force`, `-f`: Force re-extraction and overwrite existing logs.
