import os
import csv

# Set higher CSV field size limit to support large stack trace logs
csv.field_size_limit(2147483647)

def get_d4j_root():
    # Returns the absolute path to the defects4j root.
    # utils.py is located at CANonFlake/data-extraction-scripts/utils.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(script_dir, "..", ".."))

def get_common_csv_path():
    # Returns the absolute path to the shared non-flaky dataset CSV.
    d4j_root = get_d4j_root()
    return os.path.join(d4j_root, "CANonFlake", "non_flaky_dataset.csv")

def read_common_dataset():
    # Reads the shared CSV dataset, returning a list of dicts.
    # If the file does not exist, returns an empty list.
    csv_path = get_common_csv_path()
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def write_common_dataset(rows, headers):
    # Writes the list of dicts back to the shared CSV dataset using the specified headers.
    csv_path = get_common_csv_path()
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Updated non-flaky dataset CSV at: {csv_path}")

def parse_trigger_file(trigger_path):
    # Parses a Defects4J trigger_tests/[N] file.
    # Returns a list of (test_class, test_method, failure_log) tuples —
    # one entry per failing test method found in the file.
    #
    # File format:
    #   --- org.example.SomeTest::someMethod
    #   ExceptionType: message
    #       at org.example.SomeTest.someMethod(SomeTest.java:42)
    #       ...
    #   --- org.example.AnotherTest::anotherMethod   (optional second method)
    #   ...
    entries = []
    if not os.path.exists(trigger_path):
        return entries

    with open(trigger_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Split on the "--- " method header lines
    raw_blocks = []
    current_lines = []
    for line in content.splitlines():
        if line.startswith("--- "):
            if current_lines:
                raw_blocks.append(current_lines)
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        raw_blocks.append(current_lines)

    for block in raw_blocks:
        if not block:
            continue
        header = block[0]
        # Parse "--- FullyQualifiedClass::methodName"
        header_content = header[4:].strip()
        if "::" not in header_content:
            continue
        test_class, test_method = header_content.split("::", 1)
        test_class = test_class.strip()
        test_method = test_method.strip()
        # The failure log is everything after the header line
        log_lines = block[1:]
        # Strip trailing blank lines
        while log_lines and not log_lines[-1].strip():
            log_lines.pop()
        failure_log = "\n".join(log_lines)
        entries.append((test_class, test_method, failure_log))

    return entries

def resolve_test_class_method(test_id, projects_dir):
    # Resolves (test_class, test_method) from a test_id by re-reading the
    # trigger_tests file.  Avoids storing test_class/test_method in the CSV.
    #
    # test_id formats:
    #   "Lang-1"      → project=Lang, bug_id=1, method_index=1 (only method)
    #   "Chart-14-3"  → project=Chart, bug_id=14, method_index=3
    #
    # Returns (test_class, test_method) or (None, None) if not found.
    parts = test_id.split("-")
    if len(parts) < 2:
        return None, None

    project = parts[0]
    bug_id = parts[1]
    method_index = int(parts[2]) if len(parts) >= 3 else 1

    trigger_path = os.path.join(projects_dir, project, "trigger_tests", bug_id)
    entries = parse_trigger_file(trigger_path)
    if not entries:
        return None, None

    idx = method_index - 1  # method_index is 1-based
    if idx < 0 or idx >= len(entries):
        return None, None

    test_class, test_method, _ = entries[idx]
    return test_class, test_method
