import os
import csv
import re
import json
import argparse
import zipfile
import sys

# Allow importing config and utils from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import DATA_DIR, TEST_CONFIG_PATH
from utils import (
    read_common_dataset,
    write_common_dataset
)

# Headers updated for Step 2
CODE_HEADERS = [
    "id",
    "test_id",
    "isFlaky",
    "issue_category",
    "repo_url",
    "issue_commit",
    "flaky_commit",
    "fixed_commit",
    "test_code",
    "helper_methods_json"
]

def remove_comments_and_strings(code):
    #Replaces comments and strings with whitespace to avoid matching braces inside them.
    clean = []
    i = 0
    n = len(code)
    state = "code"
    
    while i < n:
        char = code[i]
        next_char = code[i+1] if i + 1 < n else ""
        
        if state == "code":
            if char == '"':
                state = "string"
                clean.append(" ")
            elif char == "'":
                state = "char"
                clean.append(" ")
            elif char == '/' and next_char == '/':
                state = "line_comment"
                clean.append("  ")
                i += 1
            elif char == '/' and next_char == '*':
                state = "block_comment"
                clean.append("  ")
                i += 1
            else:
                clean.append(char)
        elif state == "string":
            if char == '\\':
                clean.append("  ")
                i += 1
            elif char == '"':
                state = "code"
                clean.append(" ")
            else:
                clean.append(" ")
        elif state == "char":
            if char == '\\':
                clean.append("  ")
                i += 1
            elif char == "'":
                state = "code"
                clean.append(" ")
            else:
                clean.append(" ")
        elif state == "line_comment":
            if char == '\n':
                state = "code"
                clean.append('\n')
            else:
                clean.append(" ")
        elif state == "block_comment":
            if char == '*' and next_char == '/':
                state = "code"
                clean.append("  ")
                i += 1
            elif char == '\n':
                clean.append('\n')
            else:
                clean.append(" ")
        i += 1
        
    return "".join(clean)

def extract_method_body(code, method_name):
    #Extracts a method body (including modifiers) from Java/Groovy source code.
    pattern = re.compile(
        r'(?<!\.)\b(?:public|protected|private|static|final|synchronized|void|(?!new\b)[\w<>\[\]\.]+)\s+' + 
        re.escape(method_name) + r'\b\s*\('
    )
    match = pattern.search(code)
    if not match:
        return None
        
    name_start = match.start()
    name_match = re.search(r'\b' + re.escape(method_name) + r'\b', code[name_start:])
    if name_match:
        name_start += name_match.start()
    
    clean_code = remove_comments_and_strings(code)
    
    # Ensure '{' brace comes before any ';' semicolon to guarantee it is a method declaration
    brace_start = clean_code.find('{', name_start)
    semicolon_start = clean_code.find(';', name_start)
    if brace_start == -1 or (semicolon_start != -1 and semicolon_start < brace_start):
        return None
        
    depth = 1
    i = brace_start + 1
    n = len(clean_code)
    while i < n and depth > 0:
        if clean_code[i] == '{':
            depth += 1
        elif clean_code[i] == '}':
            depth -= 1
        i += 1
        
    if depth > 0:
        return None
        
    brace_end = i
    
    start_idx = name_start
    while start_idx > 0:
        prev_char = code[start_idx - 1]
        if prev_char in (';', '{', '}'):
            break
        start_idx -= 1
        
    return code[start_idx:brace_end].strip()

class ZipCache:
    #Caches open zip file references to speed up read operations across tests.
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.cache = {}

    def get(self, zip_name):
        if zip_name not in self.cache:
            path = os.path.join(self.data_dir, f"{zip_name}.zip")
            if os.path.exists(path):
                try:
                    self.cache[zip_name] = zipfile.ZipFile(path, 'r')
                except Exception as e:
                    print(f"  Error opening zip {path}: {e}")
                    self.cache[zip_name] = None
            else:
                self.cache[zip_name] = None
        return self.cache[zip_name]

    def close_all(self):
        for ref in self.cache.values():
            if ref:
                ref.close()
        self.cache.clear()

def find_class_file_in_zip(zip_ref, class_name, version="Flaky"):
    #Locates the Java or Groovy file inside the ZIP under the specified version folder.
    base_rel_path = class_name.replace('.', '/')
    if '$' in base_rel_path:
        base_rel_path = base_rel_path.split('$')[0]

    rel_path_java = base_rel_path + ".java"
    rel_path_groovy = base_rel_path + ".groovy"

    for name in zip_ref.namelist():
        if f"/{version}/" in name and (name.endswith(rel_path_java) or name.endswith(rel_path_groovy)):
            return name
    return None

def get_parent_class_name(code):
    #Parses class name and checks if it extends a parent class.
    clean_code = remove_comments_and_strings(code)
    match = re.search(r'\bclass\s+(\w+)(?:\s*<[^>]+>)?(?:\s+extends\s+([\w<>.]+))?', clean_code)
    if match:
        class_name = match.group(1)
        extends_name = match.group(2)
        if extends_name:
            extends_name = extends_name.split('<')[0].strip()
        return class_name, extends_name
    return None, None

def resolve_fqn(extends_name, current_class_fqn, code):
    #Resolves the fully qualified name of a parent class using package and imports.
    if not extends_name:
        return None
    
    clean_code = remove_comments_and_strings(code)
    # Scan imports
    pattern = re.compile(r'\bimport\s+([\w.]+)\s*;')
    imports = pattern.findall(clean_code)
    for imp in imports:
        if imp.endswith(f".{extends_name}"):
            return imp

    # Check package same name
    package_match = re.search(r'\bpackage\s+([\w.]+)\s*;', clean_code)
    if package_match:
        return f"{package_match.group(1)}.{extends_name}"

    if '.' in current_class_fqn:
        parent_pkg = current_class_fqn.rsplit('.', 1)[0]
        return f"{parent_pkg}.{extends_name}"

    return extends_name

def discover_helper_calls(method_body):
    #Finds potential local helper method calls in the method body.
    clean_body = remove_comments_and_strings(method_body)
    calls = re.findall(r'\b(\w+)\s*\(', clean_body)

    ignored = {
        "if", "for", "while", "switch", "synchronized", "catch", "new", "super", "this",
        "return", "throw", "assert", "assertEquals", "assertTrue", "assertFalse",
        "assertNull", "assertNotNull", "assertSame", "assertNotSame", "fail", "assertThat",
        "println", "print", "wait", "notify", "notifyAll", "equals", "hashCode", "toString"
    }

    helpers = set()
    for call in calls:
        if call not in ignored:
            helpers.add(call)
    return list(helpers)

def extract_method_recursive(zip_ref, class_fqn, method_name, version="Flaky"):
    #Recursively searches the class hierarchy in the ZIP to locate a method body.
    file_path = find_class_file_in_zip(zip_ref, class_fqn, version)
    if not file_path:
        return None

    try:
        with zip_ref.open(file_path) as f:
            code = f.read().decode('utf-8', errors='ignore')
    except Exception:
        return None

    body = extract_method_body(code, method_name)
    if body:
        return body

    _, extends_name = get_parent_class_name(code)
    if extends_name:
        parent_fqn = resolve_fqn(extends_name, class_fqn, code)
        if parent_fqn and parent_fqn != class_fqn:
            return extract_method_recursive(zip_ref, parent_fqn, method_name, version)

    return None

def get_test_and_helpers(zip_ref, test_class_fqn, test_method_name, version="Flaky"):
    #Extracts test code body and its referenced local helper method bodies.
    cleaned_method_name = test_method_name.split('[')[0].split(':')[0].strip()
    test_code = extract_method_recursive(zip_ref, test_class_fqn, cleaned_method_name, version)
    if not test_code:
        return None, {}

    helper_calls = discover_helper_calls(test_code)
    helpers_dict = {}
    for helper_name in helper_calls:
        if helper_name == cleaned_method_name:
            continue
        helper_body = extract_method_recursive(zip_ref, test_class_fqn, helper_name, version)
        if helper_body:
            helpers_dict[helper_name] = helper_body

    return test_code, helpers_dict

def load_test_configs():
    #Loads ZIP file and flaky test path details from test_config.csv
    configs = {}
    if not os.path.exists(TEST_CONFIG_PATH):
        return configs
    with open(TEST_CONFIG_PATH, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            container = r.get("result_container", "").strip()
            flaky_test = r.get("flaky_test", "").strip()
            zip_name = r.get("zip", "").strip()
            if container:
                configs[container] = {"zip": zip_name, "flaky_test": flaky_test}
    return configs

def run_code_extraction(limit=None, force=False):
    csv_rows = read_common_dataset()
    if not csv_rows:
        print("Error: context_enriched_dataset.csv is empty or missing. Run Stage 1 first.")
        return

    test_configs = load_test_configs()
    zip_cache = ZipCache(DATA_DIR)

    processed_count = 0
    print(f"Beginning Step 2 Code Extraction for {len(csv_rows)} records...")

    try:
        for idx, row in enumerate(csv_rows):
            test_id = row.get("test_id", "")
            config = test_configs.get(test_id)
            if not config:
                continue

            has_flaky_code = row.get("test_code")
            if has_flaky_code and not force:
                continue

            if limit is not None and processed_count >= limit:
                break

            zip_name = config["zip"]
            flaky_test_str = config["flaky_test"]
            
            if '#' not in flaky_test_str:
                continue

            class_fqn, method_name = flaky_test_str.split('#', 1)
            zip_ref = zip_cache.get(zip_name)
            
            if not zip_ref:
                print(f"  Warning: ZIP file not found for {zip_name} (test {test_id})")
                continue

            print(f"Extracting Code ({processed_count+1}/{limit if limit else len(csv_rows)}): {test_id}...")

            flaky_code, flaky_helpers = get_test_and_helpers(zip_ref, class_fqn, method_name, "Flaky")

            row.update({
                "test_code": flaky_code if flaky_code else "",
                "helper_methods_json": json.dumps(flaky_helpers, ensure_ascii=False) if flaky_helpers else ""
            })

            # Clean out any extra columns
            row.pop("fixed_test_code", None)
            row.pop("fixed_helper_methods_json", None)
            row.pop("code_under_test_json", None)

            processed_count += 1

            if processed_count % 50 == 0:
                write_common_dataset(csv_rows, CODE_HEADERS)

        write_common_dataset(csv_rows, CODE_HEADERS)
        print(f"Successfully processed and updated {processed_count} test code records in common CSV.")

    finally:
        zip_cache.close_all()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CAFlake Stage 2: Test Code & Helper Methods Extractor",
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
        help="Force overwrite of already extracted code values."
    )
    args = parser.parse_args()

    limit_val = None if args.limit <= 0 else args.limit
    run_code_extraction(limit=limit_val, force=args.force)
