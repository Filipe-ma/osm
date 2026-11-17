from pathlib import Path
import dj_database_url
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# ── SEGREDOS E MODO ────────────────────────────────────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY', '0k7(=3xy503l5nio^)k29b1ryxyfm)r%k)))4xqq3li4)og%9c')
DEBUG      = os.environ.get('DEBUG', 'True') == 'True'

# ── HOSTS ──────────────────────────────────────────────────────────────
_RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    'i-sgb-backend-1.onrender.com',
    'i-sgb-backend.onrender.com',
    'osm.co.mz',
    'app.osm.co.mz',
]
if _RENDER_HOST:
    ALLOWED_HOSTS.append(_RENDER_HOST)
if DEBUG:
    ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://i-sgb-backend.onrender.com',
    'https://osm.co.mz',
    'https://app.osm.co.mz',
    'https://i-sgb-backend-1.onrender.com',
]
if _RENDER_HOST:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_RENDER_HOST}')

# ── APPS ───────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'osm',
]

# ── MIDDLEWARE ─────────────────────────────────────────────────────────
# WhiteNoiseMiddleware DEVE ser a 2ª — logo após SecurityMiddleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'osm.middleware.RateLimitLoginMiddleware',
    'osm.middleware.ForcarTrocaSenhaMiddleware',
    'osm.middleware.RegistarActividadeMiddleware',
    'osm.middleware.LicencaMiddleware',
    'osm.middleware.CodigoSuperAdminMiddleware',
]

ROOT_URLCONF     = 'core.urls'
WSGI_APPLICATION = 'core.wsgi.application'

# ── TEMPLATES ──────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'osm.context_processors.osm_global',
            ],
        },
    },
]

# ── BASE DE DADOS ──────────────────────────────────────────────────────
DATABASES = {
    'default': dj_database_url.parse(
        "postgresql://postgres.vnyzklcnmammgnckttgw:Aventureiro%402020@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require"
    )
}

# Adiciona opções personalizadas
DATABASES['default']['CONN_MAX_AGE'] = 60   # mantém conexão por 60s
DATABASES['default']['OPTIONS'] = {
    'connect_timeout': 20,   # timeout de conexão (psycopg2)
}

# ── CACHE ──────────────────────────────────────────────────────────────
# LocMemCache apenas para rate-limit e outros caches de curta duração.
# NÃO é usado para sessões (ver SESSION_ENGINE abaixo).
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'osm-v3',
        'TIMEOUT': 300,
        'OPTIONS': {'MAX_ENTRIES': 10000},
    }
}

# ── SESSÕES ────────────────────────────────────────────────────────────
# FIX RENDER: SESSION_ENGINE trocado de "cache" para "db".
#
# Com "cache" + LocMemCache cada worker Gunicorn tem a sua própria memória;
# a sessão criada no worker A não existe no worker B → logout automático.
# Com "db" as sessões ficam no PostgreSQL (Supabase), partilhadas por todos
# os workers e persistentes entre reinícios do serviço.
SESSION_ENGINE             = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE         = 1800
SESSION_COOKIE_NAME        = 'osm_sid'
SESSION_COOKIE_HTTPONLY    = True
SESSION_COOKIE_SAMESITE    = 'Lax'
SESSION_COOKIE_SECURE      = True   # True em produção HTTPS
SESSION_SAVE_EVERY_REQUEST = True
SESSION_SERIALIZER         = 'django.contrib.sessions.serializers.JSONSerializer'

# FIX RENDER: Django está atrás de proxy HTTPS — ler header X-Forwarded-Proto
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ── AUTH ───────────────────────────────────────────────────────────────
AUTH_USER_MODEL     = 'osm.Utilizador'
LOGIN_URL           = '/'
LOGIN_REDIRECT_URL  = '/painel/'
LOGOUT_REDIRECT_URL = '/'

# Backend explícito — resolve auth em produção com modelo customizado
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 6}},
]

# ── CSRF ───────────────────────────────────────────────────────────────
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE   = not DEBUG

# ── EMAIL ──────────────────────────────────────────────────────────────
# Configuração dinâmica: variáveis de ambiente têm prioridade sobre o modelo
_EMAIL_USER = os.environ.get('EMAIL_SMTP_USER', '')
_EMAIL_PASS = os.environ.get('EMAIL_SMTP_PASS', '')

if _EMAIL_USER and _EMAIL_PASS:
    EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST          = os.environ.get('EMAIL_SMTP_HOST', 'smtp.gmail.com')
    EMAIL_PORT          = int(os.environ.get('EMAIL_SMTP_PORT', '587'))
    EMAIL_USE_TLS       = os.environ.get('EMAIL_SMTP_TLS', 'True') == 'True'
    EMAIL_HOST_USER     = _EMAIL_USER
    EMAIL_HOST_PASSWORD = _EMAIL_PASS
    DEFAULT_FROM_EMAIL  = f'OSM Microcrédito <{_EMAIL_USER}>'
else:
    # Dev fallback: imprime emails na consola
    EMAIL_BACKEND      = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = 'OSM Microcrédito <noreply@osm.co.mz>'

# BulkSMS API (alternativa ao token guardado no modelo ConfiguracaoBancaria)
BULKSMS_API_TOKEN = os.environ.get('BULKSMS_API_TOKEN', 'bWtfYWU2NmQyZGVjZDY4ZDFjY2E1ZGNjZmQ0ZTM0NjJkNTQ6NDE3MTpza18zYjY3YTQ1MjllMjkxNjJlNmMyYmI5ZTdhNWJmNjQyY2ViMmYyOGZhZGZmNTViMjU0YmQ4MGEzNjhlNjRkMzBh')
BULKSMS_SENDER    = os.environ.get('BULKSMS_SENDER', 'OSM')

# ── MOZESMS API ──────────────────────────────────────────────────────────
MOZESMS_BEARER_TOKEN = os.environ.get('MOZESMS_BEARER_TOKEN', 'bWtfYWU2NmQyZGVjZDY4ZDFjY2E1ZGNjZmQ0ZTM0NjJkNTQ6NDE3MTpza18zYjY3YTQ1MjllMjkxNjJlNmMyYmI5ZTdhNWJmNjQyY2ViMmYyOGZhZGZmNTViMjU0YmQ4MGEzNjhlNjRkMzBh')
MOZESMS_SENDER_ID    = os.environ.get('MOZESMS_SENDER_ID', 'MOZOTP')
MOZESMS_API_BASE     = os.environ.get('MOZESMS_API_BASE', 'https://api.mozesms.com')

# ── FICHEIROS ESTÁTICOS — WHITENOISE ──────────────────────────────────
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'      # destino do collectstatic

STATICFILES_DIRS = [
    BASE_DIR / 'static',                     # pasta static/ na raiz
]

# WhiteNoise: gzip + headers de cache de longa duração para ficheiros com hash
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── LOCALIZAÇÃO ────────────────────────────────────────────────────────
LANGUAGE_CODE = 'pt-pt'
TIME_ZONE     = 'Africa/Maputo'
USE_I18N      = True
USE_TZ        = True
USE_L10N      = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── CONSTANTES OSM ─────────────────────────────────────────────────────
OSM_NOME   = 'Office Semente Microcrédito, E.I.'
OSM_NUIT   = '150493129'
OSM_MORADA = 'EN6 Bairro Centro Hípico, Chimoio, Moçambique'
OSM_TEL    = '+258 87 20 31 215'
OSM_EMAIL  = 'officebernardo@gmail.com'

# ── SEGURANÇA PRODUÇÃO ─────────────────────────────────────────────────
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER       = True
    SECURE_CONTENT_TYPE_NOSNIFF     = True
    X_FRAME_OPTIONS                 = 'SAMEORIGIN'
    SECURE_HSTS_SECONDS             = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS  = True
    SECURE_HSTS_PRELOAD             = True
    # FIX: NÃO usar SECURE_SSL_REDIRECT no Render/Nginx — causa redirect loop
    # O proxy já garante HTTPS; usar SECURE_PROXY_SSL_HEADER em vez disso
    SECURE_SSL_REDIRECT             = False

# ── LOGGING ────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'root':    {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'osm':    {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'django': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
    },
}

# ── RENDER / GUNICORN ──────────────────────────────────────────────────
# Build command (Render Dashboard → Settings → Build Command):
#   pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
#
# Start command:
#   gunicorn core.wsgi:application --workers=2 --threads=4 --timeout=120 --log-file=-
#
# Variáveis de ambiente no Render:
#   SECRET_KEY  = (gerar com: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
#   DEBUG       = False
#   ALLOWED_HOSTS = (deixar em branco — RENDER_EXTERNAL_HOSTNAME é usado automaticamente)