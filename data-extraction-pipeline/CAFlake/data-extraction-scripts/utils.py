import os
import csv
import sys

# Set higher CSV field size limit to support large stack trace logs
csv.field_size_limit(2147483647)

FLAKY_CATEGORY_FULL_NAMES = {
    "id": "Implementation Dependent",
    "od": "Order Dependent",
    "nio": "Non-Idempotent",
    "td": "Time Dependent"
}

def get_workspace_root():
    #Returns the absolute path to the workspace root.utils.py is located at CAFlake/data-extraction-scripts/utils.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(script_dir, "..", ".."))

import json

def get_common_jsonl_path():
    #Returns the absolute path where the shared JSONL dataset file is stored.
    workspace = get_workspace_root()
    return os.path.join(workspace, "CAFlake", "context_enriched_dataset.jsonl")

def read_common_dataset():
    #Reads the shared JSONL dataset, returning a list of dicts.If the file does not exist, returns an empty list.
    jsonl_path = get_common_jsonl_path()
    if not os.path.exists(jsonl_path):
        return []
    
    rows = []
    with open(jsonl_path, mode='r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows

def write_common_dataset(rows, headers=None):
    #Writes the list of dicts back to the shared JSONL dataset using the specified headers to order keys.
    jsonl_path = get_common_jsonl_path()
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    
    with open(jsonl_path, mode='w', encoding='utf-8') as f:
        for row in rows:
            if headers:
                ordered_row = {col: row.get(col, "") for col in headers}
            else:
                ordered_row = row
            f.write(json.dumps(ordered_row, ensure_ascii=False) + '\n')
    print(f"Updated common dataset JSONL at: {jsonl_path}")

def load_git_metadata():
    #Loads Git commit SHAs and repository URLs from JIRA and iDoFT mapping tables.
    workspace = get_workspace_root()
    jira_path = os.path.join(workspace, "research-data", "Reproducible_JIRA_info.csv")
    idoft_path = os.path.join(workspace, "research-data", "Reproducible_iDoFT_info.csv")
    
    git_metadata = {}
    for path in (jira_path, idoft_path):
        if not os.path.exists(path):
            continue
        with open(path, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                zip_name = row.get("Zip name", "").strip()
                container_name = row.get("Container Name", "").strip()
                repo_url = row.get("Project (Github Link)", "").strip()
                flaky_sha = row.get("Flaky commit SHA", "").strip()
                fixed_sha = row.get("Fixed commit SHA", "").strip()
                
                meta = {"repo_url": repo_url, "flaky_commit": flaky_sha, "fixed_commit": fixed_sha}
                if zip_name:
                    git_metadata[zip_name] = meta
                if container_name:
                    git_metadata[container_name] = meta
    return git_metadata
