#!/usr/bin/env python3
import os
import sys
import csv
import json
import subprocess
import re
import grp
import time
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROGRESS_CSV = os.path.join(BASE_DIR, "progress.csv")
BATCH_SIZE = 80

HEADINGS_MAP = {
    'NAME': 'نام (NAME)',
    'SYNOPSIS': 'خلاصه دستور (SYNOPSIS)',
    'DESCRIPTION': 'توضیحات (DESCRIPTION)',
    'OPTIONS': 'گزینه‌ها (OPTIONS)',
    'EXAMPLES': 'مثال‌ها (EXAMPLES)',
    'EXAMPLE': 'مثال (EXAMPLE)',
    'FILES': 'فایل‌ها (FILES)',
    'SEE ALSO': 'همچنین ببینید (SEE ALSO)',
    'AUTHORS': 'نویسندگان (AUTHORS)',
    'AUTHOR': 'نویسنده (AUTHOR)',
    'AUTHOR(S)': 'نویسندگان (AUTHORS)',
    'ORIGINAL AUTHORS': 'نویسندگان اصلی (ORIGINAL AUTHORS)',
    'BUGS': 'اشکالات (BUGS)',
    'REPORTING BUGS': 'گزارش باگ‌ها (REPORTING BUGS)',
    'COPYRIGHT': 'حق نشر (COPYRIGHT)',
    'COPYING': 'کپی‌رایت و تکثیر (COPYING)',
    'LICENSE': 'مجوز (LICENSE)',
    'ENVIRONMENT': 'محیط (ENVIRONMENT)',
    'EXIT STATUS': 'وضعیت خروج (EXIT STATUS)',
    'NOTES': 'نکات (NOTES)',
    'NOTE': 'نکته (NOTE)',
    'HISTORY': 'تاریخچه (HISTORY)',
    'VERSION': 'نسخه (VERSION)',
    'VERSIONS': 'نسخه‌ها (VERSIONS)',
    'DIAGNOSTICS': 'عیب‌یابی (DIAGNOSTICS)',
    'CAVEATS': 'هشدارها (CAVEATS)',
    'WARNINGS': 'هشدارها (WARNINGS)',
    'STANDARDS': 'استانداردها (STANDARDS)',
    'CONFORMING TO': 'سازگاری با استانداردها (CONFORMING TO)',
    'CONFIGURATION': 'پیکربندی (CONFIGURATION)',
    'CONFIGURATION FILES': 'فایل‌های پیکربندی (CONFIGURATION FILES)',
    'FILE FORMAT': 'قالب فایل (FILE FORMAT)',
    'FILES AND DIRECTORIES': 'فایل‌ها و پوشه‌ها (FILES AND DIRECTORIES)',
    'USAGE': 'نحوه استفاده (USAGE)',
    'SYNTAX': 'سینتکس (SYNTAX)',
    'OVERVIEW': 'نمای کلی (OVERVIEW)',
}

def clean_heading(h):
    h = h.strip()
    if (h.startswith('"') and h.endswith('"')) or (h.startswith("'") and h.endswith("'")):
        h = h[1:-1].strip()
    # remove roff font escapes like \fB, \fR, \fI, \fP, \f(CW, \f[CR], \&
    h = re.sub(r'\\f\[[^\]]+\]', '', h)
    h = re.sub(r'\\f\([A-Za-z0-9]{2}', '', h)
    h = re.sub(r'\\f[A-Za-z0-9]', '', h)
    h = re.sub(r'\\&', '', h)
    h = re.sub(r'\\-', '-', h)
    h = h.strip()
    if (h.startswith('"') and h.endswith('"')) or (h.startswith("'") and h.endswith("'")):
        h = h[1:-1].strip()
    return h.upper()

def transform_manpage(content):
    if content.startswith(".so "):
        return content

    lines = content.splitlines(keepends=True)
    out_lines = []
    in_name = False
    name_fixed = False

    for line in lines:
        m = re.match(r'^(\.(?:SH|Sh))\s+(.*)$', line)
        if m:
            macro = m.group(1)
            raw_h = m.group(2).strip()
            # If already has Persian characters, leave untouched
            if re.search(r'[\u0600-\u06FF]', raw_h):
                out_lines.append(line)
                in_name = False
                continue

            norm = clean_heading(raw_h)
            if norm in HEADINGS_MAP:
                out_lines.append(f'{macro} "{HEADINGS_MAP[norm]}"\n')
                if norm == 'NAME':
                    in_name = True
                    name_fixed = False
                else:
                    in_name = False
                continue
            else:
                in_name = False
        elif in_name and not name_fixed:
            stripped = line.strip()
            if stripped and not stripped.startswith('.'):
                fixed = re.sub(r'(?<=\S)\s+-\s+(?=\S)', r' \\- ', line, count=1)
                out_lines.append(fixed)
                name_fixed = True
                continue

        out_lines.append(line)

    res = ''.join(out_lines)
    # Rule 5: URLs without trailing slash
    res = re.sub(r'(https?://[^\s>"\']+)/([>"\'])', r'\1\2', res)
    return res

DOCKER_DJANGO_SCRIPT = """
import django, os, sys, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "local_settings")
django.setup()
from archmanweb.models import ManPage

pairs = json.loads(sys.stdin.read())
results = {}
for cmd, sec in pairs:
    m = ManPage.objects.filter(name=cmd, section=sec, lang="en").select_related("content").first()
    if not m:
        m = ManPage.objects.filter(name__iexact=cmd, section=sec, lang="en").select_related("content").first()
    if m and m.content:
        results[f"{cmd}.{sec}"] = m.content.raw
    else:
        results[f"{cmd}.{sec}"] = None
print(json.dumps(results))
"""

def extract_batch_from_docker(batch):
    p = subprocess.run(
        ["docker", "compose", "exec", "-T", "web", "python", "-c", DOCKER_DJANGO_SCRIPT],
        input=json.dumps(batch),
        text=True,
        capture_output=True
    )
    if p.returncode != 0:
        print(f"Error in docker exec: {p.stderr}", file=sys.stderr)
        return {}
    try:
        return json.loads(p.stdout)
    except Exception as e:
        print(f"Error parsing JSON output: {e}\nRaw output: {p.stdout[:300]}", file=sys.stderr)
        return {}

def main():
    try:
        translators_gid = grp.getgrnam("translators").gr_gid
    except KeyError:
        translators_gid = -1

    # Step 1: Collect free tasks
    print("Step 1: Reading progress.csv to find free tasks for sections 1, 5, 8...")
    free_tasks = []
    with open(PROGRESS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            sec = r["section"]
            cmd = r["command"]
            st = r["status"]
            if sec in ["1", "5", "8", "1ssl", "5ssl"] and st in ["free", "in_progress"]:
                target_path = os.path.join(BASE_DIR, "translations", "fa", f"man{sec}", f"{cmd}.{sec}.fa")
                if not os.path.exists(target_path):
                    free_tasks.append((cmd, sec, target_path))

    print(f"Total free tasks needing scaffold: {len(free_tasks)}")
    by_sec = {}
    for cmd, sec, path in free_tasks:
        by_sec[sec] = by_sec.get(sec, 0) + 1
    print(f"Breakdown by section: {by_sec}")

    if not free_tasks:
        print("No free tasks need scaffolding. Exiting.")
        return

    # Step 2 & 3: Batch extraction and scaffold generation
    print(f"\nStep 2 & 3: Extracting and scaffolding in batches of {BATCH_SIZE}...")
    created_count = 0
    missing_count = 0
    created_by_sec = {"1": 0, "5": 0, "8": 0}
    missing_items = []
    created_files = []

    total_batches = (len(free_tasks) + BATCH_SIZE - 1) // BATCH_SIZE
    t_start = time.time()

    for b_idx in range(total_batches):
        batch_slice = free_tasks[b_idx * BATCH_SIZE : (b_idx + 1) * BATCH_SIZE]
        batch_pairs = [(cmd, sec) for cmd, sec, _ in batch_slice]
        b_t0 = time.time()

        data = extract_batch_from_docker(batch_pairs)
        b_t1 = time.time()

        for cmd, sec, target_path in batch_slice:
            key = f"{cmd}.{sec}"
            raw = data.get(key)
            if not raw:
                missing_count += 1
                missing_items.append(key)
                continue

            scaffold_content = transform_manpage(raw)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f_out:
                f_out.write(scaffold_content)

            # Step 4: Permissions (chmod 664, chgrp translators)
            try:
                os.chmod(target_path, 0o664)
                if translators_gid != -1:
                    os.chown(target_path, -1, translators_gid)
            except Exception as e:
                pass

            created_count += 1
            created_by_sec[sec] = created_by_sec.get(sec, 0) + 1
            created_files.append(target_path)

        print(f"Batch {b_idx + 1}/{total_batches} ({len(batch_slice)} items) done in {round(b_t1 - b_t0, 2)}s | Total created: {created_count} | Missing: {missing_count}")

    t_total = time.time() - t_start
    print(f"\nExtraction & Scaffolding complete in {round(t_total, 2)}s.")
    print(f"Created scaffolds: {created_count}")
    print(f"Created by section: {created_by_sec}")
    print(f"Missing in docker DB: {missing_count}")
    if missing_items:
        print(f"Sample missing: {missing_items[:10]}")

    # Step 5: Dual Verification Gate on sample of created files
    print("\nStep 5: Running Dual Verification Gate on created files...")
    sample_size = min(len(created_files), 150)
    sample_files = random.sample(created_files, sample_size) if created_files else []
    
    verified_ok = 0
    verification_errors = []

    for fpath in sample_files:
        p1 = subprocess.run(["mandoc", "-Tutf8", fpath], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        p2 = subprocess.run(["mandoc", "-Thtml", "-Ofragment", fpath], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

        if p1.returncode == 0 and p2.returncode == 0:
            verified_ok += 1
        else:
            err = f"{os.path.basename(fpath)}: utf8_rc={p1.returncode}, html_rc={p2.returncode}"
            if p2.stderr:
                err += f" (html stderr: {p2.stderr.strip()[:100]})"
            verification_errors.append(err)

    print(f"Sample verification completed: {verified_ok}/{sample_size} passed (100% pass: {verified_ok == sample_size})")
    if verification_errors:
        print(f"Verification errors ({len(verification_errors)}):")
        for err in verification_errors[:10]:
            print(f"  - {err}")

    # Also verify permissions on sample
    perm_ok = True
    for fpath in sample_files[:30]:
        st = os.stat(fpath)
        mode = oct(st.st_mode & 0o777)
        gid = st.st_gid
        if mode != "0o664" or (translators_gid != -1 and gid != translators_gid):
            perm_ok = False
            print(f"Permission mismatch on {fpath}: mode={mode}, gid={gid} (expected 0o664, {translators_gid})")
            break
    if perm_ok:
        print(f"Permissions verified on sample files: mode 664, group translators ({translators_gid})")

if __name__ == "__main__":
    main()
