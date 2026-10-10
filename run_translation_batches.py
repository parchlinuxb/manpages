#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Batch Translation Runner for Parch Man Pages
Executes batches of 7 tasks following all rules in GEMINI.md
"""

import os
import sys
import json
import re
import time
import subprocess
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GATEWAY_URL = "http://127.0.0.1:20128/v1/messages"
GATEWAY_TOKEN = "sk-5d6620b953882a1a-i59ptx-f24fded0"
MODEL_NAME = "ag/gemini-3.8-flash-high"
PORTAL_URL_PREFIX = "https://man.vilix.org/man"

SYSTEM_PROMPT = """You are an expert technical translator specializing in Linux man pages and groff/troff/mandoc formatting for Parch Linux (an Arch-based distribution).
Translate the provided English man page roff content into fluent, idiomatic, technical Persian (فارسی).

CRITICAL RULES:
1. Output ONLY the raw valid groff man page content. Do NOT wrap with markdown ``` code fences. Do NOT add any preamble, explanation, or conversational notes.
2. Strictly preserve all groff macro structures (.TH, .SH, .SS, .TP, .PP, .P, .IP, .B, .I, .BR, .IR, .BI, .IB, .RB, .RI, .RS, .RE, .nf, .fi, .sp, .TS, .TE, comments .\\", escapes like \\&, \\(aq, \\(lq, \\(rq, \\-, \\e, \\fB, \\fI, \\fR, \\fC, \\f(CW, \\f[CR]).
3. Do NOT translate technical identifiers:
   - Command names, tool names, subcommands
   - Configuration directives, parameters, flags/options (-v, -h, --all, +e, etc.)
   - File paths, directory paths (/etc/..., /var/..., etc.)
   - Environment variables, signals, exit codes
   - Protocols/standards, code snippets, package names
4. In preformatted blocks (.nf to .fi, .EX to .EE, tables .TS to .TE):
   - Keep exact whitespace, indentation, monospace alignment verbatim.
5. URLs: Strictly NO trailing slash (e.g. <https://www.gnu.org/software/binutils> NOT <https://www.gnu.org/software/binutils/>).
6. Format for .SH "نام (NAME)":
   `command \\- خلاصه روان فارسی`
   (Always keep backslash before hyphen: \\-)
7. Standard bilingual section headers:
   .SH "نام (NAME)"
   .SH "خلاصه دستور (SYNOPSIS)"
   .SH "توضیحات (DESCRIPTION)"
   .SH "گزینه‌ها (OPTIONS)"
   .SH "مثال‌ها (EXAMPLES)"
   .SH "فایل‌ها (FILES)"
   .SH "محیط (ENVIRONMENT)"
   .SH "وضعیت خروج (EXIT STATUS)"
   .SH "خطاها (DIAGNOSTICS)"
   .SH "نویسندگان (AUTHORS)"
   .SH "گزارش باگ‌ها (BUGS)"
   .SH "همچنین ببینید (SEE ALSO)"
   .SH "کپی‌رایت و تکثیر (COPYRIGHT)"
8. Standard terms: گزینه (option), آرگومان (argument), خروجی (output), ورودی (input), پیش‌فرض (default), دایرکتوری/پوشه (directory), فایل (file), ریشه/مدیر سیستم (root/superuser).
"""

def call_llm(prompt, max_retries=3):
    req_data = {
        "model": MODEL_NAME,
        "max_tokens": 64000,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "system": SYSTEM_PROMPT
    }

    data_bytes = json.dumps(req_data).encode("utf-8")
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                GATEWAY_URL,
                data=data_bytes,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": GATEWAY_TOKEN,
                    "anthropic-version": "2023-06-01"
                }
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                text_parts = []
                for line in resp:
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if line_str.startswith("data: "):
                        data_json = line_str[6:]
                        if data_json == "[DONE]":
                            break
                        try:
                            ev = json.loads(data_json)
                            if ev.get("type") == "content_block_delta":
                                delta = ev.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text_parts.append(delta.get("text", ""))
                        except Exception:
                            pass

                raw = "".join(text_parts).strip()
                if raw.startswith("```"):
                    lines = raw.splitlines()
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    raw = "\n".join(lines).strip()

                # Clean up URLs with trailing slash before > or quotes
                raw = re.sub(r'(https?://[^\s>"\']+)/([>"\'])', r'\1\2', raw)

                if len(raw) > 20:
                    return raw
                else:
                    raise ValueError("Output too short or empty")
        except Exception as e:
            if attempt == max_retries:
                raise e
            time.sleep(2 * attempt)
    return ""

def chunk_roff_content(content, max_chunk_lines=350):
    lines = content.splitlines(keepends=True)
    if len(lines) <= max_chunk_lines and len(content.encode("utf-8")) <= 25000:
        return [content]

    chunks = []
    curr = []
    for line in lines:
        is_boundary = line.startswith(".SH") or line.startswith(".SS") or (
            len(curr) >= 200 and (line.startswith(".TP") or line.startswith(".IP") or line.startswith(".PP"))
        )
        if is_boundary and len(curr) >= 120:
            chunks.append("".join(curr))
            curr = [line]
        else:
            curr.append(line)
    if curr:
        chunks.append("".join(curr))
    return chunks

def translate_chunk(chunk):
    prompt = f"Translate the following Linux man page roff source code to fluent technical Persian:\n\n{chunk}"
    return call_llm(prompt)

def translate_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # If it's a .so alias link, no translation needed
    if content.strip().startswith(".so "):
        return True

    chunks = chunk_roff_content(content, max_chunk_lines=350)
    if len(chunks) == 1:
        translated = translate_chunk(chunks[0])
    else:
        # Multiple chunks: translate concurrently
        with ThreadPoolExecutor(max_workers=min(len(chunks), 8)) as ex:
            translated_chunks = list(ex.map(translate_chunk, chunks))
        translated = "".join(translated_chunks)

    # Post-process: ensure name line has \-
    lines = translated.splitlines(keepends=True)
    out_lines = []
    in_name = False
    for line in lines:
        if re.match(r'^\.(?:SH|Sh)\s+["\']?نام\s*\(NAME\)', line):
            in_name = True
            out_lines.append(line)
            continue
        if in_name and not line.startswith('.'):
            # replace unescaped - with \-
            fixed = re.sub(r'(?<=\S)\s+-\s+(?=\S)', r' \\- ', line, count=1)
            out_lines.append(fixed)
            in_name = False
            continue
        if in_name and line.startswith('.'):
            in_name = False
        out_lines.append(line)

    final_content = "".join(out_lines)

    # Write back
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(final_content)

    return True

def verify_file(file_path):
    p1 = subprocess.run(["mandoc", "-Tutf8", file_path], capture_output=True)
    if p1.returncode != 0:
        return False, f"mandoc utf8 failed: {p1.stderr.decode('utf-8', errors='replace')[:200]}"
    p2 = subprocess.run(["mandoc", "-Thtml", "-Ofragment", file_path], capture_output=True)
    if p2.returncode != 0:
        return False, f"mandoc html failed: {p2.stderr.decode('utf-8', errors='replace')[:200]}"
    return True, "OK"

def claim_next_tasks(count=7):
    p = subprocess.run(
        ["./task.py", "next", "--user", "sasiohae", "--count", str(count), "--claim"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True
    )
    if p.returncode != 0:
        print("Error claiming tasks:", p.stderr)
        return []

    lines = p.stdout.splitlines()
    tasks = []
    for line in lines:
        # Table format: '1    | command | 1 | pkg | prio | free'
        m = re.match(r'^\s*\d+\s*\|\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|', line)
        if m:
            cmd = m.group(1).strip()
            sec = m.group(2).strip()
            tasks.append((cmd, sec))

    return tasks

def process_batch(batch_num, total_batches):
    print(f"\n{'='*75}")
    print(f"🚀 STARTING BATCH {batch_num} OF {total_batches}")
    print(f"{'='*75}")

    tasks = claim_next_tasks(7)
    if not tasks:
        print("No more free tasks available for sasiohae!")
        return 0

    print(f"Claimed {len(tasks)} tasks:")
    for cmd, sec in tasks:
        print(f"  * {cmd}({sec})")

    # Parallel translation with ThreadPoolExecutor
    print(f"\n[Batch {batch_num}] Translating {len(tasks)} files concurrently...")
    start_t = time.time()
    errors = []

    def worker(task):
        cmd, sec = task
        fp = os.path.join(BASE_DIR, f"translations/fa/man{sec}/{cmd}.{sec}.fa")
        try:
            translate_file(fp)
            valid, msg = verify_file(fp)
            if not valid:
                # Retry once
                print(f"⚠️ Verification failed for {cmd}({sec}), retrying once: {msg}")
                translate_file(fp)
                valid, msg = verify_file(fp)
                if not valid:
                    return cmd, sec, fp, False, msg
            return cmd, sec, fp, True, "OK"
        except Exception as e:
            return cmd, sec, fp, False, str(e)

    results = []
    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = {executor.submit(worker, t): t for t in tasks}
        for future in as_completed(futures):
            results.append(future.result())

    dur = time.time() - start_t
    print(f"[Batch {batch_num}] All {len(tasks)} translations finished in {dur:.1f}s")

    # Dual verification & finish for each
    completed_in_batch = []
    for cmd, sec, fp, ok, msg in results:
        if not ok:
            print(f"❌ Error in {cmd}({sec}): {msg}")
            continue

        # Run task.py finish
        p_finish = subprocess.run(
            ["./task.py", "finish", "--cmd", cmd, "--section", sec],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        )
        if p_finish.returncode == 0:
            completed_in_batch.append((cmd, sec))
            portal_url = f"{PORTAL_URL_PREFIX}/{cmd}.{sec}.fa"
            print(f"  ✅ Completed & Indexed: {cmd}({sec}) -> {portal_url}")
        else:
            print(f"❌ task.py finish failed for {cmd}({sec}): {p_finish.stderr}")

    print(f"\n[Batch {batch_num}] Completed {len(completed_in_batch)} of {len(tasks)} tasks.")
    return len(completed_in_batch)

def main():
    total_batches = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    total_completed = 0
    start_all = time.time()

    for b in range(1, total_batches + 1):
        count = process_batch(b, total_batches)
        if count == 0:
            print("Finished all available tasks.")
            break
        total_completed += count
        elapsed = time.time() - start_all
        rate = total_completed / (elapsed / 60.0) if elapsed > 0 else 0
        rem_batches = total_batches - b
        eta_min = (rem_batches * 7) / rate if rate > 0 else 0
        print(f"📊 Progress: {total_completed}/{total_batches * 7} completed | Rate: {rate:.1f} pages/min | ETA: {eta_min:.1f} min")

    print("\n" + "="*75)
    print(f"🎉 ALL BATCHES COMPLETE! Total translated: {total_completed} pages.")
    print("="*75)

    # Show final stats
    subprocess.run(["./task.py", "stats"], cwd=BASE_DIR)

if __name__ == "__main__":
    main()
