import os

# Root directory of the repository
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "dataSource", "reproFlake"))

# Directory containing the original project ZIPs
DATA_DIR = os.path.join(WORKSPACE_ROOT, "data")

# Directory containing ReproFlake execution results
RESULT_DIR = os.path.join(WORKSPACE_ROOT, "result")

# Path to the main test configuration CSV
TEST_CONFIG_PATH = os.path.join(WORKSPACE_ROOT, "test_config.csv")

# Path to the output common dataset CSV
COMMON_CSV_PATH = os.path.join(WORKSPACE_ROOT, "CAFlake", "context_enriched_dataset.csv")

# Paths to reproduction mapping tables
JIRA_INFO_PATH = os.path.join(WORKSPACE_ROOT, "research-data", "Reproducible_JIRA_info.csv")
IDOFT_INFO_PATH = os.path.join(WORKSPACE_ROOT, "research-data", "Reproducible_iDoFT_info.csv")
