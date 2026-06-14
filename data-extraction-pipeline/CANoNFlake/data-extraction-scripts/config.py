import os

# Root directory of the defects4j repository
D4J_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "dataSource", "defects4j"))

# Defects4J framework/projects directory — one folder per project
PROJECTS_DIR = os.path.join(D4J_ROOT, "framework", "projects")

# Bare git repositories extracted from defects4j-repos-v3.zip
# Structure: project_repos/commons-lang.git, commons-math.git, etc.
REPOS_DIR = os.path.join(D4J_ROOT, "project_repos")

# Path to the output shared CSV dataset
COMMON_CSV_PATH = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "non_flaky_dataset.csv"))

# Known GitHub repository URLs for all 17 Defects4J projects
GITHUB_URLS = {
    "Chart":          "https://github.com/jfree/jfreechart",
    "Cli":            "https://github.com/apache/commons-cli",
    "Closure":        "https://github.com/google/closure-compiler",
    "Codec":          "https://github.com/apache/commons-codec",
    "Collections":    "https://github.com/apache/commons-collections",
    "Compress":       "https://github.com/apache/commons-compress",
    "Csv":            "https://github.com/apache/commons-csv",
    "Gson":           "https://github.com/google/gson",
    "JacksonCore":    "https://github.com/FasterXML/jackson-core",
    "JacksonDatabind":"https://github.com/FasterXML/jackson-databind",
    "JacksonXml":     "https://github.com/FasterXML/jackson-dataformat-xml",
    "Jsoup":          "https://github.com/jhy/jsoup",
    "JxPath":         "https://github.com/apache/commons-jxpath",
    "Lang":           "https://github.com/apache/commons-lang",
    "Math":           "https://github.com/apache/commons-math",
    "Mockito":        "https://github.com/mockito/mockito",
    "Time":           "https://github.com/JodaOrg/joda-time",
}
