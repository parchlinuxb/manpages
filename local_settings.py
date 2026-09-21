import os
try:
    import pyalpm
except ImportError:
    import sys
    from unittest.mock import MagicMock
    sys.modules['pyalpm'] = MagicMock()

from settings import *

DEBUG = os.environ.get('DEBUG', 'False') == 'True'
SECRET_KEY = os.environ.get('SECRET_KEY', 'parch_man_pages_secret_key_prod_2026_super_secure')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'man.parchlinux.com,*.parchlinux.com,man.vilix.org,127.0.0.1,localhost').split(',')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'archmanweb'),
        'USER': os.environ.get('POSTGRES_USER', 'archmanweb'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'parch_secret_db_2026'),
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', 600)),
    }
}

# CSP Settings - allow inline scripts for theme switcher
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")
CSP_IMG_SRC = ("'self'", "data:")
