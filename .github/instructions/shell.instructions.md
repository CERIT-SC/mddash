---
applyTo: '**/*.sh'
---

# Shell Scripting Guidelines

Robust, portable Bash scripts.

<context>
Essential patterns for writing safe, maintainable shell scripts. Focus on error handling, input validation, and security.
</context>

<best_practices>

<header>
### Mandatory Header
```bash
#!/bin/bash
set -euo pipefail  # Exit on error, unset vars, pipeline failures
```
</header>

<variables>
### Variables
- **Always quote:** `"$var"` not `$var`
- **Arrays for lists:** `files=("f1" "f2")` then `"${files[@]}"`
- **Naming:** `lowercase_with_underscores`, `CONSTANTS_UPPERCASE`
- **Constants:** `readonly MAX_RETRIES=3`
</variables>

<functions>
### Functions
```bash
function_name() {
    local arg1="$1"
    local arg2="${2:-default}"
    # Function body
    return 0
}
```
</functions>

<error_handling>
### Error Handling
```bash
# Check commands
if ! mkdir -p "$dir"; then
    echo "Error message" >&2
    exit 1
fi

# Or use ||
command || { echo "Error" >&2; exit 1; }

# Cleanup trap
trap 'rm -rf "$TEMP_DIR"' EXIT SIGINT SIGTERM
```
</error_handling>

<validation>
### Input Validation
```bash
# Check argument count
[[ $# -lt 2 ]] && { echo "Usage: $0 <arg1> <arg2>" >&2; exit 2; }

# Validate non-empty
[[ -z "$var" ]] && { echo "Error: var is empty" >&2; exit 1; }

# Validate pattern
[[ ! "$input" =~ ^[0-9]+$ ]] && { echo "Error: Must be number" >&2; exit 1; }

# Check file access
[[ ! -r "$file" ]] && { echo "Error: Cannot read $file" >&2; exit 1; }
```
</validation>

<security>
### Security
```bash
# Require env vars
PASSWORD="${PASSWORD:?Error: PASSWORD not set}"

# Validate before dangerous operations
[[ -z "$DIR" || "$DIR" == "/" ]] && { echo "Error: Invalid DIR" >&2; exit 1; }
rm -rf "${DIR:?}/"*
```
</security>

<patterns>
### Modern Patterns
```bash
# Use [[ ]] not [ ]
[[ "$var" == "value" ]] && echo "Match"

# Modern command substitution
result=$(command args)  # NOT: result=`command args`

# Parameter expansion
filename="${path##*/}"     # basename
dirname="${path%/*}"       # dirname

# Read files
content=$(<file.txt)       # NOT: $(cat file.txt)

# Loop over files
for file in *.txt; do      # NOT: for file in $(ls *.txt)
    [[ -f "$file" ]] && process "$file"
done
```
</patterns>

<template>
### Template
```bash
#!/bin/bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly LOG_FILE="${LOG_FILE:-/var/log/script.log}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
cleanup() { log "Cleanup"; rm -rf "$TEMP_DIR"; }

main() {
    [[ $# -lt 1 ]] && { echo "Usage: $0 <arg>" >&2; exit 2; }
    
    local arg="$1"
    trap cleanup EXIT SIGINT SIGTERM
    
    log "Processing $arg"
}

main "$@"
```
</template>

<anti_patterns>
### Quick Reference
| Good | Bad |
|------|-----|
| `"$var"` | `$var` |
| `[[ ]]` | `[ ]` |
| `$(cmd)` | `` `cmd` `` |
| `$(<file)` | `$(cat file)` |
| `for f in *.txt` | `for f in $(ls)` |
| `command -v` | `which` |
</anti_patterns>

</best_practices>

<boundaries>
- ✅ **Always:** Include `set -euo pipefail`
- ✅ **Always:** Quote all variables (`"$var"`)
- ✅ **Always:** Validate inputs and arguments
- ✅ **Always:** Use `[[ ]]` for tests
- ✅ **Always:** Use `$(cmd)` for substitution
- ✅ **Always:** Add cleanup traps
- ✅ **Always:** Run `shellcheck` before committing
- 🚫 **Never:** Hardcode credentials
- 🚫 **Never:** Use `eval` with user input
- 🚫 **Never:** Use `[ ]` or backticks
</boundaries>
