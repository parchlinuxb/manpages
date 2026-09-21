import re
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from archmanweb.models import Content, ManPage, Package
from archmanweb.utils import extract_description, mandoc_convert, postprocess, preprocess


class Command(BaseCommand):
    help = "Import local Persian man page translations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            default="/home/debian/parch-man/translations/fa",
            help="Directory containing translations",
        )
        parser.add_argument(
            "--repo",
            default="core",
            help="Fallback repository name",
        )

    def handle(self, *args, **options):
        # ponytail: sequential file processing; add multiprocessing/batch db ops when translation count grows to thousands
        source_dir = Path(options["dir"])
        repo = options["repo"]

        pattern = re.compile(r"^(.+)\.([1-9])\.fa$")
        imported_count = 0

        for file_path in sorted(source_dir.rglob("*.[1-9].fa")):
            if not file_path.is_file():
                continue

            match = pattern.match(file_path.name)
            if not match:
                continue

            name = match.group(1)
            section = match.group(2)

            existing_man = ManPage.objects.filter(name=name, section=section, lang="en").first()
            if existing_man:
                pkg = existing_man.package
            else:
                pkg = Package.objects.filter(name=name).first()
                if not pkg:
                    pkg, _ = Package.objects.get_or_create(
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

            raw = file_path.read_text(encoding="utf-8")
            raw_pre_txt = preprocess(raw, "txt")
            txt = postprocess(mandoc_convert(raw_pre_txt, "txt", lang="fa"), "txt", lang="fa")
            raw_pre_html = preprocess(raw, "html")
            html = postprocess(mandoc_convert(raw_pre_html, "html", lang="fa"), "html", lang="fa")
            desc = extract_description(txt, lang="fa")

            man = ManPage.objects.filter(name=name, section=section, lang="fa").first()
            if man:
                content = man.content
            else:
                content = Content()

            content.raw = raw
            content.txt = txt
            content.html = html
            content.description = desc
            content.save()

            if not man:
                man = ManPage(package=pkg, name=name, section=section, lang="fa", content=content)
                man.save()

            imported_count += 1

        self.stdout.write(self.style.SUCCESS(f"Imported {imported_count} translations."))
