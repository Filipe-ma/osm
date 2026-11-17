"""
OSM Microcrédito — WSGI
Localização: core/wsgi.py

Produção:
    gunicorn -w 9 -k gevent --worker-connections=1000 core.wsgi:application
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
application = get_wsgi_application()
