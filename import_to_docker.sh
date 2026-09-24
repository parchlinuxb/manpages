#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$DIR/docker-compose.yml"
TRANSLATIONS_DIR="$DIR/translations/fa"
CACHE_FILE="$DIR/.cache/imported_hashes.json"

mkdir -p "$DIR/.cache"

# Collect candidate files and filter using SHA256 hashes
OUTPUT=$(python3 -u - "$CACHE_FILE" "$TRANSLATIONS_DIR" "$@" << 'PY_COLLECT'
import sys, os, glob, re, hashlib, json

cache_file = sys.argv[1]
translations_dir = sys.argv[2]
args = sys.argv[3:]

force_all = False
specific_files = []

if "--all" in args or "--force" in args:
    force_all = True
    args = [a for a in args if a not in ("--all", "--force")]

# Check if arguments specify command and section (e.g., "tar 5" or "ls 1")
if len(args) == 2 and args[1].isdigit() and not args[0].endswith(".fa"):
    cmd_arg, sec_arg = args[0], args[1]
    candidate = os.path.join(translations_dir, f"man{sec_arg}", f"{cmd_arg}.{sec_arg}.fa")
    if os.path.exists(candidate):
        specific_files.append(candidate)
    else:
        print(f"File not found: {candidate}", file=sys.stderr)
        sys.exit(1)
elif len(args) > 0:
    for a in args:
        if os.path.isfile(a):
            specific_files.append(os.path.abspath(a))
        else:
            candidate = os.path.join(translations_dir, a)
            if os.path.isfile(candidate):
                specific_files.append(candidate)
            else:
                print(f"Warning: File not found: {a}", file=sys.stderr)

pattern = re.compile(r'^(.+)\.([1-9][a-zA-Z0-9_]*)\.fa$')

if specific_files:
    target_files = sorted(specific_files)
    use_cache = False
else:
    target_files = sorted(glob.glob(os.path.join(translations_dir, "*", "*.*.fa")))
    use_cache = not force_all

cache = {}
if os.path.exists(cache_file):
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}

files_to_send = []

for p in target_files:
    fn = os.path.basename(p)
    m = pattern.match(fn)
    if not m:
        continue
    try:
        with open(p, "rb") as f:
            data = f.read()
    except Exception:
        continue
    
    file_hash = hashlib.sha256(data).hexdigest()
    rel_path = os.path.relpath(p, translations_dir)
    
    if use_cache and cache.get(rel_path) == file_hash:
        continue
    
    files_to_send.append((m.group(1), m.group(2), data.decode("utf-8", errors="replace"), rel_path, file_hash))

if not files_to_send:
    print("===NO_CHANGES===")
    sys.exit(0)

# Output stream for docker
for name, sec, content, rel_path, file_hash in files_to_send:
    print("===PAGE_DELIMITER===")
    print(name)
    print(sec)
    print(rel_path)
    print(file_hash)
    print(content)
PY_COLLECT
)

if [ "$OUTPUT" = "===NO_CHANGES===" ]; then
    echo "⚡ تمامی صفحات قبلاً ایندکس شده‌اند و هیچ تغییر جدیدی یافت نشد."
    exit 0
fi

# Pipe changes to docker and receive successful hashes back
echo "$OUTPUT" | docker compose -f "$COMPOSE_FILE" exec -T web python -u -c "
import os, sys, re
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'local_settings')
import django
django.setup()
from django.utils import timezone
from archmanweb.models import Content, ManPage, Package
from archmanweb.utils import extract_description, mandoc_convert, postprocess, preprocess

repo = 'core'
imported = 0
skipped = 0

for block in sys.stdin.read().split('===PAGE_DELIMITER==='):
    block = block.strip()
    if not block:
        continue
    lines = block.split('\n', 4)
    if len(lines) < 5:
        continue
    name = lines[0].strip()
    section = lines[1].strip()
    rel_path = lines[2].strip()
    file_hash = lines[3].strip()
    raw = lines[4]

    man = ManPage.objects.filter(name=name, section=section, lang='fa').first()
    if man and man.content and man.content.raw == raw:
        skipped += 1
        print(f'===SUCCESS_HASH==={rel_path}==={file_hash}')
        continue

    existing_man = ManPage.objects.filter(name=name, section=section, lang='en').first()
    if existing_man:
        pkg = existing_man.package
    else:
        pkg = Package.objects.filter(name=name).first()
        if not pkg:
            pkg, _ = Package.objects.get_or_create(
                repo=repo,
                name='parch-translations',
                defaults={
                    'version': '1.0',
                    'arch': 'any',
                    'description': 'Parch Linux Translations',
                    'build_date': timezone.now(),
                    'licenses': ['GPL'],
                },
            )

    raw_pre_txt = preprocess(raw, 'txt')
    txt = postprocess(mandoc_convert(raw_pre_txt, 'txt', lang='fa'), 'txt', lang='fa')
    raw_pre_html = preprocess(raw, 'html')
    html = postprocess(mandoc_convert(raw_pre_html, 'html', lang='fa'), 'html', lang='fa')
    desc = extract_description(txt, lang='fa')

    content = man.content if man else Content()
    content.raw = raw
    content.txt = txt
    content.html = html
    content.description = desc
    content.save()

    if not man:
        man = ManPage(package=pkg, name=name, section=section, lang='fa', content=content)
        man.save()

    imported += 1
    print(f'Imported: {name}({section})')
    print(f'===SUCCESS_HASH==={rel_path}==={file_hash}')

print(f'DONE: {imported} imported, {skipped} already up-to-date.')
" | python3 -u -c "
import sys, json, os

cache_file = '$CACHE_FILE'
cache = {}
if os.path.exists(cache_file):
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except Exception:
        cache = {}

updated = False
for line in sys.stdin:
    line = line.rstrip('\r\n')
    if line.startswith('===SUCCESS_HASH==='):
        parts = line.split('===')
        if len(parts) >= 4:
            rel_p = parts[2]
            f_hash = parts[3]
            cache[rel_p] = f_hash
            updated = True
    else:
        print(line)

if updated:
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
        os.system(f'chmod g+rw \"{cache_file}\" 2>/dev/null || true')
        os.system(f'chgrp translators \"{cache_file}\" 2>/dev/null || true')
    except Exception:
        pass
"

# Clear Nginx cache if running with docker socket access
if [ -S /var/run/docker.sock ]; then
    docker run --rm -v /var/cache/nginx/man:/cache alpine sh -c "rm -rf /cache/*" 2>/dev/null || true
fi

