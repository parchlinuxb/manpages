import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from archmanweb.models import Content, ManPage, Package
from archmanweb.utils import extract_description, mandoc_convert, postprocess, preprocess


class Command(BaseCommand):
    help = "Import local Persian man page translations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            default="",
            help="Directory containing translations (defaults to translations/fa relative to BASE_DIR)",
        )
        parser.add_argument(
            "--repo",
            default="core",
            help="Fallback repository name",
        )

    def handle(self, *args, **options):
        dir_arg = options.get("dir")
        if dir_arg:
            source_dir = Path(dir_arg)
            if not source_dir.is_absolute():
                source_dir = Path(settings.BASE_DIR) / source_dir
        else:
            source_dir = Path(settings.BASE_DIR) / "translations" / "fa"

        if not source_dir.exists():
            # Try fallback to /app/translations/fa or relative
            candidate = Path("/app/translations/fa")
            if candidate.exists():
                source_dir = candidate
            else:
                self.stderr.write(f"Translations directory not found at: {source_dir}")
                return

        repo = options["repo"]
        pattern = re.compile(r"^(.+)\.([1-9][a-zA-Z0-9]*)\.fa$")
        imported_count = 0
        skipped_count = 0

        self.stdout.write(f"Scanning translations from: {source_dir}")
        existing_fa = {
            (m.name, m.section): m
            for m in ManPage.objects.filter(lang="fa").select_related("content", "converted_content")
        }

        fallback_pkg = None

        for file_path in sorted(source_dir.rglob("*.*.fa")):
            if not file_path.is_file():
                continue

            match = pattern.match(file_path.name)
            if not match:
                continue

            name = match.group(1)
            section = match.group(2)
            raw = file_path.read_text(encoding="utf-8")

            man = existing_fa.get((name, section))
            if man and man.content and man.content.raw == raw and man.converted_content_id:
                skipped_count += 1
                continue

            existing_man = ManPage.objects.filter(name=name, section=section, lang="en").first()
            if existing_man:
                pkg = existing_man.package
            else:
                pkg = Package.objects.filter(name=name).first()
                if not pkg:
                    if not fallback_pkg:
                        fallback_pkg, _ = Package.objects.get_or_create(
                            repo=repo,
                            name="parch-translations",
                            defaults={
                                "version": "1.0",
                                "arch": "any",
                                "description": "Parch Linux Translations",
                                "build_date": timezone.now(),
                                "licenses": ["GPL"],
                            },
                        )
                    pkg = fallback_pkg

            raw_pre_txt = preprocess(raw, "txt")
            txt = postprocess(mandoc_convert(raw_pre_txt, "txt", lang="fa"), "txt", lang="fa")
            raw_pre_html = preprocess(raw, "html")
            html = postprocess(mandoc_convert(raw_pre_html, "html", lang="fa"), "html", lang="fa")
            desc = extract_description(txt, lang="fa")

            if man and man.content:
                content = man.content
            else:
                content = Content()

            content.raw = raw
            content.txt = txt
            content.html = html
            content.description = desc
            content.save()

            if not man:
                man = ManPage(
                    package=pkg,
                    name=name,
                    section=section,
                    lang="fa",
                    content=content,
                    converted_content=content,
                )
                man.save()
                existing_fa[(name, section)] = man
            else:
                man.content = content
                man.converted_content = content
                man.save(update_fields=["content", "converted_content"])

            imported_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {imported_count} imported/updated, {skipped_count} already up-to-date."
            )
        )

