---
applyTo: '**/*.sh'
---

# Shell Scripting Rules for AI Agents

## Mandatory Header
ALWAYS include:
```bash
#!/bin/bash
set -euo pipefail  # Exit on error, unset vars, pipeline failures
```

## Core Rules

### Variables
- **ALWAYS quote variables**: `"$var"` not `$var`
- Use arrays for lists: `files=("f1" "f2")` then `"${files[@]}"`
- Naming: `lowercase_with_underscores`, `CONSTANTS_UPPERCASE`
- Mark constants: `readonly MAX_RETRIES=3`

### Functions
```bash
function_name() {
    local arg1="$1"
    local arg2="${2:-default}"  # With default
    # Function body
    return 0  # Explicit return
}
```

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

# Exit codes: 0=success, 1=general error, 2=invalid args, 3+=custom
```

### Input Validation
ALWAYS validate:
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

### Security
```bash
# NEVER hardcode credentials
PASSWORD="${PASSWORD:?Error: PASSWORD not set}"  # Require env var

# NEVER use eval with user input
# BAD: eval "rm $user_input"
# GOOD: Use arrays and proper quoting

# Validate before dangerous operations
[[ -z "$DIR" || "$DIR" == "/" ]] && { echo "Error: Invalid DIR" >&2; exit 1; }
rm -rf "${DIR:?}/"*
```

### Commands & Patterns
```bash
# Use [[ ]] not [ ]
[[ "$var" == "value" ]] && echo "Match"

# Modern command substitution
result=$(command args)  # NOT: result=`command args`

# Parameter expansion (prefer over external commands)
filename="${path##*/}"     # basename
dirname="${path%/*}"       # dirname
extension="${filename##*.}"

# Read files
content=$(<file.txt)       # NOT: content=$(cat file.txt)

# Loop over files
for file in *.txt; do      # NOT: for file in $(ls *.txt)
    [[ -f "$file" ]] && process "$file"
done

# Case statements for multi-condition
case "$var" in
    opt1) action1 ;;
    opt2) action2 ;;
    *) echo "Unknown" >&2; exit 1 ;;
esac
```

### Output
```bash
# Errors to stderr
echo "Error message" >&2

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Suppress output
command &> /dev/null
```

### Dependencies
```bash
check_dependencies() {
    local missing=()
    for cmd in "$@"; do
        command -v "$cmd" &> /dev/null || missing+=("$cmd")
    done
    [[ ${#missing[@]} -gt 0 ]] && {
        echo "Error: Missing: ${missing[*]}" >&2
        exit 1
    }
}
```

## Complete Script Template
```bash
#!/bin/bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly LOG_FILE="${LOG_FILE:-/var/log/script.log}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
cleanup() { log "Cleanup"; rm -rf "$TEMP_DIR"; }

main() {
    # Validate arguments
    [[ $# -lt 1 ]] && { echo "Usage: $0 <arg>" >&2; exit 2; }
    
    local arg="$1"
    trap cleanup EXIT SIGINT SIGTERM
    
    # Script logic
    log "Processing $arg"
}

main "$@"
```

## ShellCheck Integration
RUN before committing:
```bash
shellcheck script.sh
shellcheck -x script.sh  # Follow sourced files
```

Common fixes:
- Quote all variables
- Use `[[ ]]` not `[ ]`
- Use `$()` not backticks
- Use `command -v` to check commands
- Use arrays for lists

## Quick Reference
| Pattern | Good | Bad |
|---------|------|-----|
| Quote vars | `"$var"` | `$var` |
| Test | `[[ ]]` | `[ ]` |
| Substitution | `$(cmd)` | `` `cmd` `` |
| Read file | `$(<file)` | `$(cat file)` |
| Loop files | `for f in *.txt` | `for f in $(ls)` |
| Check cmd | `command -v` | `which` |
