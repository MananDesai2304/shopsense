#!/usr/bin/env bash
# PostToolUse hook (spec 003, AC18 to AC21): run ruff format on a Python file
# Claude just edited or wrote, but only if its real path is inside the project.
# Exit 2 sends ruff's error back to Claude so it can fix the file.
set -uo pipefail

project_dir="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$project_dir" || { echo "format-python: cannot cd to $project_dir" >&2; exit 1; }

# Prints the file's real path if it is a .py file inside the project, else nothing.
# -I: stdlib only, and no module in the current directory can shadow json.
target=$(python3 -I -c '
import json, os, sys

try:
    path = json.load(sys.stdin).get("tool_input", {}).get("file_path") or ""
except (ValueError, AttributeError):
    sys.exit(1)
if path.endswith(".py"):
    real = os.path.realpath(path)
    root = os.path.realpath(sys.argv[1])
    if os.path.commonpath([root, real]) == root:
        print(real)
' "$project_dir") || { echo "format-python: could not read tool_input.file_path from hook JSON" >&2; exit 1; }

# Not Python, or outside the project: leave it alone.
[[ -z "$target" ]] && exit 0

if ! output=$(uv run ruff format "$target" 2>&1); then
  printf 'ruff format failed for %s:\n%s\n' "$target" "$output" >&2
  exit 2
fi
exit 0
