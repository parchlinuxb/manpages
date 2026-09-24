#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parch Man Pages Task Tracker & CLI Tool
مدیریت و ردیابی فرآیند ترجمه صفحات راهنمای پارچ لینوکس
"""

import argparse
import csv
import fcntl
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "progress.csv")
PORTAL_URL_PREFIX = "https://man.vilix.org/man"


def load_tasks():
    if not os.path.exists(CSV_PATH):
        print(f"Error: {CSV_PATH} not found.", file=sys.stderr)
        sys.exit(1)

    tasks = []
    with open(CSV_PATH, mode="r", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            reader = csv.DictReader(f)
            for row in reader:
                tasks.append(row)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return tasks


def save_tasks(tasks):
    if not tasks:
        return
    fieldnames = list(tasks[0].keys())
    with open(CSV_PATH, mode="r+", newline="", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            # Re-read existing file to merge completed/in_progress from other concurrent writers
            current_reader = csv.DictReader(f)
            current_map = {(r["command"], r["section"]): r for r in current_reader}
            
            # Update current map with our changes, preserving completed and active states
            for t in tasks:
                key = (t["command"], t["section"])
                cur = current_map.get(key)
                if cur:
                    if cur.get("status") == "completed" and t.get("status") != "completed":
                        continue
                    if cur.get("status") == "in_progress" and t.get("status") == "free":
                        continue
                current_map[key] = t
                
            f.seek(0)
            f.truncate()
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for r in tasks:
                # write in original order but with updated row
                key = (r["command"], r["section"])
                writer.writerow(current_map.get(key, r))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)



def cmd_stats(args):
    tasks = load_tasks()
    total = len(tasks)
    completed = sum(1 for t in tasks if t["status"] == "completed")
    in_progress = sum(1 for t in tasks if t["status"] == "in_progress")
    free = sum(1 for t in tasks if t["status"] == "free")
    pct = (completed / total * 100) if total > 0 else 0

    print("=" * 75)
    print("           PARCH MAN PAGES TRANSLATION PROGRESS REPORT           ")
    print("=" * 75)
    print(f"Total Indexed Pages:     {total:,}")
    print(f"Completed (Done):        {completed:,}  ({pct:.2f}%)")
    print(f"In Progress (Active):    {in_progress:,}")
    print(f"Pending (Free):          {free:,}")
    print("-" * 75)

    # Breakdown per user
    known_users = ["debian", "ahoura", "parviz", "sasiohae", "jobin"]
    csv_users = [t["user"] for t in tasks if t.get("user")]
    users = list(dict.fromkeys(known_users + [u for u in csv_users if u not in known_users]))
    print(f"{'User':<10} | {'Total':<7} | {'Done':<7} | {'Active':<7} | {'User Progress':<14} | {'Team Share'}")
    print("-" * 75)
    for u in users:
        u_tasks = [t for t in tasks if t["user"] == u]
        u_total = len(u_tasks)
        u_comp = sum(1 for t in u_tasks if t["status"] == "completed")
        u_prog = sum(1 for t in u_tasks if t["status"] == "in_progress")
        u_free = sum(1 for t in u_tasks if t["status"] == "free")
        u_pct = (u_comp / u_total * 100) if u_total > 0 else 0
        share_pct = (u_comp / completed * 100) if completed > 0 else 0
        print(f"{u:<10} | {u_total:<7,} | {u_comp:<7,} | {u_prog:<7,} | {u_pct:<13.2f}% | {share_pct:.1f}% ({u_comp}/{completed})")

    print("-" * 75)
    # Breakdown per priority
    print("Breakdown by Priority:")
    labels = {
        "1": "Priority 1 (Core / Critical)",
        "2": "Priority 2 (High / Services)",
        "3": "Priority 3 (Extended / Extra)"
    }
    for prio in ["1", "2", "3"]:
        p_tasks = [t for t in tasks if t.get("priority") == prio]
        p_total = len(p_tasks)
        p_comp = sum(1 for t in p_tasks if t["status"] == "completed")
        p_label = labels.get(prio, prio)
        p_pct = (p_comp / p_total * 100) if p_total > 0 else 0
        print(f"  * {p_label:<32}: {p_comp:,} / {p_total:,} ({p_pct:.1f}%)")
    print("=" * 75)


def cmd_list(args):
    tasks = load_tasks()

    filtered = tasks
    if args.user:
        filtered = [t for t in filtered if t["user"].lower() == args.user.lower()]

    if args.status:
        if args.status == "incomplete":
            filtered = [t for t in filtered if t["status"] != "completed"]
        else:
            filtered = [t for t in filtered if t["status"] == args.status]

    if args.priority:
        filtered = [t for t in filtered if t.get("priority") == str(args.priority)]

    if args.search:
        s = args.search.lower()
        filtered = [t for t in filtered if s in t["command"].lower() or s in t.get("package", "").lower()]

    total_found = len(filtered)
    limit = args.limit if args.limit and args.limit > 0 else 50
    display_rows = filtered[:limit]

    user_str = f" [User: {args.user}]" if args.user else ""
    status_str = f" [Status: {args.status}]" if args.status else ""
    print(f"Search Results{user_str}{status_str}: {total_found:,} items found (showing first {len(display_rows)}):\n")

    print(f"{'Command':<24} | {'Sec':<4} | {'Package':<18} | {'Prio':<5} | {'User':<9} | {'Status':<11} | {'File Path'}")
    print("-" * 110)
    for t in display_rows:
        fp = t.get("file_path", "")
        print(f"{t['command']:<24} | {t['section']:<4} | {t.get('package', '-'):<18} | {t.get('priority', '-'):<5} | {t['user']:<9} | {t['status']:<11} | {fp}")

    if total_found > limit:
        print(f"\n... and {total_found - limit:,} more items (use --limit to view more).")


def cmd_next(args):
    tasks = load_tasks()
    user = args.user.lower()
    count = args.count if args.count and args.count > 0 else 4

    free_tasks = [t for t in tasks if t["user"].lower() == user and t["status"] == "free"]

    if not free_tasks:
        print(f"No free tasks found for user '{user}'!")
        return

    def sort_key(item):
        try:
            prio = int(item.get("priority", 3))
        except ValueError:
            prio = 3
        return (prio, item.get("package", ""), item["command"])

    free_tasks.sort(key=sort_key)
    selected = free_tasks[:count]

    print(f"Next {len(selected)} tasks for user '{user}':\n")
    print(f"{'#':<4} | {'Command':<22} | {'Sec':<4} | {'Package':<18} | {'Prio':<5} | {'Status'}")
    print("-" * 70)
    for i, t in enumerate(selected, 1):
        print(f"{i:<4} | {t['command']:<22} | {t['section']:<4} | {t.get('package', '-'):<18} | {t.get('priority', '-'):<5} | {t['status']}")

    if args.claim:
        claimed_keys = {(t["command"], t["section"]) for t in selected}
        for t in tasks:
            if (t["command"], t["section"]) in claimed_keys:

                t["status"] = "in_progress"
        save_tasks(tasks)
        print(f"\n✅ وضعیت {len(selected)} دستور فوق در progress.csv به 'in_progress' تغییر یافت.")
    else:
        print("\n💡 برای رزرو و تغییر وضعیت خودکار آن‌ها به 'in_progress'، از سوییچ --claim استفاده کنید:")
        print(f"   ./task.py next --user {user} --count {count} --claim")


def cmd_finish(args):
    cmd = args.command
    sec = args.section
    tasks = load_tasks()

    target = None
    for t in tasks:
        if t["command"] == cmd and t["section"] == sec:
            target = t
            break

    if not target:
        print(f"خطا: دستور {cmd}({sec}) در progress.csv یافت نشد!", file=sys.stderr)
        sys.exit(1)

    sec_dir = f"man{sec}"
    expected_path = f"translations/fa/{sec_dir}/{cmd}.{sec}.fa"
    full_path = os.path.join(BASE_DIR, expected_path)

    if not os.path.exists(full_path):
        print(f"خطا: فایل ترجمه در مسیر زیر یافت نشد:\n{full_path}", file=sys.stderr)
        sys.exit(1)

    if not args.skip_verify:
        print("🔍 در حال اجرای گیت اعتبارسنجی دوگانه (Dual Verification Gate)...")
        p1 = subprocess.run(["mandoc", "-Tutf8", full_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p1.returncode != 0:
            print(f"❌ خطای رندر utf8 در mandoc:\n{p1.stderr.decode('utf-8')}", file=sys.stderr)
            sys.exit(1)
        p2 = subprocess.run(["mandoc", "-Thtml", "-Ofragment", full_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p2.returncode != 0:
            print(f"❌ خطای رندر HTML در mandoc:\n{p2.stderr.decode('utf-8')}", file=sys.stderr)
            sys.exit(1)
        print("✅ گیت اعتبارسنجی دوگانه با موفقیت کامل پاس شد.")

    if not args.skip_docker:
        print("🐳 در حال ایمپورت و ایندکس در دیتابیس داکر...")
        p_docker = subprocess.run(["./import_to_docker.sh", full_path], cwd=BASE_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p_docker.returncode != 0:
            print(f"❌ خطا در اجرای import_to_docker.sh:\n{p_docker.stderr.decode('utf-8')}", file=sys.stderr)
            sys.exit(1)
        print("✅ با موفقیت در دیتابیس داکر ذخیره شد.")

    target["status"] = "completed"
    target["file_path"] = expected_path
    save_tasks(tasks)

    portal_url = f"{PORTAL_URL_PREFIX}/{cmd}.{sec}.fa"
    print("\n" + "=" * 65)
    print(f"🎉 دستور {cmd}({sec}) با موفقیت به عنوان 'completed' ثبت شد!")
    print(f"📁 مسیر فایل: {expected_path}")
    print(f"🔗 پیوند رسمی وب‌پرتال: {portal_url}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(
        description="ابزار مدیریت و ردیابی وظایف ترجمه صفحات راهنمای پارچ لینوکس",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    p_stats = subparsers.add_parser("stats", help="نمایش آمار و داشبورد پیشرفت کل پروژه")
    p_stats.set_defaults(func=cmd_stats)

    p_list = subparsers.add_parser("list", help="فهرست کردن و فیلتر کردن تسک‌ها بر اساس کاربر و وضعیت")
    p_list.add_argument("--user", "-u", help="نام کاربر (debian, ahoura, parviz, sasiohae, jobin)")
    p_list.add_argument("--status", "-s", choices=["free", "in_progress", "completed", "incomplete"], help="وضعیت دستور")
    p_list.add_argument("--priority", "-p", choices=["1", "2", "3"], help="سطح اولویت")
    p_list.add_argument("--search", "-q", help="جستجو در نام دستور یا پکیج")
    p_list.add_argument("--limit", "-l", type=int, default=30, help="تعداد نتایج نمایشی (پیش‌فرض: ۳۰)")
    p_list.set_defaults(func=cmd_list)

    p_next = subparsers.add_parser("next", help="دریافت دستورات بعدی برای ترجمه بر اساس اولویت کاربر")
    p_next.add_argument("--user", "-u", required=True, help="نام کاربر (debian, ahoura, parviz, sasiohae, jobin)")
    p_next.add_argument("--count", "-c", type=int, default=4, help="تعداد دستورات مورد نیاز (پیش‌فرض: ۴)")
    p_next.add_argument("--claim", action="store_true", help="رزرو خودکار و تغییر وضعیت به in_progress در CSV")
    p_next.set_defaults(func=cmd_next)

    p_finish = subparsers.add_parser("finish", help="اعتبارسنجی، ایمپورت داکر و ثبت اتمام ترجمه دستور")
    p_finish.add_argument("--cmd", dest="command", required=True, help="نام دستور (مانند grep)")
    p_finish.add_argument("--section", "-s", required=True, help="شماره بخش (مانند 1)")
    p_finish.add_argument("--skip-verify", action="store_true", help="رد کردن اعتبارسنجی mandoc")
    p_finish.add_argument("--skip-docker", action="store_true", help="رد کردن اجرای import_to_docker.sh")
    p_finish.set_defaults(func=cmd_finish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
