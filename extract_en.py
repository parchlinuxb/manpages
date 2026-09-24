#!/usr/bin/env python3
import sys
import os
import subprocess
import json

def extract_pages(pairs):
    """
    pairs: list of (cmd, sec)
    """
    script = """
import django, os, sys, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "local_settings")
django.setup()
from archmanweb.models import ManPage

pairs = json.loads(sys.argv[1])
results = {}
for cmd, sec in pairs:
    m = ManPage.objects.filter(name=cmd, section=sec, lang="en").first()
    if m and m.content:
        results[f"{cmd}.{sec}"] = m.content.raw
    else:
        results[f"{cmd}.{sec}"] = None
print(json.dumps(results))
"""
    cmd_run = ["docker", "compose", "exec", "-T", "web", "python", "-c", script, json.dumps(pairs)]
    res = subprocess.run(cmd_run, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error running docker exec: {res.stderr}", file=sys.stderr)
        return {}
    try:
        return json.loads(res.stdout)
    except Exception as e:
        print(f"Error parsing json from docker output: {e}\nOutput was: {res.stdout[:200]}", file=sys.stderr)
        return {}

def main():
    if len(sys.argv) < 3:
        print("Usage: extract_en.py <cmd1> <sec1> [<cmd2> <sec2> ...]")
        sys.exit(1)

    args = sys.argv[1:]
    pairs = []
    for i in range(0, len(args), 2):
        if i + 1 < len(args):
            pairs.append((args[i], args[i+1]))

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "en_sources")
    os.makedirs(out_dir, exist_ok=True)

    data = extract_pages(pairs)
    for key, content in data.items():
        if content:
            out_path = os.path.join(out_dir, f"{key}.en")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Extracted {key} -> {out_path} ({len(content)} chars)")
        else:
            print(f"Missing {key} in Docker database!", file=sys.stderr)

if __name__ == "__main__":
    main()
