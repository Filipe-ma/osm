# context_processors.py
from django.core.cache import cache
from .models import Emprestimo, SolicitacaoPublica, ConfiguracaoBancaria
from django.apps import apps

def osm_global(request):
    """Dados globais injectados em todos os templates com cache optimizado."""
    if not request.user.is_authenticated:
        return {}

    # Chave de cache por user (inclui permissões)
    cache_key = f'osm_ctx_{request.user.pk}'
    ctx = cache.get(cache_key)
    if ctx is not None:
        return ctx

    # Inicializa contexto vazio
    ctx = {}

    # 1. Contagens de empréstimos (apenas activos)
    ctx['pendentes_count'] = Emprestimo.active_objects.filter(status='pendente').count()
    ctx['atraso_count'] = Emprestimo.active_objects.filter(
        status__in=['vencido', 'incumprimento']
    ).count()

    # 2. Solicitações pendentes (só para quem tem permissão)
    pode_ver_solicitacoes = (
        request.user.is_superuser or
        getattr(request.user, 'perfil', '') in ('superadmin', 'gestor') or
        getattr(request.user, 'perm_solicitacoes', False)
    )
    if pode_ver_solicitacoes:
        ctx['total_solicitacoes_pendentes'] = SolicitacaoPublica.active_objects.filter(
            status__in=['submetido', 'em_analise']
        ).count()
    else:
        ctx['total_solicitacoes_pendentes'] = 0

    # 3. Dados da licença (apenas superadmin)
    if request.user.is_superuser or getattr(request.user, 'eh_superadmin', False):
        try:
            LicencaSistema = apps.get_model('osm', 'LicencaSistema')  # ou importar directamente
            lic = LicencaSistema.objects.order_by('-data_emissao').first()
            if lic:
                lic.actualizar_estado()
                ctx.update({
                    'licenca_estado': lic.estado,
                    'licenca_dias_restantes': lic.dias_restantes,
                    'licenca_expiracao': lic.data_expiracao.strftime('%d/%m/%Y'),
                })
        except (ImportError, AttributeError, Exception):
            # Falha silenciosa sem comprometer o resto
            pass

    # 4. Configuração bancária (opcional, útil para footers)
    conf = ConfiguracaoBancaria.obter()
    ctx.update({
        'empresa_nome': conf.titular,
        'empresa_nib': conf.nib,
        'empresa_telefone': conf.telefone,
        'empresa_email': ConfiguracaoBancaria.obter().email_smtp_user,  # ou campo próprio
    })

    # Cache por 5 minutos (300 segundos)
    cache.set(cache_key, ctx, 300)
    return ctx