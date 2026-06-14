#!/usr/bin/env python3
import os
import sys
import re
import json
import argparse
import subprocess

# Allow importing config and utils from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import PROJECTS_DIR, REPOS_DIR
from utils import (
    read_common_dataset,
    write_common_dataset,
    resolve_test_class_method,
)

# Shared 10-column dataset schema
CUT_HEADERS = [
    "id",
    "test_id",
    "flaky_category",
    "repo_url",
    "flaky_commit",
    "fixed_commit",
    "flaky_test_code",
    "flaky_helper_methods_json",
    "flaky_failure_log",
    "flaky_code_under_test_json",
]

# Bare repo directory mapping (same as Stage 2)
REPO_DIR_NAMES = {
    "Chart":          "jfreechart.git",
    "Cli":            "commons-cli.git",
    "Closure":        "closure-compiler.git",
    "Codec":          "commons-codec.git",
    "Collections":    "commons-collections.git",
    "Compress":       "commons-compress.git",
    "Csv":            "commons-csv.git",
    "Gson":           "gson.git",
    "JacksonCore":    "jackson-core.git",
    "JacksonDatabind":"jackson-databind.git",
    "JacksonXml":     "jackson-dataformat-xml.git",
    "Jsoup":          "jsoup.git",
    "JxPath":         "commons-jxpath.git",
    "Lang":           "commons-lang.git",
    "Math":           "commons-math.git",
    "Mockito":        "mockito.git",
    "Time":           "joda-time.git",
}

# ─────────────────────────────────────────────────────────
#  Caches for structural resolution
# ─────────────────────────────────────────────────────────
_dir_layout_cache = {}
_ls_tree_cache = {}
_hierarchy_cache = {}
_imports_cache = {}
_public_methods_cache = {}
_method_body_cache = {}

# ─────────────────────────────────────────────────────────
#  dir-layout.csv helpers
# ─────────────────────────────────────────────────────────
def load_dir_layouts(project):
    if project in _dir_layout_cache:
        return _dir_layout_cache[project]
    layout = {}
    path = os.path.join(PROJECTS_DIR, project, "dir-layout.csv")
    if not os.path.exists(path):
        _dir_layout_cache[project] = layout
        return layout
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 3:
                commit_sha, src_dir, test_dir = parts[0], parts[1], parts[2]
                layout[commit_sha] = (src_dir.strip(), test_dir.strip())
    _dir_layout_cache[project] = layout
    return layout

def get_project_dirs(project, commit_sha):
    layout = load_dir_layouts(project)
    if commit_sha in layout:
        return layout[commit_sha]
    if layout:
        from collections import Counter
        most_common_src = Counter(v[0] for v in layout.values()).most_common(1)[0][0]
        most_common_test = Counter(v[1] for v in layout.values()).most_common(1)[0][0]
        return most_common_src, most_common_test
    return "src/main/java", "src/test/java"  # universal fallback

# ─────────────────────────────────────────────────────────
#  Git helpers
# ─────────────────────────────────────────────────────────
def get_repo_path(project):
    dir_name = REPO_DIR_NAMES.get(project)
    if not dir_name:
        return None
    path = os.path.join(REPOS_DIR, dir_name)
    if not os.path.exists(path):
        return None
    return path

def git_show_file(repo_path, commit_sha, file_path):
    cmd = ["git", "--git-dir", repo_path, "show", f"{commit_sha}:{file_path}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None

_ls_tree_sets = {}

def git_ls_tree(repo_path, commit_sha):
    key = (repo_path, commit_sha)
    if key in _ls_tree_cache:
        return _ls_tree_cache[key]
    cmd = ["git", "--git-dir", repo_path, "ls-tree", "-r", "--name-only", commit_sha]
    files = []
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if result.returncode == 0:
            files = result.stdout.splitlines()
    except Exception:
        pass
    _ls_tree_cache[key] = files
    _ls_tree_sets[key] = set(files)
    return files

def get_ls_tree_set(repo_path, commit_sha):
    key = (repo_path, commit_sha)
    if key in _ls_tree_sets:
        return _ls_tree_sets[key]
    git_ls_tree(repo_path, commit_sha)
    return _ls_tree_sets.get(key, set())

def find_class_file_in_repo(repo_path, commit_sha, class_fqn, src_dir):
    base_fqn = class_fqn.split("$")[0]
    rel_path = base_fqn.replace(".", "/") + ".java"
    candidate = f"{src_dir}/{rel_path}"

    files_set = get_ls_tree_set(repo_path, commit_sha)
    if candidate in files_set:
        return candidate

    # Fallback: search tree for matching filename
    simple_name = base_fqn.split(".")[-1] + ".java"
    all_files = git_ls_tree(repo_path, commit_sha)
    for f in all_files:
        if f.endswith(simple_name):
            # Fast check: package suffix match (prevents starting git show subprocess)
            if f.endswith(rel_path):
                return f
            # Strip source dir prefix if present to derive FQN
            stripped = f
            if src_dir and f.startswith(src_dir + "/"):
                stripped = f[len(src_dir)+1:]
            elif f.startswith("src/main/java/"):
                stripped = f[len("src/main/java/"):]
            elif f.startswith("src/test/java/"):
                stripped = f[len("src/test/java/"):]
            elif f.startswith("src/"):
                stripped = f[len("src/"):]
            elif f.startswith("source/"):
                stripped = f[len("source/"):]
            elif f.startswith("tests/"):
                stripped = f[len("tests/"):]
            
            derived_fqn = stripped.rsplit(".", 1)[0].replace("/", ".")
            if derived_fqn == base_fqn:
                return f
    return None

# ─────────────────────────────────────────────────────────
#  Java structural analysis helpers
# ─────────────────────────────────────────────────────────
def remove_comments_and_strings(code):
    clean = []
    i, n = 0, len(code)
    state = "code"
    while i < n:
        char = code[i]
        next_char = code[i + 1] if i + 1 < n else ""
        if state == "code":
            if char == '"':
                state = "string"; clean.append(" ")
            elif char == "'":
                state = "char"; clean.append(" ")
            elif char == "/" and next_char == "/":
                state = "line_comment"; clean.append("  "); i += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"; clean.append("  "); i += 1
            else:
                clean.append(char)
        elif state == "string":
            if char == "\\":
                clean.append("  "); i += 1
            elif char == '"':
                state = "code"; clean.append(" ")
            else:
                clean.append(" ")
        elif state == "char":
            if char == "\\":
                clean.append("  "); i += 1
            elif char == "'":
                state = "code"; clean.append(" ")
            else:
                clean.append(" ")
        elif state == "line_comment":
            if char == "\n":
                state = "code"; clean.append("\n")
            else:
                clean.append(" ")
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                state = "code"; clean.append("  "); i += 1
            elif char == "\n":
                clean.append("\n")
            else:
                clean.append(" ")
        i += 1
    return "".join(clean)

def extract_method_body(code, method_name):
    clean_code = remove_comments_and_strings(code)
    pattern = re.compile(
        r"(?<!\.)\b(?:public|protected|private|static|final|synchronized|void|(?!new\b)[\w<>\[\]\.]+)\s+"
        + re.escape(method_name) + r"\b\s*\("
    )
    match = pattern.search(clean_code)
    if not match:
        return None

    name_start = match.start()
    name_m = re.search(r"\b" + re.escape(method_name) + r"\b", clean_code[name_start:])
    if name_m:
        name_start += name_m.start()

    brace_start = clean_code.find("{", name_start)
    semi = clean_code.find(";", name_start)
    if brace_start == -1 or (semi != -1 and semi < brace_start):
        return None

    depth = 1
    i = brace_start + 1
    n = len(clean_code)
    while i < n and depth > 0:
        if clean_code[i] == "{":
            depth += 1
        elif clean_code[i] == "}":
            depth -= 1
        i += 1
    if depth > 0:
        return None
    brace_end = i

    start_idx = name_start
    while start_idx > 0:
        if code[start_idx - 1] in (";", "{", "}"):
            break
        start_idx -= 1

    return code[start_idx:brace_end].strip()

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

def resolve_fqn(extends_name, current_class_fqn, code):
    if not extends_name:
        return None
    clean = remove_comments_and_strings(code)
    imports = re.findall(r'\bimport\s+([\w.]+)\s*;', clean)
    for imp in imports:
        if imp.endswith(f".{extends_name}"):
            return imp
    pkg = re.search(r'\bpackage\s+([\w.]+)\s*;', clean)
    if pkg:
        return f"{pkg.group(1)}.{extends_name}"
    if '.' in current_class_fqn:
        return f"{current_class_fqn.rsplit('.', 1)[0]}.{extends_name}"
    return extends_name

def is_framework_class(class_name):
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
    lower_name = class_name.lower()
    if lower_name.startswith("java.") or lower_name.startswith("javax.") or lower_name.startswith("sun."):
        return True
    return False

# ─────────────────────────────────────────────────────────
#  Recursive extraction & lookup functions
# ─────────────────────────────────────────────────────────
def extract_method_recursive(repo_path, commit_sha, class_fqn, method_name, src_dir):
    cache_key = (repo_path, commit_sha, class_fqn, method_name)
    if cache_key in _method_body_cache:
        return _method_body_cache[cache_key]

    file_path = find_class_file_in_repo(repo_path, commit_sha, class_fqn, src_dir)
    if not file_path:
        _method_body_cache[cache_key] = None
        return None

    code = git_show_file(repo_path, commit_sha, file_path)
    if not code:
        _method_body_cache[cache_key] = None
        return None

    body = extract_method_body(code, method_name)
    if body:
        _method_body_cache[cache_key] = body
        return body

    _, extends_name = get_parent_class_name(code)
    if extends_name:
        parent_fqn = resolve_fqn(extends_name, class_fqn, code)
        if parent_fqn and parent_fqn != class_fqn:
            res = extract_method_recursive(repo_path, commit_sha, parent_fqn, method_name, src_dir)
            _method_body_cache[cache_key] = res
            return res

    _method_body_cache[cache_key] = None
    return None

def parse_imports_from_repo_class(repo_path, commit_sha, class_fqn, test_src_dir):
    cache_key = (repo_path, commit_sha, class_fqn)
    if cache_key in _imports_cache:
        return _imports_cache[cache_key]

    file_path = find_class_file_in_repo(repo_path, commit_sha, class_fqn, test_src_dir)
    if not file_path:
        _imports_cache[cache_key] = ({}, "")
        return {}, ""

    imports_map = {}
    package_name = ""
    code = git_show_file(repo_path, commit_sha, file_path)
    if code:
        clean_code = remove_comments_and_strings(code)
        package_match = re.search(r'\bpackage\s+([\w.]+)\s*;', clean_code)
        if package_match:
            package_name = package_match.group(1)

        pattern = re.compile(r'\bimport\s+(?:static\s+)?([\w.]+)\s*;')
        imports = pattern.findall(clean_code)
        for imp in imports:
            simple_name = imp.split('.')[-1]
            imports_map[simple_name] = imp

    _imports_cache[cache_key] = (imports_map, package_name)
    return imports_map, package_name

def collect_hierarchy_info(repo_path, commit_sha, class_fqn, test_src_dir, visited=None):
    if visited is None:
        visited = set()
    is_top_level = (len(visited) == 0)
    cache_key = (repo_path, commit_sha, class_fqn)
    if is_top_level and cache_key in _hierarchy_cache:
        return _hierarchy_cache[cache_key]

    type_map = {}
    imports_map = {}
    pkg_list = []

    if class_fqn in visited:
        return type_map, imports_map, pkg_list
    visited.add(class_fqn)

    file_path = find_class_file_in_repo(repo_path, commit_sha, class_fqn, test_src_dir)
    if not file_path:
        return type_map, imports_map, pkg_list

    code = git_show_file(repo_path, commit_sha, file_path)
    if not code:
        return type_map, imports_map, pkg_list

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
            p_type_map, p_imports_map, p_pkg_list = collect_hierarchy_info(
                repo_path, commit_sha, parent_fqn, test_src_dir, visited
            )
            for k, v in p_type_map.items():
                if k not in type_map:
                    type_map[k] = v
            for k, v in p_imports_map.items():
                if k not in imports_map:
                    imports_map[k] = v
            for pkg in p_pkg_list:
                if pkg not in pkg_list:
                    pkg_list.append(pkg)

    result = (type_map, imports_map, pkg_list)
    if is_top_level:
        _hierarchy_cache[cache_key] = result
    return result

def resolve_class_candidate(class_candidate, imports_map, pkg_list, repo_path, commit_sha, src_dir):
    if class_candidate in imports_map:
        return imports_map[class_candidate]
    for pkg in pkg_list:
        fqn = f"{pkg}.{class_candidate}" if pkg else class_candidate
        if find_class_file_in_repo(repo_path, commit_sha, fqn, src_dir):
            return fqn
    if find_class_file_in_repo(repo_path, commit_sha, class_candidate, src_dir):
        return class_candidate
    return None

def extract_all_public_methods_from_class(repo_path, commit_sha, class_fqn, src_dir):
    cache_key = (repo_path, commit_sha, class_fqn)
    if cache_key in _public_methods_cache:
        return _public_methods_cache[cache_key]

    file_path = find_class_file_in_repo(repo_path, commit_sha, class_fqn, src_dir)
    if not file_path:
        _public_methods_cache[cache_key] = {}
        return {}

    code = git_show_file(repo_path, commit_sha, file_path)
    if not code:
        _public_methods_cache[cache_key] = {}
        return {}

    clean_code = remove_comments_and_strings(code)
    methods_map = {}

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

    class_simple = class_fqn.split('.')[-1].split('$')[-1]
    constructor_pattern = re.compile(
        r'\b(?:public|protected)\s+' + re.escape(class_simple) + r'\s*\('
    )
    if constructor_pattern.search(clean_code):
        body = extract_method_body(code, class_simple)
        if body:
            methods_map["<init>"] = body

    _public_methods_cache[cache_key] = methods_map
    return methods_map

# ─────────────────────────────────────────────────────────
#  Failing Stack Trace Parser
# ─────────────────────────────────────────────────────────
def collect_stack_trace_methods(failure_log, test_class_fqn):
    targets = set()
    if not failure_log or not failure_log.strip():
        return targets
    frame_pattern = re.compile(r'at\s+([\w\.\$]+)\.([\w\<>]+\$?[\w<>]*)\([\w\.]+\.java:\d+\)')
    matches = frame_pattern.findall(failure_log)
    for class_name, meth_name in matches:
        if class_name == test_class_fqn or class_name.startswith(test_class_fqn + "$"):
            continue
        if any(class_name.endswith(suffix) for suffix in ("Test", "Tests", "TestCase", "Spec")):
            continue
        if meth_name in ("<init>", "<clinit>"):
            continue
        if is_framework_class(class_name):
            continue
        targets.add((class_name, meth_name))
    return targets

# ─────────────────────────────────────────────────────────
#  Static AST Call Parser
# ─────────────────────────────────────────────────────────
def collect_static_call_methods(flaky_test_code, flaky_helpers_json, repo_path, commit_sha, test_class_fqn, test_src_dir, src_dir):
    targets = set()
    bodies = []
    if flaky_test_code:
        bodies.append(flaky_test_code)
    if flaky_helpers_json:
        try:
            helpers = json.loads(flaky_helpers_json)
            for body in helpers.values():
                bodies.append(body)
        except Exception:
            pass

    if not bodies:
        return targets

    type_map, imports_map, pkg_list = collect_hierarchy_info(repo_path, commit_sha, test_class_fqn, test_src_dir)

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
                fqn = resolve_class_candidate(class_candidate, imports_map, pkg_list, repo_path, commit_sha, src_dir)
                if fqn:
                    if any(fqn.endswith(suffix) for suffix in ("Test", "Tests", "TestCase", "Spec")):
                        continue
                    if is_framework_class(fqn):
                        continue
                    targets.add((fqn, meth_name))

        # 2. Matches constructor calls: new ClassName(...)
        constructor_calls = re.findall(r'\bnew\s+([A-Z]\w*)(?:\s*<[^>]*>)?\s*\(', clean_body)
        for class_candidate in constructor_calls:
            fqn = resolve_class_candidate(class_candidate, imports_map, pkg_list, repo_path, commit_sha, src_dir)
            if fqn:
                if any(fqn.endswith(suffix) for suffix in ("Test", "Tests", "TestCase", "Spec")):
                    continue
                if is_framework_class(fqn):
                    continue
                targets.add((fqn, "<init>"))

        # 3. Matches capitalized words
        words = re.findall(r'\b([A-Z]\w*)\b', clean_body)
        for word in words:
            fqn = resolve_class_candidate(word, imports_map, pkg_list, repo_path, commit_sha, src_dir)
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
                if find_class_file_in_repo(repo_path, commit_sha, fqn, src_dir):
                    targets.add((fqn, meth_name))

    return targets

# ─────────────────────────────────────────────────────────
#  Main single row processing
# ─────────────────────────────────────────────────────────
def process_single_row(row):
    test_id = row.get("test_id", "")
    project = test_id.split("-")[0]
    buggy_commit = row.get("flaky_commit", "").strip()

    repo_path = get_repo_path(project)
    if not repo_path:
        return

    test_class, test_method = resolve_test_class_method(test_id, PROJECTS_DIR)
    if not test_class or not test_method:
        return

    src_dir, test_src_dir = get_project_dirs(project, buggy_commit)

    target_methods = set()

    # Phase 1: Try Failure Stack Trace Parsing
    failure_log = row.get("flaky_failure_log", "")
    # Strip the "Failed Rounds: N/M\n" prefix for parsing
    if failure_log.startswith("Failed Rounds:"):
        parts = failure_log.split("\n", 1)
        failure_log_parsed = parts[1] if len(parts) > 1 else ""
    else:
        failure_log_parsed = failure_log

    targets_stack = collect_stack_trace_methods(failure_log_parsed, test_class)
    target_methods.update(targets_stack)

    # Phase 2: Try Static Invocations (from flaky_test_code and flaky_helper_methods_json)
    test_code = row.get("flaky_test_code", "")
    helpers_json = row.get("flaky_helper_methods_json", "")
    targets_static = collect_static_call_methods(
        test_code, helpers_json, repo_path, buggy_commit,
        test_class, test_src_dir, src_dir
    )
    target_methods.update(targets_static)

    # Phase 3: Extract method bodies from Repo
    cut_dict = {}
    for c_fqn, m_name in sorted(list(target_methods)):
        file_path = find_class_file_in_repo(repo_path, buggy_commit, c_fqn, src_dir)
        if not file_path:
            continue
        actual_method_name = c_fqn.split('.')[-1].split('$')[-1] if m_name == "<init>" else m_name
        meth_body = extract_method_recursive(repo_path, buggy_commit, c_fqn, actual_method_name, src_dir)
        if meth_body:
            if c_fqn not in cut_dict:
                cut_dict[c_fqn] = {}
            cut_dict[c_fqn][m_name] = meth_body

    if not cut_dict:
        # Fallback 1: Test class package imports
        imports_map, package_name = parse_imports_from_repo_class(repo_path, buggy_commit, test_class, test_src_dir)
        
        visited_classes = set()
        def collect_imports_recursive(fqn):
            if fqn in visited_classes:
                return {}
            visited_classes.add(fqn)
            imp_map, _ = parse_imports_from_repo_class(repo_path, buggy_commit, fqn, test_src_dir)
            file_path = find_class_file_in_repo(repo_path, buggy_commit, fqn, test_src_dir)
            if not file_path:
                return imp_map
            code = git_show_file(repo_path, buggy_commit, file_path)
            if code:
                _, extends_name = get_parent_class_name(code)
                if extends_name:
                    parent_fqn = resolve_fqn(extends_name, fqn, code)
                    if parent_fqn and parent_fqn != fqn:
                        parent_imp_map = collect_imports_recursive(parent_fqn)
                        for k, v in parent_imp_map.items():
                            if k not in imp_map:
                                imp_map[k] = v
            return imp_map

        all_imports = collect_imports_recursive(test_class)
        imported_cut_classes = []
        for imp_name, imp_fqn in all_imports.items():
            if is_framework_class(imp_fqn):
                continue
            if any(imp_fqn.endswith(s) for s in ("Test", "Tests", "TestCase", "Spec")):
                continue
            if find_class_file_in_repo(repo_path, buggy_commit, imp_fqn, src_dir):
                imported_cut_classes.append(imp_fqn)

        if imported_cut_classes:
            for fqn in imported_cut_classes:
                meth_bodies = extract_all_public_methods_from_class(repo_path, buggy_commit, fqn, src_dir)
                if meth_bodies:
                    cut_dict[fqn] = meth_bodies

    if not cut_dict:
        # Fallback 2: Name-based fallback
        simple_test_class = test_class.split('.')[-1].split('$')[-1]
        fallback_bases = []
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
            package_name = test_class.rsplit('.', 1)[0] if '.' in test_class else ""
            resolved_fqn = f"{package_name}.{base_name}" if package_name else base_name
            if find_class_file_in_repo(repo_path, buggy_commit, resolved_fqn, src_dir):
                meth_bodies = extract_all_public_methods_from_class(repo_path, buggy_commit, resolved_fqn, src_dir)
                if meth_bodies:
                    cut_dict[resolved_fqn] = meth_bodies

            if not cut_dict and package_name:
                package_prefix = package_name.replace('.', '/')
                all_files = git_ls_tree(repo_path, buggy_commit)
                for name in all_files:
                    if package_prefix in name and name.endswith(".java"):
                        parts = name.split('/')
                        simple_name = parts[-1][:-5]
                        if not any(simple_name.endswith(s) for s in ("Test", "Tests", "TestCase", "Spec")):
                            if base_name.lower() in simple_name.lower():
                                class_fqn_candidate = f"{package_name}.{simple_name}"
                                meth_bodies = extract_all_public_methods_from_class(repo_path, buggy_commit, class_fqn_candidate, src_dir)
                                if meth_bodies:
                                    cut_dict[class_fqn_candidate] = meth_bodies

    if not cut_dict:
        # Fallback 3: Common core helper candidates
        core_candidates = [
            "com.alibaba.fastjson.JSON",
            "com.alibaba.fastjson2.JSON",
            "com.fasterxml.jackson.databind.ObjectMapper",
            "com.google.gson.Gson"
        ]
        for fqn in core_candidates:
            if find_class_file_in_repo(repo_path, buggy_commit, fqn, src_dir):
                meth_bodies = extract_all_public_methods_from_class(repo_path, buggy_commit, fqn, src_dir)
                if meth_bodies:
                    cut_dict[fqn] = meth_bodies
                    break

    row["flaky_code_under_test_json"] = json.dumps(cut_dict, ensure_ascii=False) if cut_dict else ""

# ─────────────────────────────────────────────────────────
#  Main runner
# ─────────────────────────────────────────────────────────
def run_cut_extraction(limit=None, force=False):
    rows = read_common_dataset()
    if not rows:
        print("No rows found in non_flaky_dataset.csv. Run previous stages first.")
        return

    processed = 0
    skipped_no_repo = set()

    for row in rows:
        if limit is not None and processed >= limit:
            break

        # Skip if already filled and not forcing
        has_cut = row.get("flaky_code_under_test_json", "").strip()
        if has_cut and has_cut != "{}" and not force:
            continue

        test_id = row.get("test_id", "")
        project = test_id.split("-")[0]

        repo_path = get_repo_path(project)
        if not repo_path:
            if project not in skipped_no_repo:
                print(f"  Skipping project {project}: bare repo not found in {REPOS_DIR}")
                skipped_no_repo.add(project)
            continue

        process_single_row(row)
        processed += 1

        # Print some summary info
        cut_len = len(row.get("flaky_code_under_test_json", ""))
        print(f"  ({processed}) {test_id} CUT: {cut_len} chars JSON")

        if processed % 100 == 0:
            write_common_dataset(rows, CUT_HEADERS)

    write_common_dataset(rows, CUT_HEADERS)
    print()
    print(f"Stage 4 complete. Extracted code under test for {processed} records.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CANonFlake Stage 4: Code Under Test Extractor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--limit", "-l",
        type=int, default=0,
        help="Limit number of records to process. 0 = no limit."
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force re-extraction of already-filled rows."
    )
    args = parser.parse_args()
    limit_val = None if args.limit <= 0 else args.limit
    run_cut_extraction(limit=limit_val, force=args.force)
