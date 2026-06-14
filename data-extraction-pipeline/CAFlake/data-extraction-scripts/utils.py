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

def get_common_csv_path():
    #Returns the absolute path where the shared CSV dataset file is stored.
    workspace = get_workspace_root()
    return os.path.join(workspace, "CAFlake", "context_enriched_dataset.csv")

def read_common_dataset():
    #Reads the shared CSV dataset, returning a list of dicts.If the file does not exist, returns an empty list.
    csv_path = get_common_csv_path()
    if not os.path.exists(csv_path):
        return []
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def write_common_dataset(rows, headers):
    #Writes the list of dicts back to the shared CSV dataset using the specified headers.
    csv_path = get_common_csv_path()
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    
    with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Updated common dataset CSV at: {csv_path}")

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
