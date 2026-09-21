# Django integration

Files in this directory implement a Django app for the integration
of archlinux-common-style in downstream Django-based projects.

## Installation

The app requires that Django can import the `archlinux_common_style.django`
module in the project where this app is used. This can be achieved by having
archlinux-common-style as a git submodule in the project, but with the
non-canonical name with underscores instead of dashes: `archlinux_common_style`.

## Configuration

The archlinux-common-style app can be enabled in a Django project with a simple
configuration:

```python
INSTALLED_APPS = [
    ...
    "archlinux_common_style.django",
    ...
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {
            "loaders": [
                (
                    "django.template.loaders.cached.Loader",
                    [
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                        "archlinux_common_style.django.template_loader.Loader",
                    ],
                ),
            ],
            ...
        },
        ...
    },
    ...
]
```

Note that the app itself modifies the `STATICFILES_DIRS` setting such that
static resources from archlinux-common-style can be looked up by Django.
Unfortunately the configuration for the template loader is more involved and
must be done manually.

## Usage

The app follows the conventions for Django apps where resources such as static
files and templates are "namespaced" with a prefix based on the app name.
Here the prefix is `archlinux_common_style/`. Hence, the following snippets can
be used in the Django project where the app is enabled:

1. Include the navbar template:

   ```django
   <header>
       {% include "archlinux_common_style/navbar-django.html" %}
   </header>
   ```

   If you need to override URLs for some links:

   ```django
   <header>
       {% include "archlinux_common_style/navbar-django.html" with anb_home_url="/" anb_packages_url="/packages/" anb_download_url="/download/" %}
   </header>
   ```

2. Use the CSS for navbar:

   ```django
   <link rel="stylesheet" type="text/css" href="{% static "archlinux_common_style/navbar.css" %}" />
   ```

3. Use the Arch Linux favicon:

   ```django
   <link rel="icon" type="image/png" href="{% static "archlinux_common_style/favicon.png" %}" />
   <link rel="shortcut icon" type="image/png" href="{% static "archlinux_common_style/favicon.png" %}" />
   ```
