from pathlib import Path
from django.apps import AppConfig
from django.conf import settings

class ArchLinuxCommonStyle(AppConfig):
    name = "archlinux_common_style.django"
    verbose_name = "Arch Linux common styles"

    def __init__(self, app_name, app_module):
        super().__init__(app_name, app_module)

        base_dir = Path(__file__).parent.parent

        # insert our static files directories to the project settings
        # https://docs.djangoproject.com/en/4.2/ref/settings/#prefixes-optional
        settings.STATICFILES_DIRS += [
            ("archlinux_common_style", str(base_dir / "css")),
            ("archlinux_common_style", str(base_dir / "img")),
        ]
