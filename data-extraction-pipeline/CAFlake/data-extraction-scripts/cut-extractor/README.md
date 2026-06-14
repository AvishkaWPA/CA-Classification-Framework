# Stage 4: Code Under Test (CUT) Extractor

This script extracts the production method bodies that are executed or tested by each flaky test case using a robust hybrid approach.

---

## Folder Location
All files for this stage reside in:
`CAFlake/data-extraction-scripts/cut-extractor/`

---

## Mechanism of Extraction (Hybrid Approach)

 For each flaky test case, the script identifies and extracts production methods using three layers of collection:
 
 1. **Dynamic Coverage (Jacoco XML)**:
    * Parses the `jacoco_*.xml` report inside the `coverage` results directory.
    * Collects all production methods where the execution instruction coverage count is greater than zero (`covered > 0`).
 2. **Dynamic Failure Path (Stack Trace)**:
    * Parses the stack trace frames from the extracted `flaky_failure_log` (Stage 3).
    * Identifies and extracts the classes/methods that directly caused or participated in the crash.
 3. **Static Call Parsing & Semantic Resolver (AST Fallback)**:
    * Parses direct method calls (`receiver.methodName()`), constructors (`new ClassName(...)`), and any capitalized words (local types, class literals) inside `flaky_test_code` and `flaky_helper_methods_json` (Stage 2).
    * **Recursive Hierarchy Scanner**: If the test class inherits from another class (e.g. `extends StompTest`), the script recursively traverses the hierarchy in the ZIP, collecting all variable types, imports, and package declarations.
    * **FQN Resolution**: Resolves each candidate type against the collected imports and packages, confirming existence as a production source file in the project ZIP.
 4. **Backup Name-based Fallback**:
    * If no CUT methods are detected, the script matches the test class name against both suffix rules (e.g. `ANYMatcherTest` -> `ANYMatcher`) and prefix rules (e.g. `TestReflect` -> `Reflect`).
    * If the corresponding production source file is found in the ZIP, the script automatically extracts all of its public methods and constructors.
 
 ### Filters Applied
 To keep the extraction clean and relevant, the script filters out:
 * The test class itself, and parent test classes ending with `Test`, `Tests`, `TestCase`, or `Spec`.
 * External third-party libraries (e.g., JUnit, Mockito, EasyMock, Hamcrest).
 * JDK internal methods and reflection frames.
 
 ### ZIP File Extraction
 For all resolved method signatures, the script opens the corresponding project ZIP file in-memory, parses the production `.java` or `.groovy` source files, and recursively extracts the method bodies (supporting inheritance hierarchies).

---

## Output Format

The extracted methods are formatted as a nested JSON structure and saved to the `flaky_code_under_test_json` column in `CAFlake/context_enriched_dataset.csv`:
```json
{
  "org.apache.accumulo.core.conf.SiteConfiguration": {
    "get": "public String get(Property property) {\n    if (parent != null)\n        return parent.get(property);\n    ...\n}"
  },
  "org.apache.accumulo.core.util.shell.Shell": {
    "setInstance": "public static void setInstance(Shell shell, Instance instance) {\n    shell.instance = instance;\n}",
    "getInstance": "public Instance getInstance() {\n    return this.instance;\n}"
  }
}
```

---

## How to Run

### 1. Run on a limit of 5 records (for verification)
```powershell
python CAFlake/data-extraction-scripts/cut-extractor/extract_cut.py --limit 5 --force
```

### 2. Run on the full dataset
```powershell
python CAFlake/data-extraction-scripts/cut-extractor/extract_cut.py
```

### 3. Force overwrite existing records
```powershell
python CAFlake/data-extraction-scripts/cut-extractor/extract_cut.py --force
```
