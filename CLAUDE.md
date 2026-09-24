# Parch Linux Man Pages Translation Project

Persistent instructions and workflow protocols for Parch Linux man pages Persian translation repository.

## Project Overview
- Translation and indexing of Linux manual pages (`man`) into Persian (`fa`).
- Storage paths: `translations/fa/man1/`, `translations/fa/man5/`, `translations/fa/man8/`.
- Coordination registry: `progress.csv` (17,542 pages tracked via `task.py`).
- Web Portal: `https://man.vilix.org` (Django + Docker backend).

## Common Commands
```bash
# Check overall translation statistics:
./task.py stats

# List incomplete tasks for a specific user:
./task.py list --user ahoura --status incomplete --limit 20

# Claim next N highest-priority tasks for a user:
./task.py next --user ahoura --count 4 --claim

# Complete task (dual verification + docker import + update progress.csv):
./task.py finish --cmd <command> --section <section>

# Manual Dual Verification Gate:
mandoc -Tutf8 translations/fa/man<section>/<command>.<section>.fa > /dev/null
mandoc -Thtml -Ofragment translations/fa/man<section>/<command>.<section>.fa > /dev/null

# Extract English source from Docker (by exact command name, NEVER sweep with ls):
python3 extract_en.py <command> <section>
```

## Core Workflows & Rules
1. **Task Lifecycle (`progress.csv`):**
   - Valid statuses: `free` -> `in_progress` -> `completed`.
   - Priorities: `1` (Core/Critical packages), `2` (Services/Config files), `3` (Extra).
   - Before translation: verify status is `free` and claim to `in_progress`.
   - After translation: run `./task.py finish --cmd <cmd> --section <sec>` which verifies and marks `completed`.

2. **Subagent Patience Rule (CRITICAL):**
   - NEVER kill, interrupt, or cancel subagents while they are translating, verifying, or importing.
   - Rely strictly on reactive task completion notifications.

3. **Web Portal Links:**
   - Always report web links using the official domain: `https://man.vilix.org/man/<command>.<section>.fa`.
   - NEVER use `localhost` or `127.0.0.1`.

## Translation & Roff Formatting Guidelines
- **Markup Preservation:**
  - Preserve all Roff/Groff macros: `.TH`, `.SH`, `.SS`, `.PP`, `.TP`, `.IP`, `.B`, `.I`, `.BR`, `.IR`, `.nf`, `.fi`, `.EX`, `.EE`.
  - Translate text descriptions only. Keep command names, flags, options, environment variables, and macro names intact.
  - Escape hyphens in command options and flags with `\-` (e.g., `\-\-all`, `\-v`).
- **Standard Persian Section Titles:**
  - `.SH "نام (NAME)"`
  - `.SH "خلاصه دستور (SYNOPSIS)"`
  - `.SH "توضیحات (DESCRIPTION)"`
  - `.SH "گزینه‌ها (OPTIONS)"`
  - `.SH "مثال‌ها (EXAMPLES)"`
  - `.SH "فایل‌ها (FILES)"`
  - `.SH "همچنین ببینید (SEE ALSO)"`
  - `.SH "نویسندگان (AUTHORS)"` یا `.SH "نویسنده (AUTHOR)"`
  - `.SH "تاریخچه (HISTORY)"`
- **ASCII Diagrams & Boxes:**
  - Keep all character-based diagrams LTR and monospace.
  - Always wrap ASCII art/flowcharts in `.nf` / `.fi` or `.EX` / `.EE`.
- **URLs in RTL Text:**
  - Strip trailing slashes from URLs (e.g. `<https://www.gnu.org>` instead of `<https://www.gnu.org/>`) to prevent BiDi punctuation reversal.

## Terminology Standard
| English Term | Approved Persian Translation | Forbidden/Avoid |
| :--- | :--- | :--- |
| Directory | دایرکتوری / پوشه | دیرکتوری |
| Option / Flag | گزینه / فلگ / سوییچ | آپشن |
| Argument | آرگومان / شناسه | - |
| Output / Input | خروجی / ورودی | اوت‌پوت / این‌پوت |
| Default | پیش‌فرض | دیفالت |
| Execute / Run | اجرا کردن | ران کردن |
| Permission | دسترسی / مجوز | پرمیشن |
| Root / Superuser | ریشه / مدیر سیستم (کاربر ارشد) | - |
| Package / Repository | بسته / مخزن | ریپازیتوری |

## Team Role Division
- `debian`: Parch core packages, package managers (`pacman`, `pacman.conf`), system tools.
- `ahoura`: File and directory commands (`ls`, `cp`, `mv`, `rm`, etc.).
- `parviz`: Text filters, permissions, process management (`grep`, `chmod`, `find`, `kill`, etc.).
- `sasiohae`: Network tools, developer utilities, and monitoring.
- `jobin`: Container tools, virtualization, and CLI utilities.

## Dual Verification Gate
Before finalizing any man page, the dual verification gate is MANDATORY:
1. `mandoc -Tutf8 translations/fa/man<section>/<command>.<section>.fa > /dev/null`
2. `mandoc -Thtml -Ofragment translations/fa/man<section>/<command>.<section>.fa > /dev/null`
Any parser warning/error must be resolved before calling `./task.py finish`.

## Large Pages Chunking Protocol (>30 KB or >1000 lines)
For large man pages:
1. **Split by Macro Boundaries:** Split strictly on `.SH`, `.SS`, or `.TP`/`.IP` blocks into `.cache/parts/<command>/part_XX.roff`.
2. **Parallel Subagents:** Fan out one subagent per chunk simultaneously.
3. **Deterministic Assembly:** Concatenate translated parts in order:
   `cat .cache/parts/<command>/part_*.fa.roff > translations/fa/man<section>/<command>.<section>.fa`
4. **Whole-File Verification:** Run the Dual Verification Gate on the assembled file before finishing.

## Critical Invariants & Forbidden Actions
- **NEVER** run `ls` or sweep the whole `.cache/en_sources/` directory. Access files strictly by exact path/command name.
- **NEVER** delete `GEMINI.md` — both files coexist for multi-agent compatibility.
- Ensure file permissions remain group-writable (`translators` group).
