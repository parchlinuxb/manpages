#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parch Man Pages Task Tracker & CLI Tool
مدیریت و ردیابی فرآیند ترجمه صفحات راهنمای پارچ لینوکس
"""

import argparse
import csv
import fcntl
import getpass
import grp
import hashlib
import os
import pwd
import sqlite3
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "progress.db")
CSV_PATH = os.path.join(BASE_DIR, "progress.csv")
PORTAL_URL_PREFIX = "https://man.vilix.org/man"

KNOWN_USERS = ["debian", "ahoura", "parviz", "sasiohae", "jobin"]
ADMIN_USERS = ["root", "debian", "ahoura"]


def get_current_system_user():
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        try:
            return getpass.getuser()
        except Exception:
            return os.environ.get("USER", "unknown")


def resolve_and_verify_user(requested_user=None, action="عملیات روی تسک‌ها", allow_admin=True):
    current_user = get_current_system_user().lower()

    if not requested_user:
        if current_user in KNOWN_USERS or current_user in ADMIN_USERS:
            return current_user
        print(f"❌ خطای دسترسی: کاربر جاری سیستم '{current_user}' جزو مترجمان تعریف‌شده ({', '.join(KNOWN_USERS)}) نیست! لطفاً با کاربر مجاز اجرا فرمایید.", file=sys.stderr)
        sys.exit(1)

    target_user = requested_user.lower()
    if current_user == target_user:
        return target_user

    if allow_admin and current_user in ADMIN_USERS:
        return target_user

    print(f"❌ خطای عدم دسترسی: شما با نام کاربری '{current_user}' وارد شده‌اید و مجاز به انجام عملیات ({action}) بر روی تسک‌های کاربر '{target_user}' نیستید!", file=sys.stderr)
    sys.exit(1)


def unlock_task_file(cmd, sec, user):
    sec_dir = f"man{sec}"
    rel_path = f"translations/fa/{sec_dir}/{cmd}.{sec}.fa"
    full_path = os.path.join(BASE_DIR, rel_path)

    if os.path.exists(full_path):
        try:
            uid = pwd.getpwnam(user).pw_uid
            os.chown(full_path, uid, -1)
        except Exception:
            pass
        try:
            os.chmod(full_path, 0o664)
            return True
        except OSError as e:
            print(f"⚠️ هشدار: خطا در باز کردن دسترسی نوشتن برای {rel_path}: {e}", file=sys.stderr)
    return False


def lock_task_file(cmd, sec):
    sec_dir = f"man{sec}"
    rel_path = f"translations/fa/{sec_dir}/{cmd}.{sec}.fa"
    full_path = os.path.join(BASE_DIR, rel_path)

    if os.path.exists(full_path):
        try:
            os.chmod(full_path, 0o444)
            return True
        except OSError:
            pass
    return False


def ensure_db_permissions(path=DB_PATH):
    for p in [path, f"{path}-wal", f"{path}-shm"]:
        if os.path.exists(p):
            try:
                os.chmod(p, 0o664)
            except OSError:
                pass
            try:
                gid = grp.getgrnam("translators").gr_gid
                os.chown(p, -1, gid)
            except Exception:
                pass


def get_file_md5(path):
    if not os.path.exists(path):
        return None
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_meta(conn, key):
    row = conn.execute("SELECT value FROM _meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn, key, value):
    with conn:
        conn.execute("INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)", (key, value))


def init_db(conn):
    with conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            command TEXT,
            section TEXT,
            package TEXT,
            priority TEXT,
            user TEXT,
            status TEXT CHECK(status IN ('free', 'in_progress', 'completed')),
            file_path TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (command, section)
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks (user, status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks (status, priority);")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS _meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
    count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if count == 0 and os.path.exists(CSV_PATH):
        import_csv_to_db(conn, CSV_PATH)


def get_db():
    os.umask(0o002)
    init_needed = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    if init_needed:
        init_db(conn)
        ensure_db_permissions()
    return conn


def export_db_to_csv(conn, csv_path=CSV_PATH):
    cursor = conn.execute(
        "SELECT command, section, package, priority, user, status, file_path FROM tasks ORDER BY rowid"
    )
    rows = cursor.fetchall()

    temp_path = f"{csv_path}.{os.getpid()}.tmp"
    with open(temp_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\r\n")
        writer.writerow(["command", "section", "package", "priority", "user", "status", "file_path"])
        for r in rows:
            writer.writerow(list(r))

    try:
        os.chmod(temp_path, 0o664)
        gid = grp.getgrnam("translators").gr_gid
        os.chown(temp_path, -1, gid)
    except Exception:
        pass

    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            os.replace(temp_path, csv_path)
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    else:
        os.replace(temp_path, csv_path)

    new_hash = get_file_md5(csv_path)
    set_meta(conn, "csv_hash", new_hash)
    ensure_db_permissions()
    return len(rows)


def import_csv_to_db(conn, csv_path=CSV_PATH):
    if not os.path.exists(csv_path):
        return 0

    with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            reader = csv.DictReader(f)
            rows = list(reader)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    if not rows:
        return 0

    with conn:
        conn.executemany("""
        INSERT INTO tasks (command, section, package, priority, user, status, file_path)
        VALUES (:command, :section, :package, :priority, :user, :status, :file_path)
        ON CONFLICT(command, section) DO UPDATE SET
            package = excluded.package,
            priority = excluded.priority,
            user = excluded.user,
            status = excluded.status,
            file_path = excluded.file_path,
            updated_at = CURRENT_TIMESTAMP
        WHERE status != excluded.status
           OR user != excluded.user
           OR priority != excluded.priority
           OR package != excluded.package
           OR file_path != excluded.file_path
        """, rows)

    new_hash = get_file_md5(csv_path)
    set_meta(conn, "csv_hash", new_hash)
    ensure_db_permissions()
    return len(rows)


def auto_sync(conn):
    if not os.path.exists(CSV_PATH):
        return

    csv_hash = get_file_md5(CSV_PATH)
    recorded_hash = get_meta(conn, "csv_hash")
    if recorded_hash != csv_hash:
        import_csv_to_db(conn, CSV_PATH)


def load_tasks():
    conn = get_db()
    auto_sync(conn)
    cursor = conn.execute(
        "SELECT command, section, package, priority, user, status, file_path FROM tasks ORDER BY rowid"
    )
    return [dict(r) for r in cursor.fetchall()]


def save_tasks(tasks):
    if not tasks:
        return
    conn = get_db()
    with conn:
        conn.executemany("""
        INSERT INTO tasks (command, section, package, priority, user, status, file_path)
        VALUES (:command, :section, :package, :priority, :user, :status, :file_path)
        ON CONFLICT(command, section) DO UPDATE SET
            package = excluded.package,
            priority = excluded.priority,
            user = excluded.user,
            status = excluded.status,
            file_path = excluded.file_path,
            updated_at = CURRENT_TIMESTAMP
        WHERE status != excluded.status
           OR user != excluded.user
           OR priority != excluded.priority
           OR package != excluded.package
           OR file_path != excluded.file_path
        """, tasks)
    ensure_db_permissions()


def cmd_stats(args):
    conn = get_db()
    auto_sync(conn)

    total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'").fetchone()[0]
    in_progress = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'in_progress'").fetchone()[0]
    free = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'free'").fetchone()[0]
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
    db_users_rows = conn.execute("SELECT DISTINCT user FROM tasks WHERE user IS NOT NULL AND user != ''").fetchall()
    db_users = [r[0] for r in db_users_rows]
    users = list(dict.fromkeys(known_users + [u for u in db_users if u not in known_users]))

    user_stats_rows = conn.execute("""
        SELECT user, status, COUNT(*) as cnt
        FROM tasks
        GROUP BY user, status
    """).fetchall()

    stats_by_user = {}
    for r in user_stats_rows:
        stats_by_user.setdefault(r["user"], {})[r["status"]] = r["cnt"]

    print(f"{'User':<10} | {'Total':<7} | {'Done':<7} | {'Active':<7} | {'User Progress':<14} | {'Team Share'}")
    print("-" * 75)
    for u in users:
        u_dict = stats_by_user.get(u, {})
        u_comp = u_dict.get("completed", 0)
        u_prog = u_dict.get("in_progress", 0)
        u_free = u_dict.get("free", 0)
        u_total = u_comp + u_prog + u_free
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
    prio_rows = conn.execute("""
        SELECT priority,
               COUNT(*) as total,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as comp
        FROM tasks
        WHERE priority IN ('1', '2', '3')
        GROUP BY priority
    """).fetchall()
    prio_map = {str(r["priority"]): (r["total"], r["comp"]) for r in prio_rows}

    for prio in ["1", "2", "3"]:
        p_total, p_comp = prio_map.get(prio, (0, 0))
        p_label = labels.get(prio, prio)
        p_pct = (p_comp / p_total * 100) if p_total > 0 else 0
        print(f"  * {p_label:<32}: {p_comp:,} / {p_total:,} ({p_pct:.1f}%)")
    print("=" * 75)


def cmd_list(args):
    conn = get_db()
    auto_sync(conn)

    where_clauses = []
    params = []

    if args.user:
        where_clauses.append("LOWER(user) = LOWER(?)")
        params.append(args.user)

    if args.status:
        if args.status == "incomplete":
            where_clauses.append("status != 'completed'")
        else:
            where_clauses.append("status = ?")
            params.append(args.status)

    if args.priority:
        where_clauses.append("priority = ?")
        params.append(str(args.priority))

    if args.search:
        s = f"%{args.search.lower()}%"
        where_clauses.append("(LOWER(command) LIKE ? OR LOWER(package) LIKE ?)")
        params.extend([s, s])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_sql = f"SELECT COUNT(*) FROM tasks {where_sql}"
    total_found = conn.execute(count_sql, params).fetchone()[0]

    limit = args.limit if args.limit and args.limit > 0 else 50
    query_sql = f"""
        SELECT command, section, package, priority, user, status, file_path
        FROM tasks
        {where_sql}
        ORDER BY rowid
        LIMIT ?
    """
    display_rows = conn.execute(query_sql, params + [limit]).fetchall()

    user_str = f" [User: {args.user}]" if args.user else ""
    status_str = f" [Status: {args.status}]" if args.status else ""
    print(f"Search Results{user_str}{status_str}: {total_found:,} items found (showing first {len(display_rows)}):\n")

    print(f"{'Command':<24} | {'Sec':<4} | {'Package':<18} | {'Prio':<5} | {'User':<9} | {'Status':<11} | {'File Path'}")
    print("-" * 110)
    for t in display_rows:
        fp = t["file_path"] or ""
        pkg = t["package"] or "-"
        prio = t["priority"] or "-"
        print(f"{t['command']:<24} | {t['section']:<4} | {pkg:<18} | {prio:<5} | {t['user']:<9} | {t['status']:<11} | {fp}")

    if total_found > limit:
        print(f"\n... and {total_found - limit:,} more items (use --limit to view more).")


def cmd_next(args):
    conn = get_db()
    auto_sync(conn)

    user = resolve_and_verify_user(args.user, action="رزرو و دریافت تسک")
    count = args.count if args.count and args.count > 0 else 4

    query = """
        SELECT command, section, package, priority, user, status, file_path
        FROM tasks
        WHERE LOWER(user) = LOWER(?) AND status = 'free'
        ORDER BY CAST(COALESCE(priority, '3') AS INTEGER) ASC, package ASC, command ASC
        LIMIT ?
    """
    selected = conn.execute(query, (user, count)).fetchall()

    if not selected:
        print(f"No free tasks found for user '{user}'!")
        return

    print(f"Next {len(selected)} tasks for user '{user}':\n")
    print(f"{'#':<4} | {'Command':<22} | {'Sec':<4} | {'Package':<18} | {'Prio':<5} | {'Status'}")
    print("-" * 70)
    for i, t in enumerate(selected, 1):
        pkg = t["package"] or "-"
        prio = t["priority"] or "-"
        print(f"{i:<4} | {t['command']:<22} | {t['section']:<4} | {pkg:<18} | {prio:<5} | {t['status']}")

    if args.claim:
        keys = [(t["command"], t["section"]) for t in selected]
        with conn:
            conn.executemany(
                "UPDATE tasks SET status = 'in_progress', updated_at = CURRENT_TIMESTAMP WHERE command = ? AND section = ?",
                keys
            )
        ensure_db_permissions()

        # Unlock the files specifically for editing by this user
        unlocked = 0
        for t in selected:
            if unlock_task_file(t["command"], t["section"], user):
                unlocked += 1

        print(f"\n✅ وضعیت {len(selected)} دستور فوق در دیتابیس به 'in_progress' تغییر یافت.")
        print(f"🔓 دسترسی نوشتن روی {unlocked} فایل مربوطه منحصراً برای کاربر '{user}' باز شد.")
    else:
        print("\n💡 برای رزرو و تغییر وضعیت خودکار آن‌ها به 'in_progress'، از سوییچ --claim استفاده کنید:")
        print(f"   ./task.py next --user {user} --count {count} --claim")


def cmd_finish(args):
    conn = get_db()
    auto_sync(conn)

    cmd = args.command
    sec = args.section

    row = conn.execute(
        "SELECT command, section, package, priority, user, status, file_path FROM tasks WHERE command = ? AND section = ?",
        (cmd, sec)
    ).fetchone()

    if not row:
        print(f"خطا: دستور {cmd}({sec}) در progress.csv یافت نشد!", file=sys.stderr)
        sys.exit(1)

    # Check assigned user identity
    assigned_user = (row["user"] or "").lower()
    current_user = get_current_system_user().lower()
    if current_user != assigned_user and current_user not in ADMIN_USERS:
        print(f"❌ خطای عدم دسترسی: دستور {cmd}({sec}) به کاربر '{assigned_user}' اختصاص دارد، اما شما با کاربر '{current_user}' وارد شده‌اید و مجاز به ثبت آن نیستید!", file=sys.stderr)
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

    with conn:
        conn.execute(
            "UPDATE tasks SET status = 'completed', file_path = ?, updated_at = CURRENT_TIMESTAMP WHERE command = ? AND section = ?",
            (expected_path, cmd, sec)
        )
    ensure_db_permissions()

    # Lock the file back to read-only 0444
    lock_task_file(cmd, sec)

    portal_url = f"{PORTAL_URL_PREFIX}/{cmd}.{sec}.fa"
    print("\n" + "=" * 65)
    print(f"🎉 دستور {cmd}({sec}) با موفقیت به عنوان 'completed' ثبت شد!")
    print(f"📁 مسیر فایل: {expected_path}")
    print("🔒 فایل ترجمه به حالت فقط-خواندنی (Read-Only) محافظت شد.")
    print(f"🔗 پیوند رسمی وب‌پرتال: {portal_url}")
    print("=" * 65)


def cmd_export_csv(args):
    conn = get_db()
    target_path = args.output if args.output else CSV_PATH
    count = export_db_to_csv(conn, target_path)
    print(f"✅ خروجی CSV با موفقیت در '{target_path}' ذخیره شد ({count:,} رکورد).")


def cmd_import_csv(args):
    conn = get_db()
    input_path = args.input if args.input else CSV_PATH
    if not os.path.exists(input_path):
        print(f"خطا: فایل {input_path} یافت نشد!", file=sys.stderr)
        sys.exit(1)
    count = import_csv_to_db(conn, input_path)
    print(f"✅ اطلاعات فایل '{input_path}' با موفقیت در پایگاه‌داده SQLite وارد شد ({count:,} رکورد).")


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
    p_next.add_argument("--user", "-u", required=False, default=None, help="نام کاربر (اختیاری؛ در صورت خالی بودن، کاربر جاری لینوکس خودکار تشخیص داده می‌شود)")
    p_next.add_argument("--count", "-c", type=int, default=4, help="تعداد دستورات مورد نیاز (پیش‌فرض: ۴)")
    p_next.add_argument("--claim", action="store_true", help="رزرو خودکار و تغییر وضعیت به in_progress در CSV")
    p_next.set_defaults(func=cmd_next)

    p_finish = subparsers.add_parser("finish", help="اعتبارسنجی، ایمپورت داکر و ثبت اتمام ترجمه دستور")
    p_finish.add_argument("--cmd", dest="command", required=True, help="نام دستور (مانند grep)")
    p_finish.add_argument("--section", "-s", required=True, help="شماره بخش (مانند 1)")
    p_finish.add_argument("--skip-verify", action="store_true", help="رد کردن اعتبارسنجی mandoc")
    p_finish.add_argument("--skip-docker", action="store_true", help="رد کردن اجرای import_to_docker.sh")
    p_finish.set_defaults(func=cmd_finish)

    p_export = subparsers.add_parser("export-csv", help="خروجی گرفتن از پایگاه‌داده SQLite به فایل CSV")
    p_export.add_argument("--output", "-o", default=CSV_PATH, help=f"مسیر فایل خروجی CSV (پیش‌فرض: {CSV_PATH})")
    p_export.set_defaults(func=cmd_export_csv)

    p_import = subparsers.add_parser("import-csv", help="وارد کردن دستی داده‌ها از فایل CSV به پایگاه‌داده SQLite")
    p_import.add_argument("--input", "-i", default=CSV_PATH, help=f"مسیر فایل ورودی CSV (پیش‌فرض: {CSV_PATH})")
    p_import.set_defaults(func=cmd_import_csv)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
