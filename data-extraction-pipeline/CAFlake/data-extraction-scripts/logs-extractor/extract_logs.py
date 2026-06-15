import os
import csv
import re
import argparse
import sys
import json

# Allow importing config and utils from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import TEST_CONFIG_PATH, RESULT_DIR
from utils import (
    read_common_dataset,
    write_common_dataset
)

# Headers updated for Step 3
LOGS_HEADERS = [
    "id",
    "test_id",
    "isFlaky",
    "issue_category",
    "repo_url",
    "issue_commit",
    "fixed_commit",
    "test_code",
    "helper_methods_json",
    "failure_log"
]

# Helper to bypass Windows 260-character path limit
def get_long_path(path):
    path = os.path.abspath(path)
    if sys.platform.startswith("win") and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + path
    return path

# Loads test configuration mappings from test_config.csv
def load_test_configs():
    configs = {}
    if not os.path.exists(TEST_CONFIG_PATH):
        return configs
    with open(TEST_CONFIG_PATH, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            container = r.get("result_container", "").strip()
            flaky_test = r.get("flaky_test", "").strip()
            if container:
                configs[container] = {"flaky_test": flaky_test}
    return configs

# Recursively crawls the flaky results directory for surefire text reports matching ClassName.txt
def find_all_report_files(flaky_dir, class_fqn):
    # Simple class name
    class_name = class_fqn.split('.')[-1].split('$')[-1]
    target_suffix = f"{class_name}.txt"
    
    report_files = []
    long_flaky_dir = get_long_path(flaky_dir)
    if not os.path.exists(long_flaky_dir):
        return report_files
        
    # Check for both surefire-reports and .nondex subdirectories
    subdirs_to_check = []
    for d in ("surefire-reports", ".nondex"):
        p = os.path.join(long_flaky_dir, d)
        if os.path.exists(p):
            subdirs_to_check.append(p)
            
    if not subdirs_to_check:
        return report_files
        
    for s_dir in subdirs_to_check:
        for root, dirs, files in os.walk(s_dir):
            for f in files:
                # We want files ending with ClassName.txt and not output files
                if f.endswith(target_suffix) and not f.endswith("-output.txt"):
                    report_files.append(os.path.join(root, f))
                
    return report_files

# Parses a surefire report text content to extract the stack trace of the target method
def parse_failure_trace(report_content, method_name):
    # Strip JUnit parameterized run suffixes like [0] or [parameter]
    cleaned_method = method_name.split('[')[0].split(':')[0].strip()
    lines = report_content.splitlines()
    trace_blocks = []
    
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        # Match test name with word boundary to avoid partial matches
        if re.search(r'\b' + re.escape(cleaned_method) + r'\b', line) and ('<<< FAILURE!' in line or '<<< ERROR!' in line):
            trace_lines = []
            i += 1
            while i < n:
                next_line = lines[i]
                
                # Check for termination conditions
                if '<<< FAILURE!' in next_line or '<<< ERROR!' in next_line:
                    break
                if 'Time elapsed:' in next_line and ('- in' not in next_line):
                    break
                if next_line.startswith('Tests run:') or next_line.startswith('---') or next_line.startswith('==='):
                    break
                    
                trace_lines.append(next_line)
                i += 1
                
            # Clean up trailing empty lines
            while trace_lines and not trace_lines[-1].strip():
                trace_lines.pop()
            if trace_lines:
                trace_blocks.append('\n'.join(trace_lines))
            continue
        i += 1
        
    return trace_blocks

# Extracts only the stack trace frames (ignoring the dynamic message) to serve as a deduplication key
def get_stack_trace_key(trace):
    frames = []
    for line in trace.splitlines():
        stripped = line.strip()
        # Java stack trace frames start with "at " or contain "Caused by:"
        if stripped.startswith("at ") or stripped.startswith("Caused by:") or stripped.startswith("..."):
            frames.append(stripped)
    if frames:
        return "\n".join(frames)
    # Fallback to the whole trace if no frames found
    return "\n".join([line.strip() for line in trace.splitlines() if line.strip()])

# Fallback parser that reads stack traces from rounds-test-results.csv JSON payloads
def parse_rounds_csv_fallback(csv_path, method_name):
    cleaned_method = method_name.split('[')[0].split(':')[0].strip()
    unique_failures = {}
    total_rounds = 0
    
    long_csv_path = get_long_path(csv_path)
    if not os.path.exists(long_csv_path):
        return unique_failures, total_rounds
        
    try:
        with open(long_csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                total_rounds += 1
                
                status = row[1].strip().lower() if len(row) > 1 else ""
                if status not in ("failure", "error"):
                    continue
                    
                # Search for JSON string in any field starting from index 3
                json_str = None
                for idx in range(3, len(row)):
                    field_val = row[idx].strip()
                    if field_val.startswith('{') and field_val.endswith('}'):
                        json_str = field_val
                        break
                        
                if json_str:
                    try:
                        data = json.loads(json_str)
                        results = data.get("results", {})
                        for k, v in results.items():
                            if cleaned_method in k:
                                res_status = v.get("result", "").strip().lower()
                                if res_status in ("failure", "error"):
                                    stack_frames = v.get("stackTrace", [])
                                    if stack_frames:
                                        # Format frames into standard java stack trace
                                        formatted_trace = "\n".join([f"\tat {frame}" for frame in stack_frames])
                                        # The JSON output doesn't have exception/message, so key is the whole trace
                                        normalized_key = "\n".join(stack_frames)
                                        if normalized_key not in unique_failures:
                                            unique_failures[normalized_key] = {"raw_trace": formatted_trace, "count": 1}
                                        else:
                                            unique_failures[normalized_key]["count"] += 1
                    except Exception:
                        pass
    except Exception as e:
        print(f"    Error reading fallback CSV {csv_path}: {e}")
        
    return unique_failures, total_rounds

# Main runner for log extraction
def run_logs_extraction(limit=None, force=False):
    csv_rows = read_common_dataset()
    if not csv_rows:
        print("Error: context_enriched_dataset.csv is empty or missing. Run Stage 1 and 2 first.")
        return
        
    test_configs = load_test_configs()
    processed_count = 0
    print(f"Beginning Step 3 Log Extraction for {len(csv_rows)} records...")
    
    for idx, row in enumerate(csv_rows):
        test_id = row.get("test_id", "")
        config = test_configs.get(test_id)
        if not config:
            continue
            
        has_log = row.get("failure_log")
        if has_log and not force:
            continue
            
        if limit is not None and processed_count >= limit:
            break
            
        flaky_test_str = config["flaky_test"]
        if '#' not in flaky_test_str:
            continue
            
        class_fqn, method_name = flaky_test_str.split('#', 1)
        
        # Locate the result/test_id/result/Flaky directory
        flaky_dir = os.path.join(RESULT_DIR, test_id, "result", "Flaky")
        if not os.path.exists(get_long_path(flaky_dir)):
            # Try lower-case check in case of result folder differences
            found = False
            test_dir_parent = os.path.join(RESULT_DIR, test_id)
            if os.path.exists(get_long_path(test_dir_parent)):
                for sub in os.listdir(get_long_path(test_dir_parent)):
                    if sub.lower() == "result":
                        flaky_sub = os.path.join(test_dir_parent, sub, "Flaky")
                        if os.path.exists(get_long_path(flaky_sub)):
                            flaky_dir = flaky_sub
                            found = True
                            break
            if not found:
                print(f"  Warning: Flaky directory not found for {test_id}")
                continue
                
        # Crawl recursively for all report files matching [ClassName].txt
        report_files = find_all_report_files(flaky_dir, class_fqn)
        
        unique_failures = {}
        total_rounds = 0
        used_fallback = False
        
        if report_files:
            # Process via surefire plain-text report files
            print(f"Extracting Logs ({processed_count+1}/{limit if limit else len(csv_rows)}): {test_id}...")
            total_rounds = len(report_files)
            for r_file in report_files:
                try:
                    with open(get_long_path(r_file), 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                except Exception as e:
                    print(f"    Error reading report {r_file}: {e}")
                    continue
                    
                round_traces = parse_failure_trace(content, method_name)
                for trace in round_traces:
                    # Deduplicate using the stack trace frames (ignoring comparison message variations)
                    trace_key = get_stack_trace_key(trace)
                    if trace_key:
                        if trace_key not in unique_failures:
                            unique_failures[trace_key] = {"raw_trace": trace, "count": 1}
                        else:
                            unique_failures[trace_key]["count"] += 1
        else:
            # Try fallback to rounds-test-results.csv JSON payload
            csv_path = os.path.join(flaky_dir, "rounds-test-results.csv")
            if os.path.exists(get_long_path(csv_path)):
                print(f"Extracting Logs via Fallback CSV ({processed_count+1}/{limit if limit else len(csv_rows)}): {test_id}...")
                unique_failures, total_rounds = parse_rounds_csv_fallback(csv_path, method_name)
                used_fallback = True
                
        if not unique_failures and not used_fallback:
            print(f"  Warning: No failure logs or surefire files found for {test_id}")
            continue
            
        # Sort failures by occurrence frequency in descending order
        sorted_failures = sorted(unique_failures.values(), key=lambda x: x["count"], reverse=True)
        
        # Limit to the single most frequent failure mode (most probable log)
        top_failures = sorted_failures[:1]
        
        # Construct the final plain text log field
        log_blocks = []
        for info in top_failures:
            count = info["count"]
            raw_trace = info["raw_trace"]
            log_blocks.append(f"Failed Rounds: {count}/{total_rounds}\n{raw_trace}")
            
        final_log = "\n\n".join(log_blocks) if log_blocks else ""
        row["failure_log"] = final_log
        
        processed_count += 1
        
        # Write back in batches of 50 to prevent loss on interrupt
        if processed_count % 50 == 0:
            write_common_dataset(csv_rows, LOGS_HEADERS)
            
    write_common_dataset(csv_rows, LOGS_HEADERS)
    print(f"Successfully processed and updated {processed_count} logs in common CSV.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CAFlake Stage 3: Run Time Failure Logs Extractor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=0,
        help="Limit the number of processed test cases. Set to 0 for no limit."
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force overwrite of already extracted failure log values."
    )
    args = parser.parse_args()
    
    limit_val = None if args.limit <= 0 else args.limit
    run_logs_extraction(limit=limit_val, force=args.force)
