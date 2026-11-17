"""
OSM Microcrédito v6 — Middleware
• ForcarTrocaSenha
• RegistarActividade
• Licença
• CodigoSuperAdmin
• RateLimitLoginMiddleware ← NOVO: bloqueia IPs após 10 tentativas falhadas
"""
from django.shortcuts import redirect, render
from django.urls import reverse
from django.core.cache import cache
from .models import LogActividade

ROTAS_LIVRES = [
    '/login/', '/logout/', '/trocar-senha/', '/static/', '/media/',
    '/', '/sobre/', '/solucoes/', '/contacto/',
    '/solicitar/', '/solicitar/sucesso/',
    '/sw.js', '/manifest.json', '/offline.html',
    '/verificar-codigo-admin/',
]

ROTAS_LICENCA = [
    '/licenca/', '/licenca/renovar/', '/licenca/pausar/',
    '/admin/',
]

# ─── Configurações de Rate Limit ────────────────────────────────────────────
MAX_TENTATIVAS_LOGIN = 10
BLOQUEIO_SEGUNDOS    = 30 * 60   # 30 minutos
JANELA_SEGUNDOS      = 15 * 60   # janela de contagem


def _key_attempts(ip):
    return f'login_attempts:{ip}'

def _key_blocked(ip):
    return f'ip_bloqueado:{ip}'


def incrementar_tentativa_login(ip):
    """Incrementa contador. Retorna (total, bloqueado)."""
    key_a = _key_attempts(ip)
    key_b = _key_blocked(ip)
    tentativas = (cache.get(key_a) or 0) + 1
    cache.set(key_a, tentativas, JANELA_SEGUNDOS)
    if tentativas >= MAX_TENTATIVAS_LOGIN:
        cache.set(key_b, True, BLOQUEIO_SEGUNDOS)
        return tentativas, True
    return tentativas, False


def resetar_tentativas_login(ip):
    """Chama após login bem-sucedido."""
    cache.delete(_key_attempts(ip))
    cache.delete(_key_blocked(ip))


def ip_esta_bloqueado(ip):
    return bool(cache.get(_key_blocked(ip)))


def tentativas_restantes(ip):
    feitas = cache.get(_key_attempts(ip)) or 0
    return max(0, MAX_TENTATIVAS_LOGIN - feitas)


# ─── Middleware Rate Limit Login ────────────────────────────────────────────
class RateLimitLoginMiddleware:
    """
    Bloqueia IPs após MAX_TENTATIVAS_LOGIN tentativas falhadas de login.
    Actua apenas em POST /login/.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/login/' and request.method == 'POST':
            ip = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                  or request.META.get('REMOTE_ADDR', ''))
            if ip_esta_bloqueado(ip):
                return render(request, 'osm/auth/ip_bloqueado.html', {
                    'minutos': BLOQUEIO_SEGUNDOS // 60,
                    'max_tentativas': MAX_TENTATIVAS_LOGIN,
                }, status=429)
        return self.get_response(request)


# ─── Middleware Força Troca Senha ───────────────────────────────────────────
class ForcarTrocaSenhaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if getattr(request.user, 'deve_trocar_senha', False):
                path  = request.path
                livre = any(path.startswith(r) for r in ROTAS_LIVRES)
                if not livre and path != reverse('trocar_senha'):
                    return redirect('trocar_senha')
        return self.get_response(request)


# ─── Middleware Registo Actividade ──────────────────────────────────────────
class RegistarActividadeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code in (403, 404, 500) and request.user.is_authenticated:
            LogActividade.registar(
                f'http_{response.status_code}',
                f'{response.status_code} em {request.path}',
                utilizador=request.user, request=request
            )
        return response


# ─── Middleware Licença ─────────────────────────────────────────────────────
class LicencaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        always_free = ROTAS_LIVRES + ROTAS_LICENCA
        if any(path.startswith(r) for r in always_free):
            return self.get_response(request)

        if request.user.is_authenticated:
            try:
                from .models import LicencaSistema
                lic = LicencaSistema.objects.order_by('-data_emissao').first()
                if lic:
                    lic.actualizar_estado()
                    if lic.bloqueada:
                        if getattr(request.user, 'eh_superadmin', False) or request.user.is_superuser:
                            return redirect('licenca_painel')
                        return render(request, 'osm/admin/licenca_bloqueada.html',
                                      {'lic': lic}, status=503)
            except Exception:
                pass

        return self.get_response(request)


# ─── Middleware Código SuperAdmin ───────────────────────────────────────────
class CodigoSuperAdminMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (request.user.is_authenticated and
                getattr(request.user, 'eh_superadmin', False) and
                request.path.startswith('/licenca/') and
                not request.path.startswith('/verificar-codigo-admin/')):
            if not request.session.get('codigo_superadmin_ok'):
                return redirect('verificar_codigo_admin')
        return self.get_response(request)
