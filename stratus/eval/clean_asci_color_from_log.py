import re
import sys

# Path to your log file
log_file_path = sys.argv[1]

# Read the content of the log file
with open(log_file_path, "r") as file:
    log_content = file.read()

# Remove all ANSI escape sequences
cleaned_log_content = re.sub(r"\x1b\[[0-9;]*m", "", log_content)
log_file_path = log_file_path.removesuffix(".log")
# Save the cleaned log content back to the file or to a new file
with open(log_file_path + "-cleaned.log", "w") as file:
    file.write(cleaned_log_content)

print("ANSI color codes have been removed. Saved to cleaned .log.")
