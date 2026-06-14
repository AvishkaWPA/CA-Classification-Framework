# Stage 2 — Test Code Extractor

This module extracts the source code body of the failing test method and any helper methods defined in the same test class or its direct parent class.

## How It Works

1. **Bare Git Repository Access:** Matches the project to its bare Git repository under `project_repos/` (e.g. `jfreechart.git`, `commons-lang.git`).
2. **Commit Alignment:** Focuses on the **fixed commit** (`fixed_commit`). In Defects4J, the failing test is added/enabled in the fixed commit and removed or commented out in the buggy commit (`flaky_commit`).
3. **Test File Locator:** Locates the test `.java` source file using `dir-layout.csv` (mapping paths like `src/test/java`).
4. **Brace-Counting Parser:** 
   - Strips comments and string literals to prevent syntax false matches.
   - Searches for the method signature using regex matching.
   - Traces the method bounds using brace matching (`{` and `}`) to extract the raw test method body.
5. **Helper Methods Tracing:** Searches the test body for internal calls, resolving their signatures in the same class (or walking up one level to a parent test class) and serializing the helper bodies to `flaky_helper_methods_json`.
6. **SVN/Patch Fallback:** If the bare git repository query fails (common on legacy SVN-based Chart bugs), the script reads the Defects4J `.test.patch` file and reconstructs the test method source by parsing hunk deletions (`-` lines).

## Execution

```powershell
python data-extraction-scripts/code-extractor/extract_codes.py
```

### CLI Arguments:
*   `--limit`, `-l`: Limit the number of processed test cases.
*   `--force`, `-f`: Force re-extraction and overwrite existing test code fields.
