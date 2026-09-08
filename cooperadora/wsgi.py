"""WSGI configuration for the Cooperadora project."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cooperadora.settings")

application = get_wsgi_application()
