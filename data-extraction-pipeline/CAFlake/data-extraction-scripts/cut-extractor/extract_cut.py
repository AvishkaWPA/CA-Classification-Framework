import os
import csv
import re
import json
import argparse
import zipfile
import sys
import xml.etree.ElementTree as ET

# Allow importing config and utils from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import DATA_DIR, TEST_CONFIG_PATH, RESULT_DIR
from utils import (
    read_common_dataset,
    write_common_dataset
)

# Headers updated for Step 4
CUT_HEADERS = [
    "id",
    "test_id",
    "isFlaky",
    "issue_category",
    "repo_url",
    "issue_commit",
    "flaky_commit",
    "fixed_commit",
    "test_code",
    "helper_methods_json",
    "failure_log",
    "code_under_test_json"
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
            zip_name = r.get("zip", "").strip()
            if container:
                configs[container] = {"zip": zip_name, "flaky_test": flaky_test}
    return configs

# Standard comment and string removal helper to clean Java code
def remove_comments_and_strings(code):
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

# Extracts a method body from Java/Groovy source code
def extract_method_body(code, method_name):
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

# Caches open ZIP file references
class ZipCache:
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

# Cache of class files in ZIPs grouped by simple name to optimize lookup:
# { (zip_filename, version): { simple_class_name: [full_zip_paths] } }
zip_file_map_cache = {}

# Locates Java/Groovy file inside project ZIP
def find_class_file_in_zip(zip_ref, class_name, version="Flaky"):
    if not zip_ref:
        return None
        
    cache_key = (zip_ref.filename, version)
    if cache_key not in zip_file_map_cache:
        file_map = {}
        for name in zip_ref.namelist():
            if f"/{version}/" in name and (name.endswith(".java") or name.endswith(".groovy")):
                simple_name = name.split('/')[-1].rsplit('.', 1)[0]
                if simple_name not in file_map:
                    file_map[simple_name] = []
                file_map[simple_name].append(name)
        zip_file_map_cache[cache_key] = file_map
        
    file_map = zip_file_map_cache[cache_key]
    
    base_rel_path = class_name.replace('.', '/')
    if '$' in base_rel_path:
        base_rel_path = base_rel_path.split('$')[0]

    simple_class = base_rel_path.split('/')[-1]
    if simple_class in file_map:
        suffix_java = base_rel_path + ".java"
        suffix_groovy = base_rel_path + ".groovy"
        for path in file_map[simple_class]:
            if path.endswith(suffix_java) or path.endswith(suffix_groovy):
                return path
    return None

def is_framework_class(class_name):
    lower_name = class_name.lower()
    framework_prefixes = (
        "org.junit.",
        "junit.framework.",
        "org.mockito.",
        "org.hamcrest.",
        "org.easymock.",
        "org.jacoco.",
        "org.testng.",
        "org.assertj.",
        "com.google.common.truth.",
        "sun.reflect.",
        "java.lang.reflect.",
    )
    if any(class_name.startswith(p) for p in framework_prefixes):
        return True
    if lower_name.startswith("java.") or lower_name.startswith("javax.") or lower_name.startswith("sun."):
        return True
    return False

# Builds a variable type map from class code
def build_variable_type_map(class_code):
    clean_code = remove_comments_and_strings(class_code)
    type_map = {}
    java_keywords = {"Class", "Interface", "Enum", "Public", "Private", "Protected", "Static", "Final", "New", "Return", "Void"}
    matches = re.findall(r'\b([A-Z]\w*(?:<[^>]*>)?)\s+(\w+)\b', clean_code)
    for cls_candidate, var_candidate in matches:
        cls_simple = cls_candidate.split('<')[0].strip()
        if cls_simple in java_keywords or var_candidate in java_keywords:
            continue
        if var_candidate[0].islower():
            type_map[var_candidate] = cls_simple
    return type_map

# Resolves class name and checks parent inheritance
def get_parent_class_name(code):
    clean_code = remove_comments_and_strings(code)
    match = re.search(r'\bclass\s+(\w+)(?:\s*<[^>]+>)?(?:\s+extends\s+([\w<>.]+))?', clean_code)
    if match:
        class_name = match.group(1)
        extends_name = match.group(2)
        if extends_name:
            extends_name = extends_name.split('<')[0].strip()
        return class_name, extends_name
    return None, None

# Resolves parent class fully qualified name
def resolve_fqn(extends_name, current_class_fqn, code):
    if not extends_name:
        return None
    
    clean_code = remove_comments_and_strings(code)
    pattern = re.compile(r'\bimport\s+([\w.]+)\s*;')
    imports = pattern.findall(clean_code)
    for imp in imports:
        if imp.endswith(f".{extends_name}"):
            return imp

    package_match = re.search(r'\bpackage\s+([\w.]+)\s*;', clean_code)
    if package_match:
        return f"{package_match.group(1)}.{extends_name}"

    if '.' in current_class_fqn:
        parent_pkg = current_class_fqn.rsplit('.', 1)[0]
        return f"{parent_pkg}.{extends_name}"

    return extends_name

# Caches for expensive recursive class hierarchy traversal and file parsing:
method_body_cache = {}
imports_cache = {}
hierarchy_info_cache = {}
public_methods_cache = {}

# Recursively searches inheritance hierarchy in ZIP to find a method body
def extract_method_recursive(zip_ref, class_fqn, method_name, version="Flaky"):
    if not zip_ref:
        return None
    cache_key = (zip_ref.filename, class_fqn, method_name, version)
    if cache_key in method_body_cache:
        return method_body_cache[cache_key]

    file_path = find_class_file_in_zip(zip_ref, class_fqn, version)
    if not file_path:
        method_body_cache[cache_key] = None
        return None

    try:
        with zip_ref.open(file_path) as f:
            code = f.read().decode('utf-8', errors='ignore')
    except Exception:
        method_body_cache[cache_key] = None
        return None

    body = extract_method_body(code, method_name)
    if body:
        method_body_cache[cache_key] = body
        return body

    _, extends_name = get_parent_class_name(code)
    if extends_name:
        parent_fqn = resolve_fqn(extends_name, class_fqn, code)
        if parent_fqn and parent_fqn != class_fqn:
            res = extract_method_recursive(zip_ref, parent_fqn, method_name, version)
            method_body_cache[cache_key] = res
            return res

    method_body_cache[cache_key] = None
    return None

# Resolves imports in a test file to map simple names to FQNs
def parse_imports_from_zip_class(zip_ref, class_fqn, version="Flaky"):
    if not zip_ref:
        return {}, ""
    cache_key = (zip_ref.filename, class_fqn, version)
    if cache_key in imports_cache:
        return imports_cache[cache_key]

    file_path = find_class_file_in_zip(zip_ref, class_fqn, version)
    if not file_path:
        imports_cache[cache_key] = ({}, "")
        return {}, ""
        
    imports_map = {}
    package_name = ""
    try:
        with zip_ref.open(file_path) as f:
            code = f.read().decode('utf-8', errors='ignore')
            clean_code = remove_comments_and_strings(code)
            
            # Find package
            package_match = re.search(r'\bpackage\s+([\w.]+)\s*;', clean_code)
            if package_match:
                package_name = package_match.group(1)
                
            # Find imports
            pattern = re.compile(r'\bimport\s+(?:static\s+)?([\w.]+)\s*;')
            imports = pattern.findall(clean_code)
            for imp in imports:
                simple_name = imp.split('.')[-1]
                imports_map[simple_name] = imp
    except Exception:
        pass
    
    imports_cache[cache_key] = (imports_map, package_name)
    return imports_map, package_name

# Recursively scans class inheritance hierarchy to build a variable and import map
def collect_hierarchy_info(zip_ref, class_fqn, version="Flaky", visited=None):
    if visited is None:
        visited = set()
        
    is_top_level = (len(visited) == 0)
    if is_top_level and zip_ref:
        cache_key = (zip_ref.filename, class_fqn, version)
        if cache_key in hierarchy_info_cache:
            return hierarchy_info_cache[cache_key]

    type_map = {}
    imports_map = {}
    pkg_list = []
    
    if class_fqn in visited:
        return type_map, imports_map, pkg_list
    visited.add(class_fqn)
    
    file_path = find_class_file_in_zip(zip_ref, class_fqn, version)
    if not file_path:
        return type_map, imports_map, pkg_list
        
    try:
        with zip_ref.open(file_path) as f:
            code = f.read().decode('utf-8', errors='ignore')
            clean_code = remove_comments_and_strings(code)
            
            local_map = build_variable_type_map(code)
            type_map.update(local_map)
            
            package_match = re.search(r'\bpackage\s+([\w.]+)\s*;', clean_code)
            package_name = package_match.group(1) if package_match else ""
            if package_name:
                pkg_list.append(package_name)
                
            pattern = re.compile(r'\bimport\s+(?:static\s+)?([\w.]+)\s*;')
            imports = pattern.findall(clean_code)
            for imp in imports:
                simple_name = imp.split('.')[-1]
                imports_map[simple_name] = imp
                
            _, extends_name = get_parent_class_name(code)
            if extends_name:
                parent_fqn = resolve_fqn(extends_name, class_fqn, code)
                if parent_fqn and parent_fqn != class_fqn:
                    p_type_map, p_imports_map, p_pkg_list = collect_hierarchy_info(zip_ref, parent_fqn, version, visited)
                    for k, v in p_type_map.items():
                        if k not in type_map:
                            type_map[k] = v
                    for k, v in p_imports_map.items():
                        if k not in imports_map:
                            imports_map[k] = v
                    for pkg in p_pkg_list:
                        if pkg not in pkg_list:
                            pkg_list.append(pkg)
    except:
        pass

    result = (type_map, imports_map, pkg_list)
    if is_top_level and zip_ref:
        hierarchy_info_cache[cache_key] = result
    return result

# Resolves a simple class candidate name to FQN and verifies existence in ZIP
def resolve_class_candidate(class_candidate, imports_map, pkg_list, zip_ref, version="Flaky"):
    if class_candidate in imports_map:
        return imports_map[class_candidate]
    for pkg in pkg_list:
        fqn = f"{pkg}.{class_candidate}" if pkg else class_candidate
        if find_class_file_in_zip(zip_ref, fqn, version):
            return fqn
    if find_class_file_in_zip(zip_ref, class_candidate, version):
        return class_candidate
    return None

# Extracts all public methods and constructors from a class file in the ZIP
def extract_all_public_methods_from_class(zip_ref, class_fqn, version="Flaky"):
    if not zip_ref:
        return {}
    cache_key = (zip_ref.filename, class_fqn, version)
    if cache_key in public_methods_cache:
        return public_methods_cache[cache_key]

    file_path = find_class_file_in_zip(zip_ref, class_fqn, version)
    if not file_path:
        public_methods_cache[cache_key] = {}
        return {}
        
    try:
        with zip_ref.open(file_path) as f:
            code = f.read().decode('utf-8', errors='ignore')
            
        clean_code = remove_comments_and_strings(code)
        methods_map = {}
        
        # Match methods: public/protected return_type name(...)
        ignored_names = {"class", "interface", "enum", "new", "throws", "return", "if", "for", "while", "switch", "catch"}
        pattern = re.compile(
            r'\b(?:public|protected)\s+(?:static\s+|final\s+|synchronized\s+)*([\w<>\[\]\.]+)\s+(\w+)\s*\('
        )
        matches = pattern.findall(clean_code)
        
        for return_type, method_name in matches:
            if method_name in ignored_names:
                continue
            body = extract_method_body(code, method_name)
            if body:
                methods_map[method_name] = body
                
        # Match constructor
        class_simple = class_fqn.split('.')[-1].split('$')[-1]
        constructor_pattern = re.compile(
            r'\b(?:public|protected)\s+' + re.escape(class_simple) + r'\s*\('
        )
        if constructor_pattern.search(clean_code):
            body = extract_method_body(code, class_simple)
            if body:
                methods_map["<init>"] = body
                
        public_methods_cache[cache_key] = methods_map
        return methods_map
    except:
        public_methods_cache[cache_key] = {}
        return {}

# 1. Jacoco XML Parser for covered methods
def collect_jacoco_covered_methods(jacoco_xml_path, test_class_fqn):
    targets = set()
    if not os.path.exists(jacoco_xml_path):
        return targets
        
    try:
        context = ET.iterparse(jacoco_xml_path, events=("start", "end"))
        for event, elem in context:
            if event == "end" and elem.tag == "package":
                package_name = elem.attrib.get("name", "").replace('/', '.')
                for cls in elem.findall("class"):
                    class_name = cls.attrib.get("name", "").replace('/', '.')
                    
                    # Filter out test classes
                    if class_name == test_class_fqn or class_name.startswith(test_class_fqn + "$"):
                        continue
                    if any(class_name.endswith(suffix) for suffix in ("Test", "Tests", "TestCase", "Spec")):
                        continue
                        
                    # Filter out external/third-party frameworks
                    if is_framework_class(class_name):
                        continue
                        
                    for meth in cls.findall("method"):
                        meth_name = meth.attrib.get("name", "")
                        # Filter out constructors and class initializers
                        if meth_name in ("<init>", "<clinit>"):
                            continue
                            
                        covered = False
                        for counter in meth.findall("counter"):
                            if counter.attrib.get("type") == "METHOD" and int(counter.attrib.get("covered", 0)) > 0:
                                covered = True
                            elif counter.attrib.get("type") == "INSTRUCTION" and int(counter.attrib.get("covered", 0)) > 0:
                                covered = True
                                
                        if covered:
                            targets.add((class_name, meth_name))
                elem.clear()
    except Exception as e:
        print(f"    Error parsing Jacoco XML {jacoco_xml_path}: {e}")
        
    return targets

# 2. Failure Stack Trace Parser
def collect_stack_trace_methods(failure_log, test_class_fqn):
    targets = set()
    if not failure_log or not failure_log.strip():
        return targets
        
    # Matches frames like: at org.apache.accumulo.core.conf.SiteConfiguration.get(SiteConfiguration.java:67)
    frame_pattern = re.compile(r'at\s+([\w\.\$]+)\.([\w\<>]+\$?[\w<>]*)\([\w\.]+\.java:\d+\)')
    matches = frame_pattern.findall(failure_log)
    for class_name, meth_name in matches:
        if class_name == test_class_fqn or class_name.startswith(test_class_fqn + "$"):
            continue
        if any(class_name.endswith(suffix) for suffix in ("Test", "Tests", "TestCase", "Spec")):
            continue
            
        # Filter constructors/clinit and external libraries
        if meth_name in ("<init>", "<clinit>"):
            continue
        if is_framework_class(class_name):
            continue
            
        targets.add((class_name, meth_name))
        
    return targets

# 3. Static AST Direct Call Parser (Test Code & Helpers)
def collect_static_call_methods(flaky_test_code, flaky_helpers_json, zip_ref, test_class_fqn):
    targets = set()
    
    # Load all method bodies
    bodies = []
    if flaky_test_code:
        bodies.append(flaky_test_code)
    if flaky_helpers_json:
        if isinstance(flaky_helpers_json, str):
            try:
                helpers = json.loads(flaky_helpers_json)
            except Exception:
                helpers = {}
        else:
            helpers = flaky_helpers_json
            
        if isinstance(helpers, dict):
            for body in helpers.values():
                bodies.append(body)
            
    if not bodies:
        return targets
        
    # Get test file packages/imports/types recursively
    type_map, imports_map, pkg_list = collect_hierarchy_info(zip_ref, test_class_fqn)
    
    # Basic filters
    ignored_calls = {
        "if", "for", "while", "switch", "synchronized", "catch", "new", "super", "this",
        "return", "throw", "assert", "assertEquals", "assertTrue", "assertFalse",
        "assertNull", "assertNotNull", "assertSame", "assertNotSame", "fail", "assertThat",
        "println", "print", "wait", "notify", "notifyAll", "equals", "hashCode", "toString"
    }
    
    for body in bodies:
        clean_body = remove_comments_and_strings(body)
        
        # 1. Matches object.methodName(...) or ClassName.staticMethod(...)
        member_calls = re.findall(r'\b(\w+)\.(\w+)\s*\(', clean_body)
        for receiver, meth_name in member_calls:
            if meth_name in ignored_calls:
                continue
                
            class_candidate = None
            if receiver in type_map:
                class_candidate = type_map[receiver]
            elif receiver[0].isupper():
                class_candidate = receiver
                
            if class_candidate:
                fqn = resolve_class_candidate(class_candidate, imports_map, pkg_list, zip_ref)
                if fqn:
                    if any(fqn.endswith(suffix) for suffix in ("Test", "Tests", "TestCase", "Spec")):
                        continue
                    if is_framework_class(fqn):
                        continue
                    targets.add((fqn, meth_name))
                
        # 2. Matches constructor calls: new ClassName(...)
        constructor_calls = re.findall(r'\bnew\s+([A-Z]\w*)(?:\s*<[^>]*>)?\s*\(', clean_body)
        for class_candidate in constructor_calls:
            fqn = resolve_class_candidate(class_candidate, imports_map, pkg_list, zip_ref)
            if fqn:
                if any(fqn.endswith(suffix) for suffix in ("Test", "Tests", "TestCase", "Spec")):
                    continue
                if is_framework_class(fqn):
                    continue
                targets.add((fqn, "<init>"))
                
        # 3. Matches capitalized words (e.g. types, literals, static refs)
        words = re.findall(r'\b([A-Z]\w*)\b', clean_body)
        for word in words:
            fqn = resolve_class_candidate(word, imports_map, pkg_list, zip_ref)
            if fqn:
                if any(fqn.endswith(suffix) for suffix in ("Test", "Tests", "TestCase", "Spec")):
                    continue
                if is_framework_class(fqn):
                    continue
                targets.add((fqn, "<init>"))
                
        # 4. Matches all method calls: methodName(...)
        ignored_search_methods = {
            "if", "for", "while", "switch", "synchronized", "catch", "new", "super", "this",
            "return", "throw", "assert", "assertEquals", "assertTrue", "assertFalse",
            "assertNull", "assertNotNull", "assertSame", "assertNotSame", "fail", "assertThat",
            "println", "print", "wait", "notify", "notifyAll", "equals", "hashCode", "toString",
            "get", "size", "add", "put", "contains", "isEmpty", "values", "clear", "next",
            "hasNext", "remove", "split", "length", "write", "read", "run", "start", "stop",
            "close", "flush", "format", "substring", "replace", "valueOf", "builder", "build",
            "create", "init", "newInstance", "getInstance", "getClass"
        }
        calls = re.findall(r'\b(\w+)\s*\(', clean_body)
        for meth_name in calls:
            if meth_name in ignored_search_methods:
                continue
            candidates = []
            for imp_name, imp_fqn in imports_map.items():
                if is_framework_class(imp_fqn):
                    continue
                candidates.append(imp_fqn)
            for fqn in candidates:
                if find_class_file_in_zip(zip_ref, fqn, "Flaky"):
                    targets.add((fqn, meth_name))
                
    return targets

# Runs the Code Under Test collection for a single row
def process_single_row(row, test_configs, zip_cache):
    test_id = row.get("test_id", "")
    config = test_configs.get(test_id)
    if not config:
        return
        
    zip_name = config["zip"]
    flaky_test_str = config["flaky_test"]
    if '#' not in flaky_test_str:
        return
        
    class_fqn, method_name = flaky_test_str.split('#', 1)
    zip_ref = zip_cache.get(zip_name)
    if not zip_ref:
        return
        
    target_methods = set()
    
    # Phase 1: Try Dynamic Coverage (Jacoco XML)
    flaky_dir = os.path.join(RESULT_DIR, test_id, "result", "Flaky")
    long_flaky_dir = get_long_path(flaky_dir)
    cov_dir = os.path.join(long_flaky_dir, "coverage")
    
    jacoco_xml_path = None
    if os.path.exists(cov_dir):
        try:
            for f in os.listdir(cov_dir):
                if f.endswith(".xml") and "jacoco" in f:
                    jacoco_xml_path = os.path.join(cov_dir, f)
                    break
        except Exception:
            pass
            
    if jacoco_xml_path:
        targets_xml = collect_jacoco_covered_methods(jacoco_xml_path, class_fqn)
        target_methods.update(targets_xml)
        
    # Phase 2: Try Failure Stack Trace Parsing
    failure_log = row.get("failure_log", "")
    targets_stack = collect_stack_trace_methods(failure_log, class_fqn)
    target_methods.update(targets_stack)
    
    # Phase 3: Try Static Invocations (Fallback / Enrichment)
    test_code = row.get("test_code", "")
    helpers_json = row.get("helper_methods_json", "")
    targets_static = collect_static_call_methods(test_code, helpers_json, zip_ref, class_fqn)
    target_methods.update(targets_static)
    
    # Phase 4: Extract method bodies from ZIP
    cut_dict = {}
    for c_fqn, m_name in sorted(list(target_methods)):
        # Verify if class file exists in ZIP to avoid empty entries
        file_path = find_class_file_in_zip(zip_ref, c_fqn, "Flaky")
        if not file_path:
            continue
            
        # For constructors, search for the class's simple name as the method name
        actual_method_name = c_fqn.split('.')[-1].split('$')[-1] if m_name == "<init>" else m_name
        meth_body = extract_method_recursive(zip_ref, c_fqn, actual_method_name, "Flaky")
        if meth_body:
            if c_fqn not in cut_dict:
                cut_dict[c_fqn] = {}
            cut_dict[c_fqn][m_name] = meth_body
            
    if not cut_dict:
        # Fallback 1: Test class package imports (extract production classes imported by the test class)
        imports_map, package_name = parse_imports_from_zip_class(zip_ref, class_fqn, "Flaky")
        
        # Walk parent classes recursively to collect all imports in the hierarchy
        visited_classes = set()
        def collect_imports_recursive(fqn):
            if fqn in visited_classes:
                return {}
            visited_classes.add(fqn)
            imp_map, _ = parse_imports_from_zip_class(zip_ref, fqn, "Flaky")
            file_path = find_class_file_in_zip(zip_ref, fqn, "Flaky")
            if not file_path:
                return imp_map
            try:
                with zip_ref.open(file_path) as f:
                    code = f.read().decode('utf-8', errors='ignore')
                _, extends_name = get_parent_class_name(code)
                if extends_name:
                    parent_fqn = resolve_fqn(extends_name, fqn, code)
                    if parent_fqn and parent_fqn != fqn:
                        parent_imp_map = collect_imports_recursive(parent_fqn)
                        for k, v in parent_imp_map.items():
                            if k not in imp_map:
                                imp_map[k] = v
            except:
                pass
            return imp_map
            
        all_imports = collect_imports_recursive(class_fqn)
        
        imported_cut_classes = []
        for imp_name, imp_fqn in all_imports.items():
            if is_framework_class(imp_fqn):
                continue
            if any(imp_fqn.endswith(s) for s in ("Test", "Tests", "TestCase", "Spec")):
                continue
            if find_class_file_in_zip(zip_ref, imp_fqn, "Flaky"):
                imported_cut_classes.append(imp_fqn)
                
        if imported_cut_classes:
            for fqn in imported_cut_classes:
                meth_bodies = extract_all_public_methods_from_class(zip_ref, fqn, "Flaky")
                if meth_bodies:
                    cut_dict[fqn] = meth_bodies

    if not cut_dict:
        # Fallback 2: Name-based fallback (prefix and suffix matching, searching ZIP)
        simple_test_class = class_fqn.split('.')[-1].split('$')[-1]
        fallback_bases = []
        
        # Get base name by stripping suffix/prefix
        for suffix in ("Test", "Tests", "TestCase", "Spec"):
            if simple_test_class.endswith(suffix) and len(simple_test_class) > len(suffix):
                fallback_bases.append(simple_test_class[:-len(suffix)])
                break
        for prefix in ("Test", "Tests", "TestCase", "Spec"):
            if simple_test_class.startswith(prefix) and len(simple_test_class) > len(prefix):
                fallback_bases.append(simple_test_class[len(prefix):])
                break
                
        if fallback_bases:
            base_name = fallback_bases[0]
            package_name = class_fqn.rsplit('.', 1)[0] if '.' in class_fqn else ""
            
            # Check if a class with exactly base_name exists in the package
            resolved_fqn = f"{package_name}.{base_name}" if package_name else base_name
            if find_class_file_in_zip(zip_ref, resolved_fqn, "Flaky"):
                meth_bodies = extract_all_public_methods_from_class(zip_ref, resolved_fqn, "Flaky")
                if meth_bodies:
                    cut_dict[resolved_fqn] = meth_bodies
            
            # If not found, search the ZIP for any production class in the package whose name starts with or contains base_name
            if not cut_dict and package_name:
                package_prefix = package_name.replace('.', '/')
                for name in zip_ref.namelist():
                    if "/Flaky/" in name and package_prefix in name and name.endswith(".java"):
                        parts = name.split('/')
                        simple_name = parts[-1][:-5]
                        if not any(simple_name.endswith(s) for s in ("Test", "Tests", "TestCase", "Spec")):
                            if base_name.lower() in simple_name.lower():
                                class_fqn_candidate = f"{package_name}.{simple_name}"
                                meth_bodies = extract_all_public_methods_from_class(zip_ref, class_fqn_candidate, "Flaky")
                                if meth_bodies:
                                    cut_dict[class_fqn_candidate] = meth_bodies

    if not cut_dict:
        # Fallback 3: Repository-level common classes (e.g. JSON, ObjectMapper, Gson)
        core_candidates = [
            "com.alibaba.fastjson.JSON",
            "com.alibaba.fastjson2.JSON",
            "com.fasterxml.jackson.databind.ObjectMapper",
            "com.google.gson.Gson"
        ]
        for fqn in core_candidates:
            if find_class_file_in_zip(zip_ref, fqn, "Flaky"):
                meth_bodies = extract_all_public_methods_from_class(zip_ref, fqn, "Flaky")
                if meth_bodies:
                    cut_dict[fqn] = meth_bodies
                    break
            
    # Save results
    row["code_under_test_json"] = cut_dict if cut_dict else {}

# Main runner
def run_cut_extraction(limit=None, force=False):
    csv_rows = read_common_dataset()
    if not csv_rows:
        print("Error: context_enriched_dataset.csv is empty or missing.")
        return
        
    test_configs = load_test_configs()
    zip_cache = ZipCache(DATA_DIR)
    processed_count = 0
    
    print(f"Beginning Step 4 Code Under Test Extraction for {len(csv_rows)} records...")
    
    try:
        for idx, row in enumerate(csv_rows):
            test_id = row.get("test_id", "")
            config = test_configs.get(test_id)
            if not config:
                continue
                
            has_cut = row.get("code_under_test_json")
            if has_cut:
                if isinstance(has_cut, dict):
                    if has_cut and not force:
                        continue
                elif isinstance(has_cut, str) and has_cut.strip() and has_cut.strip() != "{}" and not force:
                    continue
                
            if limit is not None and processed_count >= limit:
                break
                
            print(f"Extracting CUT ({processed_count+1}/{limit if limit else len(csv_rows)}): {test_id}...")
            process_single_row(row, test_configs, zip_cache)
            
            processed_count += 1
            
            if processed_count % 50 == 0:
                write_common_dataset(csv_rows, CUT_HEADERS)
                
        write_common_dataset(csv_rows, CUT_HEADERS)
        print(f"Successfully processed and updated {processed_count} CUT records in common CSV.")
        
    finally:
        zip_cache.close_all()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CAFlake Stage 4: Code Under Test Extractor",
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
        help="Force overwrite of already extracted CUT values."
    )
    args = parser.parse_args()
    
    limit_val = None if args.limit <= 0 else args.limit
    run_cut_extraction(limit=limit_val, force=args.force)
