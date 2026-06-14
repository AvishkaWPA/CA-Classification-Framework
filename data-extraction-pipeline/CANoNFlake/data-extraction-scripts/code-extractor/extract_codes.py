#!/usr/bin/env python3
import os
import re
import csv
import sys
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
    parse_trigger_file,
)

# Stage 2 fills these columns (all 12 are preserved)
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
    "helper_methods_json",
    "failure_log",
    "code_under_test_json",
]

# Maps Defects4J project name → bare repo directory name inside project_repos/
# Names match those extracted from defects4j-repos-v3.zip
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
#  dir-layout.csv helpers
# ─────────────────────────────────────────────────────────

# Cache: project → {commit_sha: test_dir}
_dir_layout_cache = {}

def load_dir_layout(project):
    # Returns dict: {commit_sha → test_src_dir}
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
                commit_sha, _src_dir, test_dir = parts[0], parts[1], parts[2]
                layout[commit_sha] = test_dir.strip()
    _dir_layout_cache[project] = layout
    return layout

def get_test_src_dir(project, commit_sha):
    # Returns the test source directory (e.g. 'src/test/java') for a given commit.
    # Falls back to the most common value if the exact SHA is not listed.
    layout = load_dir_layout(project)
    if commit_sha in layout:
        return layout[commit_sha]
    # Fallback: use most common test_dir across all commits in this project
    if layout:
        from collections import Counter
        most_common = Counter(layout.values()).most_common(1)[0][0]
        return most_common
    return "src/test/java"  # universal fallback


# ─────────────────────────────────────────────────────────
#  Git helpers (works on bare repos via git show)
# ─────────────────────────────────────────────────────────

def get_repo_path(project):
    # Returns the absolute path to the bare .git repo for a project.
    dir_name = REPO_DIR_NAMES.get(project)
    if not dir_name:
        return None
    path = os.path.join(REPOS_DIR, dir_name)
    if not os.path.exists(path):
        return None
    return path

def git_show_file(repo_path, commit_sha, file_path):
    # Reads a file from a bare git repo at a specific commit.
    # Returns the file content string, or None on failure.
    cmd = ["git", "--git-dir", repo_path, "show", f"{commit_sha}:{file_path}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if result.returncode == 0:
            return result.stdout
    except Exception as e:
        pass
    return None

def git_ls_tree(repo_path, commit_sha, tree_path=""):
    # Lists all files in a directory tree at a given commit.
    # Returns list of file path strings.
    cmd = ["git", "--git-dir", repo_path, "ls-tree", "-r", "--name-only", commit_sha]
    if tree_path:
        cmd.append(tree_path)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if result.returncode == 0:
            return result.stdout.splitlines()
    except Exception:
        pass
    return []

def find_test_file_in_repo(repo_path, commit_sha, test_class_fqn, test_src_dir):
    # Finds the .java file path for a test class inside the bare git repo.
    # test_class_fqn: e.g. "org.apache.commons.lang3.math.NumberUtilsTest"
    # Returns the git tree path string (e.g. "src/test/java/org/apache/.../NumberUtilsTest.java")
    # or None if not found.

    # Build expected relative path from FQN
    # Strip inner class suffixes like $Inner
    base_fqn = test_class_fqn.split("$")[0]
    rel_path = base_fqn.replace(".", "/") + ".java"
    candidate = f"{test_src_dir}/{rel_path}"

    # Try direct path first (fast path)
    content = git_show_file(repo_path, commit_sha, candidate)
    if content:
        return candidate

    # Fallback: search the full tree for the filename
    simple_name = base_fqn.split(".")[-1] + ".java"
    all_files = git_ls_tree(repo_path, commit_sha)
    for f in all_files:
        if f.endswith(simple_name) and ("test" in f.lower() or "spec" in f.lower()):
            # Verify it's actually the right class by checking package
            check = git_show_file(repo_path, commit_sha, f)
            if check and base_fqn.split(".")[-1] in check:
                return f

    # Widest fallback: any file matching the simple class name
    for f in all_files:
        if f.endswith(simple_name):
            return f

    return None


# ─────────────────────────────────────────────────────────
#  Java code extraction (brace-counting parser)
#  Reused logic from CAFlake's extract_codes.py
# ─────────────────────────────────────────────────────────

def remove_comments_and_strings(code):
    # Strips Java comments and string literals for structural analysis.
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
    # Extracts a method body from Java source by brace counting.
    # Returns the full method string (signature + body) or None.
    #
    # Search is performed on comment-stripped code to avoid false matches
    # inside Javadoc comment lines (e.g. "* Added testFoo()").
    clean_code = remove_comments_and_strings(code)

    pattern = re.compile(
        r"(?<!\.)\b(?:public|protected|private|static|final|synchronized|void|(?!new\b)[\w<>\[\]\.]+)\s+"
        + re.escape(method_name) + r"\b\s*\("
    )
    match = pattern.search(clean_code)
    if not match:
        return None

    name_start = match.start()
    # Refine name_start to point exactly at the method name token
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

def get_parent_class(code):
    # Returns (class_name, extends_name) from a Java class declaration.
    clean = remove_comments_and_strings(code)
    m = re.search(r"\bclass\s+(\w+)(?:\s*<[^>]+>)?(?:\s+extends\s+([\w<>.]+))?", clean)
    if m:
        return m.group(1), (m.group(2).split("<")[0].strip() if m.group(2) else None)
    return None, None

def resolve_parent_fqn(extends_name, class_fqn, code):
    if not extends_name:
        return None
    clean = remove_comments_and_strings(code)
    imports = re.findall(r"\bimport\s+([\w.]+)\s*;", clean)
    for imp in imports:
        if imp.endswith(f".{extends_name}"):
            return imp
    pkg = re.search(r"\bpackage\s+([\w.]+)\s*;", clean)
    if pkg:
        return f"{pkg.group(1)}.{extends_name}"
    if "." in class_fqn:
        return f"{class_fqn.rsplit('.', 1)[0]}.{extends_name}"
    return extends_name

def extract_helper_methods(code, test_method_name, class_fqn, repo_path, commit_sha, test_src_dir):
    # Finds helper methods called by the test method and returns them as a dict.
    # Handles single-level inheritance (walks up one parent class if needed).
    method_body = extract_method_body(code, test_method_name)
    if not method_body:
        return {}

    clean_code = remove_comments_and_strings(code)
    # Collect all method names defined in this class
    defined_methods = set(re.findall(
        r"\b(?:public|protected|private|static|final|void|[\w<>\[\]]+)\s+(\w+)\s*\(", clean_code
    ))
    # Find method calls inside the test body
    called = set(re.findall(r"\b(\w+)\s*\(", remove_comments_and_strings(method_body)))

    ignore = {
        test_method_name, "if", "for", "while", "switch", "catch", "new",
        "super", "this", "return", "throw", "assert", "assertEquals",
        "assertTrue", "assertFalse", "assertNull", "assertNotNull",
        "assertSame", "assertNotSame", "fail", "assertThat",
        "println", "print", "wait", "notify", "notifyAll",
        "equals", "hashCode", "toString", "get", "set", "size",
        "add", "put", "remove", "contains", "isEmpty",
    }

    helpers = {}
    for m in called - ignore:
        if m not in defined_methods:
            continue
        body = extract_method_body(code, m)
        if body:
            helpers[m] = body

    # Walk parent class for inherited helpers
    _, extends_name = get_parent_class(code)
    if extends_name:
        parent_fqn = resolve_parent_fqn(extends_name, class_fqn, code)
        if parent_fqn:
            parent_file = find_test_file_in_repo(repo_path, commit_sha, parent_fqn, test_src_dir)
            if parent_file:
                parent_code = git_show_file(repo_path, commit_sha, parent_file)
                if parent_code:
                    for m in called - ignore:
                        if m in helpers:
                            continue
                        body = extract_method_body(parent_code, m)
                        if body:
                            helpers[m] = body

    return helpers


# ─────────────────────────────────────────────────────────
#  Main extraction logic
# ─────────────────────────────────────────────────────────

def extract_project_from_test_id(test_id):
    # "Lang-1" → "Lang",  "Chart-14-3" → "Chart"
    return test_id.split("-")[0]


# ─────────────────────────────────────────────────────────
#  Chart / SVN fallback: extract test code from test.patch
# ─────────────────────────────────────────────────────────

def extract_from_test_patch(project, bug_id, test_method):
    # Fallback for SVN-based projects (e.g. Chart) where the bare git repo
    # uses SVN revision numbers, not git SHAs.
    #
    # In D4J test.patch for SVN projects:
    #   --- ... (revision N_fixed)   ← source = fixed state (HAS the test)
    #   +++ ... (revision N_buggy)   ← dest   = buggy state (test removed)
    #   Lines starting with '-' are ONLY in the fixed state (i.e. contain the test)
    #   Lines starting with '+' are ONLY in the buggy state
    #   Lines starting with ' '  are context (common to both)
    #
    # Strategy: try extracting from '-' lines only first (cleanest), then
    # fall back to '-' + context lines if the method spans context sections.
    patch_path = os.path.join(PROJECTS_DIR, project, "patches", f"{bug_id}.test.patch")
    if not os.path.exists(patch_path):
        return None, {}

    with open(patch_path, encoding="utf-8", errors="ignore") as f:
        patch_text = f.read()

    def build_reconstruction(include_context):
        lines = []
        in_hunk = False
        for line in patch_text.splitlines():
            if line.startswith("@@"):
                in_hunk = True
                continue
            if (line.startswith("---") or line.startswith("+++")
                    or line.startswith("Index:") or line.startswith("===")):
                in_hunk = False
                continue
            if in_hunk:
                if line.startswith("-"):
                    lines.append(line[1:])
                elif line.startswith(" ") and include_context:
                    lines.append(line[1:])
        return "\n".join(lines)

    # Pass 1: only the '-' lines (pure test code, no stray comment fragments)
    minus_only = build_reconstruction(include_context=False)
    # Mask orphan block-comment fragment lines (e.g. " * Added testFoo()") that lack
    # their /** opener so remove_comments_and_strings cannot identify them as comments.
    def mask_orphan_comments(text):
        masked = []
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("* ") or stripped.startswith("*/") or stripped.startswith("/**"):
                masked.append("")        # blank out the line
            else:
                masked.append(line)
        return "\n".join(masked)

    minus_masked = mask_orphan_comments(minus_only)
    test_code = extract_method_body(minus_masked, test_method) if minus_masked.strip() else None
    # Use original (un-masked) text for extracting the final method body with Javadoc
    if test_code:
        test_code = extract_method_body(minus_only, test_method) or test_code

    # Pass 2: '-' + context lines (handles methods that span context sections)
    if not test_code:
        full_recon = build_reconstruction(include_context=True)
        test_code = extract_method_body(full_recon, test_method) if full_recon.strip() else None
        source_for_helpers = full_recon
    else:
        source_for_helpers = minus_only

    if not test_code:
        return None, {}

    # Extract helpers from the same source used to find the test
    clean = remove_comments_and_strings(source_for_helpers)
    defined_methods = set(re.findall(
        r"\b(?:public|protected|private|static|final|void|[\w<>\[\]]+)\s+(\w+)\s*\(", clean
    ))
    called = set(re.findall(r"\b(\w+)\s*\(", remove_comments_and_strings(test_code)))
    ignore = {
        test_method, "if", "for", "while", "switch", "catch", "new",
        "super", "this", "return", "throw", "assert", "assertEquals",
        "assertTrue", "assertFalse", "assertNull", "assertNotNull",
        "assertSame", "assertNotSame", "fail", "assertThat",
        "println", "print", "wait", "notify", "notifyAll",
        "equals", "hashCode", "toString", "get", "set", "size",
        "add", "put", "remove", "contains", "isEmpty",
    }
    helpers = {}
    for m in called - ignore:
        if m not in defined_methods:
            continue
        body = extract_method_body(source_for_helpers, m)
        if body:
            helpers[m] = body

    return test_code, helpers

def run_code_extraction(limit=None, force=False):
    rows = read_common_dataset()
    if not rows:
        print("No rows found in non_flaky_dataset.csv. Run Stage 1 first.")
        return

    processed = 0
    skipped_no_repo = set()

    for i, row in enumerate(rows):
        if limit is not None and processed >= limit:
            break

        # Skip if already filled and not forcing
        if row.get("test_code", "").strip() and not force:
            continue

        test_id = row.get("test_id", "")
        project = extract_project_from_test_id(test_id)
        buggy_commit  = row.get("flaky_commit", "").strip()   # production code buggy state
        fixed_commit  = row.get("fixed_commit", "").strip()   # test method lives HERE

        # Get bare repo
        repo_path = get_repo_path(project)
        if not repo_path:
            if project not in skipped_no_repo:
                print(f"  Skipping project {project}: bare repo not found in {REPOS_DIR}")
                skipped_no_repo.add(project)
            continue

        # Resolve test class and method from test_id
        test_class, test_method = resolve_test_class_method(test_id, PROJECTS_DIR)
        if not test_class or not test_method:
            print(f"  Warning: Could not resolve test class/method for {test_id}, skipping.")
            continue

        # KEY INSIGHT: The failing test method lives in the FIXED commit's test file.
        # Defects4J's test.patch REMOVES the test from the fixed file to create
        # the buggy testing state. So we must read from fixed_commit, not buggy_commit.
        test_src_dir = get_test_src_dir(project, fixed_commit)

        # Find the .java file in the git tree at the FIXED commit
        file_path = find_test_file_in_repo(repo_path, fixed_commit, test_class, test_src_dir)
        if not file_path:
            # Git lookup failed — try test.patch fallback (handles Chart/SVN revisions)
            parts = test_id.split("-")
            bug_id = parts[1]
            test_code, helpers = extract_from_test_patch(project, bug_id, test_method)
            if test_code:
                row["test_code"] = test_code
                row["helper_methods_json"] = helpers if helpers else {}
                processed += 1
                print(f"  ({processed}{f'/{limit}' if limit else ''}) {test_id} [patch]: "
                      f"{test_class}::{test_method} [{len(test_code)} chars, {len(helpers)} helpers]")
            else:
                print(f"  Warning: Could not find test file for {test_id} ({test_class}), skipping.")
            continue

        # Read file content from git at FIXED commit
        source_code = git_show_file(repo_path, fixed_commit, file_path)
        if not source_code:
            print(f"  Warning: Could not read file {file_path} at {fixed_commit[:8]} for {test_id}, skipping.")
            continue

        # Extract test method body
        test_code = extract_method_body(source_code, test_method)
        if not test_code:
            # Try patch fallback before giving up
            parts = test_id.split("-")
            bug_id = parts[1]
            test_code, helpers = extract_from_test_patch(project, bug_id, test_method)
            if test_code:
                row["test_code"] = test_code
                row["helper_methods_json"] = helpers if helpers else {}
                processed += 1
                print(f"  ({processed}{f'/{limit}' if limit else ''}) {test_id} [patch]: "
                      f"{test_class}::{test_method} [{len(test_code)} chars, {len(helpers)} helpers]")
            else:
                print(f"  Warning: Could not extract method '{test_method}' from {file_path} for {test_id}, skipping.")
            continue

        # Extract helper methods (also from fixed commit)
        helpers = extract_helper_methods(
            source_code, test_method, test_class,
            repo_path, fixed_commit, test_src_dir
        )

        # Update row
        row["test_code"] = test_code
        row["helper_methods_json"] = helpers if helpers else {}
        processed += 1

        print(f"  ({processed}{f'/{limit}' if limit else ''}) {test_id}: {test_class}::{test_method}"
              f" [{len(test_code)} chars, {len(helpers)} helpers]")

    write_common_dataset(rows, CODE_HEADERS)
    print()
    print(f"Stage 2 complete. Extracted code for {processed} records.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CANonFlake Stage 2: Test Code Extractor (from Defects4J bare git repos)",
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
    run_code_extraction(limit=limit_val, force=args.force)
