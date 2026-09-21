"""
Wrapper for loading templates from the "html" directory in the
archlinux-common-style project. It loads only template names that are
"namespaced", i.e. prefixed with the "archlinux_common_style/" prefix.
"""

from pathlib import Path

from django.template import Origin, TemplateDoesNotExist
from django.template.loaders.base import Loader as BaseLoader

class Loader(BaseLoader):
    def __init__(self, engine):
        super().__init__(engine)

        self.prefix = "archlinux_common_style"
        self.dir = Path(__file__).parent.parent / "html"
        assert self.dir.is_dir()

    def get_contents(self, origin):
        try:
            with open(origin.name, encoding=self.engine.file_charset) as fp:
                return fp.read()
        except FileNotFoundError:
            raise TemplateDoesNotExist(origin)

    def get_template_sources(self, template_name):
        if template_name.startswith(self.prefix + "/"):
            _, name = template_name.split("/", maxsplit=1)
            path = self.dir / name
            if path.is_file():
                yield Origin(
                    name=str(path),
                    template_name=template_name,
                    loader=self,
                )
