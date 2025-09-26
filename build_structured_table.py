import glob
import os
from analytics.structured_table import build_structured_table

# Path to all log.jsonl files inside each subfolder of logs/
log_files = glob.glob(os.path.join("logs", "*", "log.jsonl"))

for log_file in log_files:
    print(f"Processing {log_file}...")
    build_structured_table(log_file)
