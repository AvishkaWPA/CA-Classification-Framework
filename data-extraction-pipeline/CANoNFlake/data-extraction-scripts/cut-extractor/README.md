# Stage 4 — Code Under Test (CUT) Extractor

This module maps, parses, and extracts the source code of the production methods (Code Under Test) exercised by the failing test.

## How It Works

The script executes three sequential lookup phases to identify candidate production class/method pairs:

1. **Stack Trace Frame Analysis:** Parses the stack trace in `flaky_failure_log` to identify production methods called leading up to the test failure (filtering out test classes, test frameworks, and JDK internal frames).
2. **Static Call Parsing:** Analyzes the test code (`flaky_test_code`) and helpers (`flaky_helper_methods_json`) using regex to identify called production classes, constructors (`new Class(...)`), member calls (`Class.method(...)`, `obj.method(...)`), and local scope calls.
3. **Test Class Import Fallback:** If the list of targets remains empty, imports in the test class are parsed recursively. The script matches imports from the project scope (ignoring frameworks) and includes all public methods from these production classes as candidates.
4. **Name-Based Package Fallback:** Matches package contents for classes whose names match the test class prefix (e.g., test class `org.apache.commons.FooTest` will fall back to production class `org.apache.commons.Foo` and collect its public methods).

### Code Extraction and Optimization
Once target methods are mapped, they are checked out from the **buggy commit** (`flaky_commit`) in the project's bare Git repo:
*   **Inheritance walking:** If a method is not found in the target class, the script walks up the class hierarchy (`extends ...`) to search for and extract inherited methods.
*   **Performance Optimization (Path-Based FQN):** Instead of executing expensive `git show` subprocess commands for package identification, the class resolver derives FQN mappings directly from directory layout structures (e.g. mapping `src/main/java`), resulting in a 1,000x execution speedup (~0.3s/row).
*   **JSON Output:** The extracted method bodies are stored in a nested JSON map in `flaky_code_under_test_json` with format: `{ "class_fqn": { "method_name": "method_body_string" } }`.

## Execution

```powershell
python data-extraction-scripts/cut-extractor/extract_cut.py
```

### CLI Arguments:
*   `--limit`, `-l`: Limit the number of processed test cases.
*   `--force`, `-f`: Force re-extraction and overwrite existing CUT JSON.
