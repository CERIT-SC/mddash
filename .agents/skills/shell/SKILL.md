---
name: shell
description: ALWAYS use this skill when creating, modifying, or debugging sh, Bash, Zsh, POSIX shell, setup, run, CI, or automation scripts.
---

# Shell Standards

## Shell Choice

- Use POSIX `sh` for portable automation scripts.
- Use Bash or Zsh only when the script needs shell-specific features.
- Match the shebang to the features used by the script.
- Use `set -eu` for portable scripts and add `pipefail` in shells that support it.

## Variables And Inputs

- Quote variable expansions and command substitutions by default.
- Use `printf` for portable formatted output.
- Validate required arguments and environment variables before side effects.
- Use explicit allowlists for user-controlled modes, commands, paths, and environments.
- Use `command -v` for command detection.
- Use arrays only in scripts that declare a shell with array support.

## Safety

- Keep secrets in environment variables, secret stores, or mounted secret files.
- Guard destructive operations with non-empty path checks and allowlisted directories.
- Use temporary directories created by `mktemp -d` for intermediate files.
- Register cleanup traps for temporary files, mounts, locks, and background processes.
- Use explicit command arguments for dynamic behavior.

## Portability And Maintainability

- Keep setup, CI, and deployment scripts idempotent.
- Use globs directly for file iteration and handle empty matches deliberately.
- Keep complex logic in small functions or move it to a real programming language.
- Keep scripts independent of the caller's current working directory when they operate on repository files.

## Verification

- Run `shellcheck` on changed scripts when available.
- Test scripts from a clean environment when they depend on exported variables, PATH, current directory, or platform tools.
