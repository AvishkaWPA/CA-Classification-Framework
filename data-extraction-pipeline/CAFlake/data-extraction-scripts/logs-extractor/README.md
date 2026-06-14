# Stage 3: Run Time Failure Logs Extractor

This script parses Maven Surefire text reports generated across multiple execution rounds to extract deduplicated failure stack traces for the target flaky test cases.

---

## Folder Location
All files for this stage reside in:
`CAFlake/data-extraction-scripts/logs-extractor/`

---

## Mechanism of Log Extraction

For each flaky test case (`test_id`), the script does the following:

1. **Resolve Test Target**: Cross-references the `test_config.csv` to map the `test_id` to the fully qualified test class name (e.g., `org.apache.accumulo.core.util.shell.ShellSetInstanceTest`) and method name (e.g., `testSetInstance_HdfsZooInstance_Explicit`).
2. **Scan Execution Rounds**: Finds the surefire reports directory at `result/[test_id]/result/Flaky/surefire-reports/` and locates all round subdirectories (`reports-0`, `reports-1`, etc.).
3. **Locate Plain-Text Report**: Searches each round directory for `[ClassName].txt`. It handles inner class paths (e.g., `MyClass$InnerClass` resolves to `MyClass.txt`) and uses a fallback name search if the FQN doesn't match directly.
4. **Parse Stack Trace**:
   * Scans the report file line-by-line.
   * Matches the line containing the target test method and ending in `<<< FAILURE!` or `<<< ERROR!`.
   * Captures the subsequent lines containing the exception name, failure message, and stack trace.
   * Stops capturing when encountering headers for another test case, surefire execution summaries, or dividers.
5. **Deduplicate Traces**:
   * Standardizes whitespace and line formatting of the captured stack trace to identify identical failures across rounds.
   * Counts the frequency of each unique stack trace.
6. **Save to CSV**:
   * Formats each unique failure with a count header (e.g., `Failed Rounds: 40/100`).
   * Saves the result as plain text in the `flaky_failure_log` column in `CAFlake/context_enriched_dataset.csv`.

---

## Log Output Examples

### Example 1: Single Failure Mode (Accumulo 2102)
If a test case failed in 10 out of 10 runs with the exact same error:
```text
Failed Rounds: 10/10
java.lang.AssertionError: Unexpected method call ClientConfiguration.containsKey("instance.dfs.dir"):
	at org.easymock.internal.MockInvocationHandler.invoke(MockInvocationHandler.java:44)
	at org.easymock.internal.ObjectMethodsFilter.invoke(ObjectMethodsFilter.java:85)
	at org.apache.accumulo.core.conf.SiteConfiguration.get(SiteConfiguration.java:67)
```

### Example 2: Multiple Failure Modes
If a test case failed in two different ways (e.g., 38 assertion failures and 2 timeouts out of 100 runs):
```text
Failed Rounds: 38/100
java.lang.AssertionError: Expected true but was false
	at org.junit.Assert.fail(Assert.java:88)
	at com.example.MyTest.testFlaky(MyTest.java:45)

Failed Rounds: 2/100
java.util.concurrent.TimeoutException: Transaction timed out after 5000ms
	at java.util.concurrent.FutureTask.get(FutureTask.java:206)
	at com.example.MyTest.testFlaky(MyTest.java:48)
```

---

## How to Run

### 1. Run on a limit of 5 records (for verification)
```powershell
python CAFlake/data-extraction-scripts/logs-extractor/extract_logs.py --limit 5
```

### 2. Run on the full dataset
```powershell
python CAFlake/data-extraction-scripts/logs-extractor/extract_logs.py
```

### 3. Force overwrite existing records
```powershell
python CAFlake/data-extraction-scripts/logs-extractor/extract_logs.py --force
```
