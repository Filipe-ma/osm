"""
OSM Microcrédito v5.0 — Views Completas (adaptadas para modelos com Credito)
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Sum, Count, Q, Avg
from django.core.paginator import Paginator
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.cache import cache_page, never_cache
from datetime import date, timedelta
from decimal import Decimal
import json, logging
import requests
from .models import Emprestimo, Utilizador, Credito
from .services import calcular_kpis, calcular_relatorio_periodo
from .pdf_utils import (
    gerar_contrato, gerar_ficha_gestor, gerar_ficha_cliente,
    gerar_declaracao, gerar_recibo, gerar_fatura,
    gerar_fatura_dupla, gerar_recibo_comerciante,
    gerar_recibo_pos, gerar_fatura_turbohost
)
from .sms import enviar_sms_mozesms
from .models import (
    Utilizador, Emprestimo, Pagamento, Comerciante, PagamentoDiario,
    LogActividade, LogSMS, ConfiguracaoBancaria, FotoGarantia,
    RequisicaoCliente, LancamentoPagamento, SolicitacaoPublica,
    LicencaSistema, gerar_username, gerar_senha, Credito
)
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime

logger = logging.getLogger('osm')


def _invalidar_cache_painel():
    """Invalida o cache do painel após alterações de dados."""
    cache.delete('painel_kpis')
    cache.delete('painel_sectores')
    cache.delete('painel_scores')
    cache.delete('kpis_dashboard')
    cache.delete('sectores_breakdown')


# =============================================================================
# HELPERS E DECORADORES (inalterados)
# =============================================================================
def get_ip(request):
    return (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', ''))

def log(tipo, desc, detalhe='', request=None):
    u = request.user if request and request.user.is_authenticated else None
    LogActividade.registar(tipo, desc, detalhe, u, request)

def requer_perfil(*perfis):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not (request.user.perfil in perfis or request.user.is_superuser):
                messages.error(request, '⛔ Sem permissão para aceder a esta área.')
                return redirect('painel')
            return view_func(request, *args, **kwargs)
        wrapper.__name__ = view_func.__name__
        return wrapper
    return decorator

def _enviar_sms_real(telefone, mensagem, nome, contrato, utilizador):
    if not telefone:
        return False, "Telefone vazio"
    cfg = ConfiguracaoBancaria.obter()
    tem_moze = bool(getattr(settings, 'MOZESMS_BEARER_TOKEN', None))
    status = ''
    ok = False
    detalhe = ''
    if tem_moze:
        ok, detalhe = enviar_sms_mozesms(telefone, mensagem)
        status = 'enviado' if ok else f'erro:{detalhe[:50]}'
    elif cfg.bulksms_api_token:
        ok, detalhe = enviar_sms_bulksms(telefone, mensagem, cfg)
        status = 'enviado' if ok else f'erro:{detalhe[:50]}'
    else:
        status = 'simulado'
        ok = True
        detalhe = 'modo simulação'
    LogSMS.objects.create(
        nome=nome, telefone=telefone, mensagem=mensagem[:500],
        status=status, numero_contrato=contrato, enviado_por=utilizador,
    )
    return ok, detalhe

def _sms_template(tipo, contexto):
    nome     = contexto.get('nome', '')
    contrato = contexto.get('contrato', '')
    valor    = contexto.get('valor', '')
    parcela  = contexto.get('parcela', '')
    periodo  = contexto.get('periodo', '')
    total    = contexto.get('total', '')
    saldo    = contexto.get('saldo', '')
    dias     = contexto.get('dias', '')
    templates = {
        'pendente': (f'OSM Microcredito — {nome}, o seu pedido de credito {contrato} no valor de MT {valor} foi REGISTADO e esta em analise. Aguardamos aprovacao. cel/emola: 258872031215'),
        'aprovado': (f'OSM Microcredito — {nome}, o seu credito {contrato} no valor de MT {valor} foi APROVADO! Compareça para assinar o contrato. cel/emola: 258872031215'),
        'rejeitado': (f'OSM Microcredito — {nome}, o seu pedido de credito nao foi aprovado desta vez. Para mais informacoes contacte: 258872031215'),
        'pagamento_confirmado': (f'OSM Microcredito — {nome}, pagamento de MT {valor} do contrato {contrato} CONFIRMADO! Saldo restante: MT {saldo}. Obrigado!'),
        'pagamento_parcial': (f'OSM Microcredito — {nome}, pagamento parcial de MT {valor} registado no contrato {contrato}. Saldo restante: MT {saldo}. Obrigado!'),
        'quitado': (f'OSM Microcredito — Parabens {nome}! Contrato {contrato} QUITADO. Total pago: MT {total}. Obrigado pela confianca!'),
        'atraso': (f'OSM Microcredito — {nome}, o contrato {contrato} tem {dias} dia(s) de atraso. Valor em divida: MT {valor}. Regularize urgentemente. cel/emola: 258872031215'),
        'urgente': (f'URGENTE — OSM Microcredito. {nome}, contrato {contrato} em incumprimento ha {dias} dias. Montante: MT {valor}. Contacte-nos IMEDIATAMENTE: 258872031215'),
        'juridico': (f'OSM Microcredito — {nome}, NOTIFICACAO FORMAL. Contrato {contrato} sera enviado para tribunal se nao regularizar MT {valor} em 48h. cel/emola: 258872031215'),
        'lembrete': (f'OSM Microcredito — {nome}, lembrete: parcela do contrato {contrato} vence em breve. Valor: MT {valor}. Evite juros de mora. cel/emola: 258872031215'),
        'comerciante_pagamento': (f'OSM Microcredito — {nome}, parcela {periodo} do contrato {contrato} confirmada! Valor: MT {parcela}. Total pago: MT {total}. Obrigado!'),
        'comerciante_atraso': (f'OSM Microcredito — {nome}, contrato {contrato} tem {dias} parcela(s) em atraso. Valor: MT {valor}. Regularize hoje. cel/emola: 258872031215'),
        'comerciante_criado': (f'OSM Microcredito — {nome}, o seu contrato de comerciante {contrato} foi registado com sucesso! Capital: MT {valor}. Modalidade: {periodo}. cel/emola: 258872031215'),
    }
    return templates.get(tipo, f'OSM Microcredito — {nome}, notificacao sobre contrato {contrato}.')

def _auto_sms_emprestimo(emp, tipo, utilizador):
    if not emp.telefone:
        return False, 'Sem telefone'
    saldo = emp.saldo_restante if emp.saldo_restante is not None else emp.total_com_multa
    ctx = {'nome': emp.nome, 'contrato': emp.numero_contrato, 'valor': f'{float(emp.total_com_multa):,.2f}', 'total': f'{float(emp.total_com_multa):,.2f}', 'saldo': f'{float(saldo or 0):,.2f}', 'dias': str(emp.dias_atraso)}
    msg = _sms_template(tipo, ctx)
    return _enviar_sms_real(emp.telefone, msg, emp.nome, emp.numero_contrato, utilizador)

def _auto_sms_comerciante(com, tipo, utilizador):
    if not com.telefone:
        return False, 'Sem telefone'
    ctx = {'nome': com.nome, 'contrato': com.numero_contrato, 'parcela': f'{float(com.parcela_atual):,.2f}', 'periodo': f'{com.periodos_pagos}/{com.total_periodos}', 'total': f'{float(com.total_pago):,.2f}', 'valor': f'{float(com.total_em_atraso):,.2f}', 'dias': str(com.periodos_em_atraso)}
    msg = _sms_template(tipo, ctx)
    return _enviar_sms_real(com.telefone, msg, com.nome, com.numero_contrato, utilizador)

def enviar_sms_log(nome, telefone, mensagem, status, contrato, utilizador=None):
    LogSMS.objects.create(nome=nome, telefone=telefone, mensagem=mensagem, status=status, numero_contrato=contrato, enviado_por=utilizador)

def enviar_sms_bulksms(telefone, mensagem, cfg=None):
    import urllib.request, urllib.error
    import json as _json
    if cfg is None:
        cfg = ConfiguracaoBancaria.obter()
    api_token = cfg.bulksms_api_token.strip() if cfg.bulksms_api_token else ''
    if not api_token:
        return False, 'API token não configurado'
    tel = telefone.strip().replace(' ', '').replace('-', '')
    if tel.startswith('0'):
        tel = '+258' + tel[1:]
    elif not tel.startswith('+'):
        tel = '+258' + tel
    sender = (cfg.bulksms_sender or 'OSM').strip()[:11]
    payload = _json.dumps({'to': tel, 'body': mensagem, 'from': sender, 'routingGroup': 'STANDARD', 'encoding': 'TEXT'}).encode('utf-8')
    try:
        import base64
        credentials = base64.b64encode(f':{api_token}'.encode()).decode()
        req = urllib.request.Request('https://api.bulksms.com/v1/messages', data=payload, headers={'Content-Type': 'application/json', 'Authorization': f'Basic {credentials}'}, method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8')
            data = _json.loads(body)
            msg_id = data[0].get('id', '?') if isinstance(data, list) else data.get('id', '?')
            return True, f'id={msg_id}'
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return False, f'HTTP {e.code}: {body[:200]}'
    except Exception as e:
        return False, str(e)

def enviar_cobranca_email(emprestimo, tipo='atraso', request=None):
    from django.template.loader import render_to_string
    from django.core.mail import EmailMessage
    cfg = ConfiguracaoBancaria.obter()
    if not cfg.email_ativo:
        return False, 'Email não activado nas configurações'
    if not emprestimo.cliente or not emprestimo.cliente.email:
        return False, 'Cliente sem email'
    if cfg.email_smtp_user and cfg.email_smtp_pass:
        from django.core.mail.backends.smtp import EmailBackend
        backend = EmailBackend(host=cfg.email_smtp_host or 'smtp.gmail.com', port=cfg.email_smtp_port or 587, username=cfg.email_smtp_user, password=cfg.email_smtp_pass, use_tls=cfg.email_smtp_tls, fail_silently=False)
    else:
        backend = None
    subtitulos = {'atraso': 'Parcela em atraso — regularize urgentemente', 'urgente': 'Acção imediata necessária', 'juridico': 'Notificação formal de incumprimento', 'lembrete': 'Lembrete de pagamento próximo', 'aprovacao': 'O seu crédito foi aprovado', 'boas_vindas': 'Bem-vindo à OSM Microcrédito', 'quitacao': 'Parabéns — contrato liquidado'}
    assuntos = {'atraso': f'[OSM] ⚠ Aviso de Cobrança — {emprestimo.numero_contrato}', 'urgente': f'[OSM] 🔴 URGENTE — {emprestimo.numero_contrato}', 'juridico': f'[OSM] ⚖ Aviso Legal — {emprestimo.numero_contrato}', 'lembrete': f'[OSM] 🔔 Lembrete de Pagamento — {emprestimo.numero_contrato}', 'aprovacao': f'[OSM] ✅ Crédito Aprovado — {emprestimo.numero_contrato}', 'boas_vindas': f'[OSM] 🎉 Bem-vindo — {emprestimo.numero_contrato}', 'quitacao': f'[OSM] 🏆 Contrato Quitado — {emprestimo.numero_contrato}'}
    context = {'emprestimo': emprestimo, 'banco': cfg, 'tipo': tipo, 'assunto': assuntos.get(tipo, f'[OSM] Notificação — {emprestimo.numero_contrato}'), 'subtitulo': subtitulos.get(tipo, ''), 'hoje': timezone.localdate().strftime('%d/%m/%Y'), 'ano': timezone.localdate().year, 'portal_url': ''}
    try:
        html_body = render_to_string('emails/cobranca_email.html', context)
        email = EmailMessage(subject=assuntos.get(tipo, f'[OSM] Notificação — {emprestimo.numero_contrato}'), body=html_body, from_email=f'OSM Microcrédito <{cfg.email_smtp_user or "noreply@osm.co.mz"}>', to=[emprestimo.cliente.email], connection=backend)
        email.content_subtype = 'html'
        email.send()
        return True, f'Email enviado para {emprestimo.cliente.email}'
    except Exception as e:
        return False, str(e)

def enviar_email_credenciais(utilizador, senha_inicial):
    if not utilizador.email:
        return False
    try:
        send_mail(subject='OSM Microcrédito — As suas credenciais de acesso', message=f'Olá {utilizador.nome_completo},\n\nA sua conta foi criada na OSM Microcrédito.\n\nUsername: {utilizador.username}\nPassword: {senha_inicial}\n\nAceda em: https://osm.co.mz/login/\n\nNa primeira sessão será obrigatório trocar as suas credenciais.\n\nOSM Microcrédito', from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[utilizador.email], fail_silently=True)
        return True
    except Exception as e:
        logger.error(f'Erro ao enviar email: {e}')
        return False


# =============================================================================
# LANDING PAGE
# =============================================================================
@cache_page(300)
def view_landing(request):
    if request.user.is_authenticated:
        if request.user.perfil == 'cliente':
            return redirect('portal_cliente')
        return redirect('painel')
    return render(request, 'osm/sistema/landing.html')


# =============================================================================
# AUTENTICAÇÃO
# =============================================================================
@never_cache
def view_login(request):
    from .middleware import (incrementar_tentativa_login, resetar_tentativas_login, ip_esta_bloqueado, tentativas_restantes, MAX_TENTATIVAS_LOGIN, BLOQUEIO_SEGUNDOS)
    if request.user.is_authenticated:
        if request.user.perfil == 'cliente':
            return redirect('portal_cliente')
        return redirect('painel')
    erro = None
    restantes = None
    ip = get_ip(request)
    if ip_esta_bloqueado(ip):
        return render(request, 'osm/auth/ip_bloqueado.html', {'minutos': BLOQUEIO_SEGUNDOS // 60, 'max_tentativas': MAX_TENTATIVAS_LOGIN}, status=429)
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        senha    = request.POST.get('senha', '')
        user = authenticate(request, username=username, password=senha)
        if user and user.activo:
            resetar_tentativas_login(ip)
            login(request, user)
            user.ultimo_login_ip = ip
            user.save(update_fields=['ultimo_login_ip'])
            log('login', f'Login: {user.nome_completo}', user.email, request)
            if user.deve_trocar_senha:
                return redirect('trocar_senha')
            if user.perfil == 'cliente':
                return redirect('portal_cliente')
            return redirect('painel')
        else:
            total, bloqueado = incrementar_tentativa_login(ip)
            log('login_falhou', f'Tentativa falhada: {username}', f'IP:{ip}', request)
            if bloqueado:
                return render(request, 'osm/auth/ip_bloqueado.html', {'minutos': BLOQUEIO_SEGUNDOS // 60, 'max_tentativas': MAX_TENTATIVAS_LOGIN}, status=429)
            restantes = tentativas_restantes(ip)
            if restantes <= 3:
                erro = f'Username ou password incorrectos. Ainda tem {restantes} tentativa(s) antes do bloqueio.'
            else:
                erro = 'Username ou password incorrectos.'
    return render(request, 'osm/auth/login.html', {'erro': erro, 'restantes': restantes})

@login_required
@never_cache
def view_trocar_senha(request):
    if request.method == 'POST':
        novo_username = request.POST.get('novo_username', '').strip()
        nova_senha    = request.POST.get('nova_senha', '')
        confirmar     = request.POST.get('confirmar_senha', '')
        erros = []
        if len(novo_username) < 4:
            erros.append('Username deve ter pelo menos 4 caracteres.')
        if novo_username != request.user.username:
            if Utilizador.objects.filter(username=novo_username).exclude(pk=request.user.pk).exists():
                erros.append('Este username já está em uso.')
        if len(nova_senha) < 6:
            erros.append('A password deve ter pelo menos 6 caracteres.')
        if nova_senha != confirmar:
            erros.append('As passwords não coincidem.')
        if not erros:
            u = request.user
            u.username          = novo_username
            u.deve_trocar_senha = False
            u.senha_inicial     = ''
            u.set_password(nova_senha)
            u.save()
            update_session_auth_hash(request, u)
            log('trocar_senha', f'Senha trocada: {u.nome_completo}', '', request)
            messages.success(request, '✓ Credenciais actualizadas com sucesso!')
            if u.perfil == 'cliente':
                return redirect('portal_cliente')
            return redirect('painel')
        for e in erros:
            messages.error(request, e)
    return render(request, 'osm/auth/trocar_senha.html', {'username_atual': request.user.username})

@login_required
def view_logout(request):
    log('logout', 'Sessão terminada', request.user.email, request)
    logout(request)
    return redirect('landing')


# =============================================================================
# PAINEL PRINCIPAL (Gestor/Admin) – adaptado para Credito
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_painel(request):
    from decimal import Decimal
    from django.db.models import Sum, Count

    # Tenta usar KPIs em cache (TTL 3 min) para evitar N queries a cada refresh
    kpis_cached = cache.get('painel_kpis')
    sectores_cached = cache.get('painel_sectores')
    scores_cached = cache.get('painel_scores')

    if kpis_cached and sectores_cached and scores_cached:
        pendentes_recentes = Emprestimo.active_objects.filter(
            status='pendente', deleted_at__isnull=True
        ).select_related('registado_por', 'cliente').order_by('-data_registo')[:5]
        em_atraso_lista = Emprestimo.active_objects.filter(
            status__in=['vencido', 'incumprimento'], deleted_at__isnull=True
        ).select_related('cliente').order_by('data_vencimento')[:5]
        return render(request, 'osm/sistema/painel.html', {
            'kpis': kpis_cached,
            'sectores': sectores_cached,
            'scores': scores_cached,
            'total_emp': max(kpis_cached.get('emprestimos_ativos', 1), 1),
            'pendentes_recentes': pendentes_recentes,
            'em_atraso': em_atraso_lista,
        })

    # --------------------------------------------------------------
    # 1. Base de empréstimos activos (exclui quitados, rejeitados, deletados)
    # --------------------------------------------------------------
    qs_base = Emprestimo.active_objects.filter(
        deleted_at__isnull=True
    ).exclude(status__in=['quitado', 'rejeitado'])

    total_emp = qs_base.count()
    if total_emp == 0:
        total_emp = 1  # evita divisão por zero

    # --------------------------------------------------------------
    # 2. Carteira activa (soma dos créditos NÃO pagos)
    # --------------------------------------------------------------
    carteira = Credito.active_objects.filter(
        emprestimo__in=qs_base, pago=False
    ).aggregate(total=Sum('valor'))['total'] or Decimal('0')

    # --------------------------------------------------------------
    # 3. Empréstimos em atraso (vencido ou incumprimento)
    # --------------------------------------------------------------
    em_atraso_qs = qs_base.filter(status__in=['vencido', 'incumprimento'])
    em_atraso = em_atraso_qs.count()

    pendentes = qs_base.filter(status='pendente').count()
    quitados = Emprestimo.active_objects.filter(status='quitado').count()

    # --------------------------------------------------------------
    # 4. Clientes distintos com empréstimos activos (Contas Activas)
    # --------------------------------------------------------------
    clientes_ids = qs_base.values_list('cliente_id', flat=True).distinct()
    contas_ativas = clientes_ids.count()  # número de clientes com contratos activos

    # --------------------------------------------------------------
    # 5. Clientes normais e comerciantes (baseado no perfil do Utilizador)
    # --------------------------------------------------------------
    clientes_normais = Utilizador.objects.filter(
        id__in=clientes_ids, tipo_cliente='normal'
    ).count()

    comerciantes_ativos = Utilizador.objects.filter(
        id__in=clientes_ids, tipo_cliente='comerciante'
    ).count()

    # --------------------------------------------------------------
    # 6. Juros total do mês e mora acumulada (calculados a partir dos Créditos)
    # --------------------------------------------------------------
    juros_total = Decimal('0')
    mora_total = Decimal('0')

    creditos = Credito.active_objects.filter(emprestimo__in=qs_base)
    for cred in creditos:
        juros_total += cred.valor * (cred.taxa_juros / Decimal('100'))
        if cred.em_incumprimento or cred.esta_vencido:
            mora_total += cred.mora_composta

    # --------------------------------------------------------------
    # 7. Funcionários e Gestores (baseado no perfil do Utilizador)
    # --------------------------------------------------------------
    total_funcionarios = Utilizador.objects.filter(
        perfil='gestor', is_active=True, deleted_at__isnull=True
    ).count()
    total_gestores = Utilizador.objects.filter(
        perfil__in=['superadmin', 'gestor'], is_active=True, deleted_at__isnull=True
    ).count()

    # --------------------------------------------------------------
    # 8. Dicionário de KPIs (agora com todos os campos do template)
    # --------------------------------------------------------------
    kpis = {
        'carteira': float(carteira),
        'emprestimos_ativos': total_emp,
        'em_atraso': em_atraso,
        'pct_atraso': round((em_atraso / max(total_emp, 1)) * 100, 1),
        'total_contratos': total_emp + quitados,
        'quitados': quitados,
        'pendentes': pendentes,
        'juros_total_mes': float(juros_total),
        'mora_total': float(mora_total),
        'total_clientes_normais': clientes_normais,
        'total_comerciantes_cli': comerciantes_ativos,
        'taxa_juros_padrao': 30,
        'taxa_multa_padrao': 2,
        'total_funcionarios': total_funcionarios,
        'total_gestores': total_gestores,
        'contas_ativas': contas_ativas,          # ← ADICIONADO
    }

    # --------------------------------------------------------------
    # 9. Dados para gráficos
    # --------------------------------------------------------------
    sectores = list(qs_base.values('sector').annotate(total=Count('id')).order_by('-total'))
    scores = list(qs_base.values('score').annotate(total=Count('id')).order_by('score'))

    # Guarda em cache por 3 minutos
    cache.set('painel_kpis', kpis, 180)
    cache.set('painel_sectores', sectores, 180)
    cache.set('painel_scores', scores, 180)
    cache.set('sectores_breakdown', sectores, 300)

    # --------------------------------------------------------------
    # 10. Listas recentes com select_related
    # --------------------------------------------------------------
    pendentes_recentes = qs_base.filter(status='pendente') \
                                .select_related('registado_por', 'cliente') \
                                .order_by('-data_registo')[:5]

    em_atraso_lista = em_atraso_qs.select_related('cliente') \
                                  .order_by('data_vencimento')[:5]

    # --------------------------------------------------------------
    # 11. Renderização
    # --------------------------------------------------------------
    return render(request, 'osm/sistema/painel.html', {
        'kpis': kpis,
        'sectores': sectores,
        'scores': scores,
        'total_emp': max(total_emp, 1),
        'pendentes_recentes': pendentes_recentes,
        'em_atraso': em_atraso_lista,
    })

@login_required
@requer_perfil('superadmin', 'gestor')
def view_emprestimos(request):
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    sector = request.GET.get('sector', '')
    score = request.GET.get('score', '')

    # Query base: apenas activos (soft delete) com relacionamentos
    qs = Emprestimo.active_objects.select_related(
        'registado_por', 'aprovado_por', 'cliente'
    ).prefetch_related('creditos')

    # Filtros
    if q:
        qs = qs.filter(
            Q(nome__icontains=q) |
            Q(numero_contrato__icontains=q) |
            Q(telefone__icontains=q) |
            Q(nuit__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if sector:
        qs = qs.filter(sector=sector)
    if score:
        qs = qs.filter(score=score)

    # Anotações sobre créditos do próprio empréstimo
    qs = qs.annotate(
        total_creditos=Count('creditos', filter=Q(creditos__deleted_at__isnull=True)),
        num_creditos_ativos=Count('creditos', filter=Q(creditos__deleted_at__isnull=True, creditos__pago=False)),
        num_creditos_quitados=Count('creditos', filter=Q(creditos__deleted_at__isnull=True, creditos__pago=True))
    )

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    # --- Estatísticas por cliente (apenas empréstimos com cliente) ---
    stats_por_cliente = (
        Emprestimo.active_objects
        .filter(cliente__isnull=False)
        .values('cliente_id')
        .annotate(
            total=Count('id'),
            em_divida=Count('id', filter=~Q(status='quitado')),
            quitados=Count('id', filter=Q(status='quitado'))
        )
    )
    stats_dict = {
        item['cliente_id']: (item['total'], item['em_divida'], item['quitados'])
        for item in stats_por_cliente
    }

    # Atribuir as estatísticas a cada empréstimo da página
    for emprestimo in page:
        cid = emprestimo.cliente_id
        if cid and cid in stats_dict:
            total_emp, divida_emp, quitados_emp = stats_dict[cid]
        else:
            # Empréstimo sem cliente associado: conta apenas ele mesmo
            total_emp = 1
            if emprestimo.status == 'quitado' or emprestimo.esta_quitado:
                quitados_emp = 1
                divida_emp = 0
            else:
                quitados_emp = 0
                divida_emp = 1
        emprestimo.cliente_total_emp = total_emp
        emprestimo.cliente_divida_emp = divida_emp
        emprestimo.cliente_quitados_emp = quitados_emp

    context = {
        'page': page,
        'q': q,
        'status': status,
        'sector': sector,
        'score': score,
        'pendentes': Emprestimo.active_objects.filter(status='pendente').count(),
        'STATUS_CHOICES': Emprestimo.STATUS_CHOICES,
        'SECTOR_CHOICES': Emprestimo.SECTOR_CHOICES,
        'SCORE_CHOICES': Emprestimo.SCORE_CHOICES,
    }
    return render(request, 'osm/emprestimos/emprestimos.html', context)


@login_required
@requer_perfil('superadmin', 'gestor')
def view_creditos_cliente(request, pk):
    # Obtém o empréstimo com os relacionamentos necessários e com prefetch dos créditos
    emp = get_object_or_404(
        Emprestimo.objects
        .select_related('cliente', 'registado_por', 'aprovado_por')
        .prefetch_related('creditos'),  # <-- evita N+1
        pk=pk
    )
    
    # ---- CRÉDITOS (activos e quitados) ----
    creditos = emp.creditos.filter(deleted_at__isnull=True).order_by('-data_inicio')
    creditos_activos = [c for c in creditos if not c.esta_quitado]
    creditos_quitados = [c for c in creditos if c.esta_quitado]
    
    # ---- DEMAIS DADOS (mantidos da sua view original) ----
    ultimo_pagamento = Pagamento.objects.filter(credito__emprestimo=emp).order_by('-data_pagamento').first()
    lancamentos_validados = emp.lancamentos.filter(status='validado').select_related('submetido_por', 'validado_por').order_by('-data_pagamento')
    lancamentos_pendentes = emp.lancamentos.filter(status='pendente').count()
    
    clientes_sem_emprestimo = []
    if not emp.cliente:
        clientes_sem_emprestimo = list(Utilizador.objects.filter(perfil='cliente', activo=True).order_by('first_name', 'last_name'))
    
    # ---- CONTEXTO (incluindo os novos campos) ----
    context = {
        'emp': emp,
        'creditos_activos': creditos_activos,
        'creditos_quitados': creditos_quitados,
        'total_creditos': len(creditos),
        'ultimo_pagamento': ultimo_pagamento,
        'lancamentos_validados': lancamentos_validados,
        'lancamentos_pendentes': lancamentos_pendentes,
        'saldo_atual': emp.saldo_restante if emp.saldo_restante is not None else emp.total_com_multa,
        'mora_atual': emp.mora_composta,
        'total_devido': emp.total_com_multa,
        'clientes_sem_emprestimo': clientes_sem_emprestimo,
    }
    return render(request, 'osm/creditos/creditos_cliente.html', context)

#--

@login_required
@requer_perfil('superadmin', 'gestor')
def view_emprestimo_novo(request):
    if request.method == 'POST':
        return _gravar_emprestimo(request, None)
    b = ConfiguracaoBancaria.obter()
    return render(request, 'osm/emprestimos/emprestimo_form.html', {'editar': False, 'banco': b})

@login_required
@requer_perfil('superadmin', 'gestor')
def view_emprestimo_editar(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    if request.method == 'POST':
        return _gravar_emprestimo(request, emp)
    b = ConfiguracaoBancaria.obter()
    return render(request, 'osm/emprestimos/emprestimo_form.html', {'emp': emp, 'editar': True, 'banco': b})

def _gravar_emprestimo(request, emp):
    p = request.POST
    try:
        valor = Decimal(p.get('valor', '0') or '0')
    except Exception:
        valor = Decimal('0')
    nome = p.get('nome', '').strip()
    if not nome or not valor:
        messages.error(request, 'Nome e valor são obrigatórios.')
        return redirect(request.path)
    cfg = ConfiguracaoBancaria.obter()
    taxa_j  = cfg.taxa_juros_padrao
    taxa_m  = cfg.taxa_multa_padrao
    prazo_m = cfg.prazo_multa_dias
    if request.user.eh_superadmin:
        try:
            taxa_j  = Decimal(p.get('taxa_juros', '') or str(cfg.taxa_juros_padrao))
            taxa_m  = Decimal(p.get('taxa_multa', '') or str(cfg.taxa_multa_padrao))
            prazo_m = int(p.get('prazo_multa_dias', '') or cfg.prazo_multa_dias)
        except Exception:
            pass
    dados = {
        'nome': nome, 'nuit': p.get('nuit', '').strip(), 'bi': p.get('bi', '').strip(),
        'telefone': p.get('telefone', '').strip(), 'sector': p.get('sector', 'Comercio'),
        'score': p.get('score', 'A'), 'finalidade': p.get('finalidade', '').strip(),
        'garantia': p.get('garantia', '').strip(), 'estado_civil': p.get('estado_civil', '').strip(),
        'bairro': p.get('bairro', '').strip(), 'empregador': p.get('empregador', '').strip(),
        'nome_pai': p.get('nome_pai', '').strip(), 'nome_mae': p.get('nome_mae', '').strip(),
        'distrito': p.get('distrito', 'Chimoio'), 'provincia': p.get('provincia', 'Manica'),
        'local_emissao_bi': p.get('local_emissao_bi', 'Chimoio'), 'data_emissao_bi': p.get('data_emissao_bi') or None,
        'tipo_cliente': p.get('tipo_cliente', 'normal'),
    }
    if emp is None:
        u = request.user
        status = 'ativo' if u.pode_aprovar else 'pendente'
        if u.limite_emprestimo > 0 and valor > u.limite_emprestimo:
            messages.error(request, f'Valor excede o seu limite de MT {u.limite_emprestimo:,.2f}.')
            return redirect(request.path)
        emp = Emprestimo(registado_por=u, status=status, **dados)
        emp.save()
        Credito.objects.create(emprestimo=emp, valor=valor, taxa_juros=taxa_j, taxa_multa=taxa_m, prazo_multa_dias=prazo_m, data_inicio=emp.data_inicio, data_vencimento=emp.data_vencimento)
        for foto in request.FILES.getlist('fotos_garantia'):
            FotoGarantia.objects.create(emprestimo=emp, foto=foto)
        emp.refresh_from_db()
        if emp.telefone:
            tipo_sms = 'pendente' if status == 'pendente' else 'aprovado'
            _auto_sms_emprestimo(emp, tipo_sms, request.user)
        log('novo_emprestimo', f'Novo: {emp.nome}', f'{emp.numero_contrato} MT {float(valor):,.0f}', request)
        _invalidar_cache_painel()
        messages.success(request, f'✓ Empréstimo {emp.numero_contrato} registado!')
    else:
        for k, v in dados.items():
            setattr(emp, k, v)
        emp.save()
        cred = emp.creditos_activos.first()
        if cred:
            cred.taxa_juros = taxa_j
            cred.taxa_multa = taxa_m
            cred.prazo_multa_dias = prazo_m
            cred.save(update_fields=['taxa_juros', 'taxa_multa', 'prazo_multa_dias'])
        for foto in request.FILES.getlist('fotos_garantia'):
            FotoGarantia.objects.create(emprestimo=emp, foto=foto)
        log('editar_emprestimo', f'Editado: {emp.nome}', emp.numero_contrato, request)
        _invalidar_cache_painel()
        messages.success(request, '✓ Alterações guardadas.')
    return redirect('emprestimos')

@login_required
@requer_perfil('superadmin', 'gestor')
def view_emprestimo_detalhe(request, pk):
    # Obtém o empréstimo com os relacionamentos necessários e com prefetch dos créditos
    emp = get_object_or_404(
        Emprestimo.objects
        .select_related('cliente', 'registado_por', 'aprovado_por')
        .prefetch_related('creditos'),  # <-- evita N+1
        pk=pk
    )
    
    # ---- CRÉDITOS (activos e quitados) ----
    creditos = emp.creditos.filter(deleted_at__isnull=True).order_by('-data_inicio')
    creditos_activos = [c for c in creditos if not c.esta_quitado]
    creditos_quitados = [c for c in creditos if c.esta_quitado]

    # Suporte a ?credito=<pk> para pré-seleccionar o tab do crédito correcto
    credito_sel_pk = request.GET.get('credito')
    credito_sel_idx = 0  # default: primeiro
    if credito_sel_pk:
        try:
            credito_sel_pk = int(credito_sel_pk)
            for i, c in enumerate(creditos_activos):
                if c.pk == credito_sel_pk:
                    credito_sel_idx = i
                    break
        except (ValueError, TypeError):
            pass
    
    # ---- DEMAIS DADOS (mantidos da sua view original) ----
    ultimo_pagamento = Pagamento.objects.filter(credito__emprestimo=emp).order_by('-data_pagamento').first()
    lancamentos_validados = emp.lancamentos.filter(status='validado').select_related('submetido_por', 'validado_por').order_by('-data_pagamento')
    lancamentos_pendentes = emp.lancamentos.filter(status='pendente').count()
    
    clientes_sem_emprestimo = []
    if not emp.cliente:
        clientes_sem_emprestimo = list(Utilizador.objects.filter(perfil='cliente', activo=True).order_by('first_name', 'last_name'))
    
    # ---- CONTEXTO (incluindo os novos campos) ----
    context = {
        'emp': emp,
        'creditos_activos': creditos_activos,
        'creditos_quitados': creditos_quitados,
        'total_creditos': len(creditos),
        'credito_sel_idx': credito_sel_idx,
        'ultimo_pagamento': ultimo_pagamento,
        'lancamentos_validados': lancamentos_validados,
        'lancamentos_pendentes': lancamentos_pendentes,
        'saldo_atual': emp.saldo_restante if emp.saldo_restante is not None else emp.total_com_multa,
        'mora_atual': emp.mora_composta,
        'total_devido': emp.total_com_multa,
        'clientes_sem_emprestimo': clientes_sem_emprestimo,
    }
    return render(request, 'osm/emprestimos/emprestimo_detalhe.html', context)

#--

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_emprestimo_eliminar(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    if not request.user.pode_eliminar:
        messages.error(request, '⛔ Sem permissão para eliminar.')
        return redirect('emprestimo_detalhe', pk=pk)
    nome, contrato = emp.nome, emp.numero_contrato
    emp.delete()
    log('eliminar_emprestimo', f'Eliminado: {nome}', contrato, request)
    messages.success(request, f'Empréstimo {contrato} eliminado.')
    return redirect('emprestimos')

@login_required
@require_POST
def view_registar_pagamento(request, pk):
    from django.db import transaction
    emp = get_object_or_404(Emprestimo, pk=pk)
    if not request.user.pode_aprovar:
        messages.error(request, "⛔ Apenas gestores podem registar pagamentos directos.")
        return redirect("emprestimo_detalhe", pk=pk)
    if emp.esta_quitado or emp.status == "quitado":
        messages.warning(request, "Este empréstimo já está quitado.")
        return redirect("emprestimo_detalhe", pk=pk)
    if emp.status in ("pendente", "rejeitado"):
        messages.error(request, "Não é possível quitar um empréstimo pendente ou rejeitado.")
        return redirect("emprestimo_detalhe", pk=pk)
    try:
        with transaction.atomic():
            credito = emp.creditos_activos.filter(pago=False).first()
            if not credito:
                messages.error(request, "Nenhum crédito activo encontrado.")
                return redirect("emprestimo_detalhe", pk=pk)
            credito.registar_pagamento_total(valor_pago=None, registado_por=request.user, metodo='dinheiro', referencia='Quitação directa', observacoes=(f"Quitação em {timezone.localdate()} — {emp.dias_atraso}d atraso" if emp.dias_atraso else "Quitação no prazo"))
        if emp.dias_atraso:
            log("quitacao", f"Quitado c/ multa: {emp.nome}", f"{emp.numero_contrato} MT {float(emp.total_com_multa):,.0f} ({emp.dias_atraso}d atraso)", request)
            messages.success(request, f"✅ Empréstimo quitado! Capital+Juros: MT {float(emp.total_a_pagar):,.2f} + Multa: MT {float(emp.multa_valor):,.2f} = MT {float(emp.total_com_multa):,.2f}")
        else:
            log("quitacao", f"Quitado no prazo: {emp.nome}", f"{emp.numero_contrato} MT {float(emp.total_a_pagar):,.0f}", request)
            messages.success(request, f"✅ Empréstimo quitado no prazo! Total: MT {float(emp.total_a_pagar):,.2f}")
        emp.refresh_from_db()
        if emp.telefone:
            _auto_sms_emprestimo(emp, 'quitado', request.user)
    except Exception as e:
        messages.error(request, f"❌ Erro ao registar pagamento: {e}")
        log("erro_pagamento", f"Erro quitação: {emp.nome}", str(e), request)
    return redirect("emprestimo_detalhe", pk=pk)


# =============================================================================
# APROVAÇÕES
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_aprovacoes(request):
    if not request.user.pode_aprovar:
        messages.error(request, '⛔ Sem permissão para aprovar.')
        return redirect('painel')
    pendentes  = Emprestimo.objects.filter(status='pendente').select_related('registado_por').order_by('-data_registo')
    rejeitados = Emprestimo.objects.filter(status='rejeitado').order_by('-data_registo')[:20]
    return render(request, 'osm/emprestimos/aprovacoes.html', {'pendentes': pendentes, 'rejeitados': rejeitados})

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_aprovar(request, pk):
    from django.db import transaction
    if not request.user.pode_aprovar:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('aprovacoes')
    emp = get_object_or_404(Emprestimo, pk=pk, status='pendente')
    with transaction.atomic():
        emp_locked = Emprestimo.objects.select_for_update().get(pk=pk)
        if emp_locked.status != 'pendente':
            messages.warning(request, 'Este empréstimo já foi processado.')
            return redirect('aprovacoes')
        emp_locked.status         = 'ativo'
        emp_locked.aprovado_por   = request.user
        emp_locked.data_aprovacao = timezone.now()
        emp_locked.save(update_fields=['status', 'aprovado_por', 'data_aprovacao'])
    emp.refresh_from_db()
    b = ConfiguracaoBancaria.obter()
    if emp.telefone:
        _auto_sms_emprestimo(emp, 'aprovado', request.user)
    if b.email_ativo and emp.cliente and emp.cliente.email:
        enviar_cobranca_email(emp, tipo='aprovacao', request=request)
    log('aprovacao', f'APROVADO: {emp.nome}', emp.numero_contrato, request)
    _invalidar_cache_painel()
    messages.success(request, f'✓ Empréstimo de {emp.nome} aprovado!')
    return redirect('aprovacoes')

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_rejeitar(request, pk):
    from django.db import transaction
    if not request.user.pode_aprovar:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('aprovacoes')
    emp = get_object_or_404(Emprestimo, pk=pk, status='pendente')
    motivo = request.POST.get('motivo', 'Não especificado').strip()
    with transaction.atomic():
        emp_locked = Emprestimo.objects.select_for_update().get(pk=pk)
        if emp_locked.status != 'pendente':
            messages.warning(request, 'Este empréstimo já foi processado.')
            return redirect('aprovacoes')
        emp_locked.status          = 'rejeitado'
        emp_locked.motivo_rejeicao = motivo
        emp_locked.save(update_fields=['status', 'motivo_rejeicao'])
    emp.refresh_from_db()
    if emp.telefone:
        _auto_sms_emprestimo(emp, 'rejeitado', request.user)
    log('rejeicao', f'REJEITADO: {emp.nome}', f'{emp.numero_contrato} — {motivo}', request)
    messages.warning(request, f'Empréstimo de {emp.nome} rejeitado.')
    return redirect('aprovacoes')


# =============================================================================
# INADIMPLÊNCIA
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_inadimplencia(request):
    if not (request.user.perm_inadimplencia or request.user.eh_superadmin):
        messages.error(request, '⛔ Sem permissão para aceder à inadimplência.')
        return redirect('painel')

    # Correcção: removido .exclude(pago=True) porque 'pago' é property, não campo real
    for emp in Emprestimo.objects.filter(status__in=['ativo', 'vencido']):
        emp.atualizar_status_automatico()

    vencidos     = list(Emprestimo.objects.filter(status='vencido').order_by('data_vencimento'))
    incump       = list(Emprestimo.objects.filter(status='incumprimento').order_by('data_vencimento'))
    em_atraso    = vencidos + incump
    multa_total  = sum(float(e.multa_valor) for e in em_atraso)
    divida_total = sum(float(e.total_com_multa) for e in em_atraso)
    cfg = ConfiguracaoBancaria.obter()

    return render(request, 'osm/emprestimos/inadimplencia.html', {
        'em_atraso': em_atraso,
        'vencidos': vencidos,
        'incump': incump,
        'multa_total': multa_total,
        'divida_total': divida_total,
        'cfg': cfg,
    })
# =============================================================================
# UTILIZADORES
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_utilizadores(request):
    if not (request.user.perm_utilizadores or request.user.eh_superadmin):
        messages.error(request, '⛔ Sem permissão para gerir utilizadores.')
        return redirect('painel')
    users = Utilizador.objects.select_related('criado_por').order_by('first_name', 'last_name')
    return render(request, 'osm/admin/utilizadores.html', {'users': users})

@login_required
@requer_perfil('superadmin')
def view_utilizador_novo(request):
    if request.method == 'POST':
        return _gravar_utilizador(request, None)
    return render(request, 'osm/admin/utilizador_form.html', {'editar': False})

@login_required
@requer_perfil('superadmin')
def view_utilizador_editar(request, pk):
    u = get_object_or_404(Utilizador, pk=pk)
    if request.method == 'POST':
        return _gravar_utilizador(request, u)
    return render(request, 'osm/admin/utilizador_form.html', {'u': u, 'editar': True})

def _gravar_utilizador(request, u):
    p = request.POST
    nome     = p.get('nome', '').strip()
    apelido  = p.get('apelido', '').strip()
    email    = p.get('email', '').strip().lower()
    telefone = p.get('telefone', '').strip()
    perfil   = p.get('perfil', 'gestor')
    nuit     = p.get('nuit', '').strip()
    bi       = p.get('bi', '').strip()
    cargo    = p.get('cargo', '').strip()
    if not nome:
        messages.error(request, 'Nome é obrigatório.')
        return redirect(request.path)
    def _set_perms_gestor(obj):
        obj.perm_aprovar      = p.get('perm_aprovar') == 'on'
        obj.perm_eliminar     = p.get('perm_eliminar') == 'on'
        obj.perm_sms          = p.get('perm_sms') == 'on'
        obj.perm_exportar     = p.get('perm_exportar') == 'on'
        obj.perm_comerciantes = p.get('perm_comerciantes') == 'on'
        obj.perm_relatorios   = p.get('perm_relatorios') == 'on'
        obj.perm_utilizadores = p.get('perm_utilizadores') == 'on'
        obj.perm_config       = p.get('perm_config') == 'on'
        obj.perm_inadimplencia= p.get('perm_inadimplencia') == 'on'
        obj.perm_tribunal     = p.get('perm_tribunal') == 'on'
        obj.perm_lista_negra  = p.get('perm_lista_negra') == 'on'
        obj.perm_lancamentos  = p.get('perm_lancamentos') == 'on'
        obj.perm_solicitacoes = p.get('perm_solicitacoes') == 'on'
        try:
            obj.limite_emprestimo = Decimal(p.get('limite_emprestimo', '0') or '0')
        except Exception:
            obj.limite_emprestimo = Decimal('0')
    senha_inicial = None
    if u is None:
        senha_inicial = gerar_senha()
        username      = gerar_username()
        tipo_cli = p.get('tipo_cliente', 'normal') if perfil == 'cliente' else 'normal'
        u = Utilizador.objects.create_user(username=username, email=email, password=senha_inicial, first_name=nome, last_name=apelido, perfil=perfil, telefone=telefone, nuit=nuit, bi=bi, cargo=cargo, tipo_cliente=tipo_cli, deve_trocar_senha=True, senha_inicial=senha_inicial, criado_por=request.user)
        if perfil == 'gestor':
            _set_perms_gestor(u)
            u.save()
        enviar_email_credenciais(u, senha_inicial)
        if telefone:
            msg = f'OSM Microcrédito — Bem-vindo(a)! Username: {username} | Password: {senha_inicial} | Acesse em: https://osm.co.mz/login/'
            _enviar_sms_real(telefone, msg, u.nome_completo, '—', request.user)
        log('novo_utilizador', f'Criado: {u.nome_completo}', f'{email} perfil:{perfil}', request)
        request.session['novo_user_pk']    = u.pk
        request.session['novo_user_senha'] = senha_inicial
        messages.success(request, f'✓ {u.nome_completo} criado! Username: {username}')
        return redirect('utilizador_ficha_pdf', pk=u.pk)
    else:
        u.first_name = nome
        u.last_name  = apelido
        u.email      = email
        u.telefone   = telefone
        u.perfil     = perfil
        u.nuit       = nuit
        u.bi         = bi
        u.cargo      = cargo
        if perfil == 'cliente':
            u.tipo_cliente = p.get('tipo_cliente', u.tipo_cliente)
        if perfil == 'gestor':
            _set_perms_gestor(u)
        u.save()
        log('editar_utilizador', f'Editado: {u.nome_completo}', email, request)
        messages.success(request, '✓ Utilizador actualizado.')
        return redirect('utilizadores')

@login_required
@requer_perfil('superadmin')
def view_utilizador_ficha_pdf(request, pk):
    u = get_object_or_404(Utilizador, pk=pk)
    senha = request.session.pop('novo_user_senha', u.senha_inicial or '••••••••')
    return render(request, 'osm/admin/utilizador_ficha.html', {'u': u, 'senha': senha})
 
@login_required
@requer_perfil('superadmin')
def view_utilizador_pdf(request, pk):
    u = get_object_or_404(Utilizador, pk=pk)
    senha = request.session.get('novo_user_senha', u.senha_inicial or '••••••••')
    if u.perfil == 'cliente':
        buf = gerar_ficha_cliente(u, senha)
        nome_pdf = f'cliente_{u.username}.pdf'
    else:
        buf = gerar_ficha_gestor(u, senha)
        nome_pdf = f'gestor_{u.username}.pdf'
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{nome_pdf}"'
    log('pdf_ficha', f'PDF ficha: {u.nome_completo}', u.username, request)
    return response

@login_required
@requer_perfil('superadmin')
@require_POST
def view_utilizador_toggle(request, pk):
    u = get_object_or_404(Utilizador, pk=pk)
    if u == request.user:
        messages.error(request, 'Não pode desactivar a sua própria conta.')
        return redirect('utilizadores')
    u.activo    = not u.activo
    u.is_active = u.activo
    u.save()
    estado = 'activado' if u.activo else 'desactivado'
    log('toggle_utilizador', f'{estado.capitalize()}: {u.nome_completo}', '', request)
    messages.success(request, f'✓ {u.nome_completo} {estado}.')
    return redirect('utilizadores')

@login_required
@requer_perfil('superadmin')
@require_POST
def view_utilizador_eliminar(request, pk):
    u = get_object_or_404(Utilizador, pk=pk)
    if u == request.user:
        messages.error(request, 'Não pode eliminar a sua própria conta.')
        return redirect('utilizadores')
    nome = u.nome_completo
    u.delete()
    log('eliminar_utilizador', f'Eliminado: {nome}', '', request)
    messages.success(request, f'✓ {nome} eliminado.')
    return redirect('utilizadores')


# =============================================================================
# COMERCIANTES (com criação de Credito)
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_comerciantes(request):
    if not request.user.perm_comerciantes and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão para gestão de comerciantes.')
        return redirect('painel')
    from django.db.models import Count, Q
    lista = list(
        Comerciante.objects
        .filter(deleted_at__isnull=True)
        .prefetch_related('pagamentos_diarios', 'creditos')
        .annotate(
            total_creditos=Count(
                'creditos',
                filter=Q(creditos__deleted_at__isnull=True)
            ),
            num_creditos_ativos=Count(
                'creditos',
                filter=Q(creditos__deleted_at__isnull=True, creditos__pago=False)
            ),
            num_creditos_quitados=Count(
                'creditos',
                filter=Q(creditos__deleted_at__isnull=True, creditos__pago=True)
            )
        )
        .all()
    )
    hoje = timezone.localdate()
    return render(request, 'osm/comerciantes_app/comerciantes.html', {'lista': lista, 'hoje': hoje}) 

@login_required
@requer_perfil('superadmin', 'gestor')
def view_comerciante_novo(request):
    if not request.user.perm_comerciantes and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('painel')
    if request.method == 'POST':
        return _gravar_comerciante(request, None)
    return render(request, 'osm/comerciantes_app/comerciante_form.html', {'editar': False, 'tipo_comercio_choices': ['Comércio','Serviços','Produção','Agricultura','Pescas','Construção']})

@login_required
@requer_perfil('superadmin', 'gestor')
def view_comerciante_editar(request, pk):
    com = get_object_or_404(Comerciante, pk=pk, deleted_at__isnull=True)
    if not request.user.perm_comerciantes and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('painel')
    if request.method == 'POST':
        return _gravar_comerciante(request, com)
    return render(request, 'osm/comerciantes_app/comerciante_form.html', {'com': com, 'editar': True, 'tipo_comercio_choices': ['Comércio','Serviços','Produção','Agricultura','Pescas','Construção']})

def _gravar_comerciante(request, com):
    p = request.POST
    nome    = p.get('nome', '').strip()
    capital = Decimal(p.get('capital', '0') or '0')
    if not nome or not capital:
        messages.error(request, 'Nome e capital são obrigatórios.')
        return redirect(request.path)
    dados = {
        'nome': nome, 'tipo_comercio': p.get('tipo_comercio', 'Retalhista'),
        'nuit': p.get('nuit', '').strip(), 'bi': p.get('bi', '').strip(),
        'telefone': p.get('telefone', '').strip(), 'bairro': p.get('bairro', '').strip(),
        'garantia': p.get('garantia', '').strip(),
        'data_inicio': (datetime.strptime(p.get('data_inicio'), '%Y-%m-%d').date() if p.get('data_inicio') else timezone.localdate()),
        'modalidade_pagamento': p.get('modalidade_pagamento', 'diario'), 'prazo_dias': int(p.get('prazo_dias', 30)),
    }
    cfg = ConfiguracaoBancaria.obter()
    taxa_juros = cfg.taxa_juros_padrao
    taxa_multa = cfg.taxa_multa_padrao
    if request.user.eh_superadmin:
        try:
            taxa_juros = Decimal(p.get('taxa_juros', '') or str(cfg.taxa_juros_padrao))
            taxa_multa = Decimal(p.get('taxa_multa', '') or str(cfg.taxa_multa_padrao))
        except:
            pass
    if com is None:
        com = Comerciante(registado_por=request.user, **dados)
        com.save()
        Credito.objects.create(comerciante=com, valor=capital, taxa_juros=taxa_juros, taxa_multa=taxa_multa, prazo_multa_dias=cfg.prazo_multa_dias, data_inicio=com.data_inicio, data_vencimento=com.data_inicio + timedelta(days=com.prazo_dias))
        com.refresh_from_db()
        if com.telefone:
            contexto = {'nome': com.nome, 'contrato': com.numero_contrato, 'valor': f'{float(capital):,.2f}', 'periodo': com.modalidade_pagamento}
            msg = _sms_template('comerciante_criado', contexto)
            _enviar_sms_real(com.telefone, msg, com.nome, com.numero_contrato, request.user)
        log('novo_comerciante', f'Novo: {com.nome}', f'{com.numero_contrato} MT {float(capital):,.0f}', request)
        messages.success(request, f'✓ {com.numero_contrato} registado!')
    else:
        for k, v in dados.items():
            setattr(com, k, v)
        com.save()
        cred = com.creditos_activos.first()
        if cred:
            cred.valor = capital
            cred.taxa_juros = taxa_juros
            cred.taxa_multa = taxa_multa
            cred.save(update_fields=['valor', 'taxa_juros', 'taxa_multa'])
        messages.success(request, '✓ Alterações guardadas.')
    return redirect('comerciantes')

@login_required
@requer_perfil('superadmin', 'gestor')
def view_comerciante_detalhe(request, pk):
    com = get_object_or_404(Comerciante, pk=pk, deleted_at__isnull=True)
    hoje = timezone.localdate()
    inicio = com.data_inicio
    pagamentos = com.pagamentos_diarios.filter(deleted_at__isnull=True).values_list('data', flat=True)
    pagos = set(pagamentos)
    calendario = []
    proximo_nao_pago = None
    for d in range(1, com.prazo_dias + 1):
        data_dia = inicio + timedelta(days=d-1)
        pago = data_dia in pagos
        eh_hoje = (data_dia == hoje)
        calendario.append((d, data_dia, pago, eh_hoje))
        if not pago and proximo_nao_pago is None:
            proximo_nao_pago = (d, data_dia)
    recibos = com.pagamentos_diarios.filter(deleted_at__isnull=True).order_by('-data')
    
    # ---- CRÉDITOS (activos e quitados) ----
    creditos = com.creditos.filter(deleted_at__isnull=True).order_by('-data_inicio')
    creditos_activos = [c for c in creditos if not c.esta_quitado]
    creditos_quitados = [c for c in creditos if c.esta_quitado]

    # Suporte a ?credito=<pk> para pré-seleccionar o tab do crédito correcto
    credito_sel_pk = request.GET.get('credito')
    credito_sel_idx = 0
    if credito_sel_pk:
        try:
            credito_sel_pk = int(credito_sel_pk)
            for i, c in enumerate(creditos_activos):
                if c.pk == credito_sel_pk:
                    credito_sel_idx = i
                    break
        except (ValueError, TypeError):
            pass

    context = {
        'com': com,
        'calendario': calendario,
        'proximo_nao_pago': proximo_nao_pago,
        'hoje': hoje,
        'recibos': recibos,
        'banco': ConfiguracaoBancaria.obter(),
        'creditos_activos': creditos_activos,
        'creditos_quitados': creditos_quitados,
        'credito_sel_idx': credito_sel_idx,
    }
    return render(request, 'osm/comerciantes_app/comerciante_detalhe.html', context)

@login_required
@requer_perfil('superadmin', 'gestor')
def view_creditos_comerciante(request, pk):
    """Página de lista de créditos de um comerciante — equivalente ao creditos_cliente para empréstimos."""
    com = get_object_or_404(
        Comerciante.objects
        .prefetch_related('creditos'),
        pk=pk,
        deleted_at__isnull=True
    )
    creditos = com.creditos.filter(deleted_at__isnull=True).order_by('-data_inicio')
    creditos_activos = [c for c in creditos if not c.esta_quitado]
    creditos_quitados = [c for c in creditos if c.esta_quitado]
    context = {
        'com': com,
        'creditos_activos': creditos_activos,
        'creditos_quitados': creditos_quitados,
        'total_creditos': len(creditos),
    }
    return render(request, 'osm/comerciantes_app/creditos_comerciante.html', context)

# =============================================================================
# CRÉDITOS PARA COMERCIANTES – HTMX
# =============================================================================

@login_required
@requer_perfil('superadmin', 'gestor')
def creditos_lista_comerciante(request, pk):
    com = get_object_or_404(Comerciante, pk=pk)
    creditos = com.creditos.filter(deleted_at__isnull=True).order_by('-data_inicio')
    creditos_activos = [c for c in creditos if not c.esta_quitado]
    creditos_quitados = [c for c in creditos if c.esta_quitado]
    return render(request, 'osm/includes/creditos_lista_comerciante.html', {
        'com': com,
        'creditos_activos': creditos_activos,
        'creditos_quitados': creditos_quitados,
    })
 
@login_required
@requer_perfil('superadmin', 'gestor')
def adicionar_credito_comerciante_form(request, pk):
    com = get_object_or_404(Comerciante, pk=pk)
    return render(request, 'osm/includes/credito_form_comerciante.html', {'com': com})

@login_required
@requer_perfil('superadmin', 'gestor')
def adicionar_credito_comerciante(request, pk):
    com = get_object_or_404(Comerciante, pk=pk)
    if request.method == 'POST':
        try:
            valor = Decimal(request.POST.get('valor', '0'))
            taxa_juros = Decimal(request.POST.get('taxa_juros', '30'))
            taxa_multa = Decimal(request.POST.get('taxa_multa', '2'))
            prazo_multa_dias = int(request.POST.get('prazo_multa_dias', 5))
            data_inicio_str = request.POST.get('data_inicio')
            data_vencimento_str = request.POST.get('data_vencimento')

            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else timezone.localdate()
            data_vencimento = datetime.strptime(data_vencimento_str, '%Y-%m-%d').date() if data_vencimento_str else None

            Credito.objects.create(
                comerciante=com,
                valor=valor,
                taxa_juros=taxa_juros,
                taxa_multa=taxa_multa,
                prazo_multa_dias=prazo_multa_dias,
                data_inicio=data_inicio,
                data_vencimento=data_vencimento,
                pago=False,
            )
            messages.success(request, f'✅ Crédito de MT {valor:,.2f} adicionado ao comerciante {com.nome}!')
            log('creditos_lista_comerciante', f'Novo crédito: {com.nome}', f'{com.numero_contrato} MT {valor:,.2f}', request)
        except Exception as e:
            messages.error(request, f'❌ Erro ao adicionar crédito: {str(e)}')

    if request.headers.get('HX-Request'):
        return creditos_lista_comerciante(request, pk)
    return redirect('creditos_lista_comerciante', pk=com.pk)

@login_required
@requer_perfil('superadmin', 'gestor')
def view_recibo_comerciante_pdf(request, pk):
    pagamento = get_object_or_404(PagamentoDiario, pk=pk, deleted_at__isnull=True)
    com = pagamento.comerciante
    buf = gerar_recibo_comerciante(com, today=pagamento.data, registado_por=pagamento.registado_por)
    response = HttpResponse(buf, content_type='application/pdf')
    nome_pdf = f"recibo_{com.numero_contrato}_{pagamento.data.strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'inline; filename="{nome_pdf}"'
    return response

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_confirmar_pagamento(request, pk, data=None):
    from django.db import transaction
    from .models import SMS_CUSTO
    if not request.user.perm_comerciantes and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('comerciante_detalhe', pk=pk)
    if data is None:
        data_str = request.POST.get('data')
        if data_str:
            try:
                data = datetime.strptime(data_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Data inválida.')
                return redirect('comerciante_detalhe', pk=pk)
        else:
            data = timezone.localdate()
    else:
        if isinstance(data, str):
            try:
                data = datetime.strptime(data, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Data inválida.')
                return redirect('comerciante_detalhe', pk=pk)
    with transaction.atomic():
        com = Comerciante.objects.select_for_update().get(pk=pk)
        delta = (data - com.data_inicio).days
        if delta < 0 or delta >= com.prazo_dias:
            messages.error(request, f'Data {data.strftime("%d/%m/%Y")} fora do período do contrato.')
            return redirect('comerciante_detalhe', pk=pk)
        if com.pagamentos_diarios.filter(data=data, deleted_at__isnull=True).exists():
            messages.warning(request, f'Pagamento para {data.strftime("%d/%m/%Y")} já registado.')
            return redirect('comerciante_detalhe', pk=pk)
        valor_parcela = com.parcela_atual
        PagamentoDiario.objects.create(comerciante=com, data=data, valor_pago=valor_parcela, custo_sms=SMS_CUSTO, registado_por=request.user, confirmado=True)
        if com.data_ultimo_pagamento is None or data > com.data_ultimo_pagamento:
            com.data_ultimo_pagamento = data
            com.save(update_fields=['data_ultimo_pagamento'])
    com = Comerciante.objects.get(pk=pk)
    log('pagamento_comercio', f'Pagamento {com.modalidade_pagamento}: {com.nome} - {data.strftime("%d/%m/%Y")}', f'{com.numero_contrato} periodo {com.periodos_pagos}/{com.total_periodos}', request)
    messages.success(request, f'✅ Pagamento de {data.strftime("%d/%m/%Y")} confirmado! <small>(+1.20 MT SMS)</small>')
    if com.telefone:
        _auto_sms_comerciante(com, 'comerciante_pagamento', request.user)
    try:
        from .pdf_utils import gerar_recibo_comerciante
        gerar_recibo_comerciante(com, today=data, registado_por=request.user)
    except Exception as e:
        logger.warning(f"Erro ao gerar recibo do comerciante {com.pk}: {e}")
    return redirect('comerciante_detalhe', pk=pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_anular_pagamento_data(request, pk):
    from django.db import transaction
    com = get_object_or_404(Comerciante, pk=pk)
    if not request.user.perm_comerciantes and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('comerciante_detalhe', pk=pk)
    data_str = request.POST.get('data')
    if not data_str:
        messages.error(request, 'Data não especificada.')
        return redirect('comerciante_detalhe', pk=pk)
    try:
        data = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'Data inválida.')
        return redirect('comerciante_detalhe', pk=pk)
    with transaction.atomic():
        pag = com.pagamentos_diarios.filter(data=data).first()
        if pag:
            pag.delete()
            log('anular_pagamento_data', f'Anulado: {com.nome} - {data.strftime("%d/%m/%Y")}', com.numero_contrato, request)
            messages.warning(request, f'Pagamento de {data.strftime("%d/%m/%Y")} anulado.')
        else:
            messages.info(request, f'Nenhum pagamento encontrado para {data.strftime("%d/%m/%Y")}.')
    return redirect('comerciante_detalhe', pk=pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_cancelar_pagamento(request, pk):
    com = get_object_or_404(Comerciante, pk=pk)
    if not request.user.perm_comerciantes and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('comerciante_detalhe', pk=pk)
    hoje = timezone.localdate()
    pag = com.pagamentos_diarios.filter(data=hoje).first()
    if pag:
        pag.delete()
        log('cancelar_pagamento', f'Anulado: {com.nome}', com.numero_contrato, request)
        messages.warning(request, f'Pagamento de {com.nome} de hoje anulado.')
    return redirect('comerciante_detalhe', pk=pk)


# =============================================================================
# PDFs
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def visualizar_contrato(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    buf = gerar_contrato(emp)
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="contrato_{emp.numero_contrato}.pdf"'
    return response

@login_required
@requer_perfil('superadmin', 'gestor')
def baixar_contrato(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    buf = gerar_contrato(emp)
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="contrato_{emp.numero_contrato}.pdf"'
    log('pdf_contrato', f'PDF contrato: {emp.nome}', emp.numero_contrato, request)
    return response

@login_required
def view_pdf_declaracao(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    buf = gerar_declaracao(emp)
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="declaracao_{emp.numero_contrato}.pdf"'
    log('pdf_declaracao', f'PDF declaração: {emp.nome}', emp.numero_contrato, request)
    return response


# =============================================================================
# PAGAMENTOS — lista global com estatísticas (adaptado para Credito)
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_pagamentos(request):
    q          = request.GET.get('q', '').strip()
    filtro_de  = request.GET.get('de', '')
    filtro_ate = request.GET.get('ate', '')
    qs = Pagamento.objects.select_related('credito__emprestimo', 'registado_por').order_by('-data_pagamento')
    if q:
        qs = qs.filter(Q(credito__emprestimo__nome__icontains=q) | Q(credito__emprestimo__numero_contrato__icontains=q) | Q(credito__emprestimo__telefone__icontains=q))
    if filtro_de:
        try:
            qs = qs.filter(data_pagamento__gte=datetime.strptime(filtro_de, '%Y-%m-%d').date())
        except ValueError:
            pass
    if filtro_ate:
        try:
            qs = qs.filter(data_pagamento__lte=datetime.strptime(filtro_ate, '%Y-%m-%d').date())
        except ValueError:
            pass
    hoje = timezone.localdate()
    mes_ini = hoje.replace(day=1)
    total_rec = Pagamento.objects.aggregate(t=Sum('valor_total'))['t'] or Decimal('0')
    rec_mes = Pagamento.objects.filter(data_pagamento__gte=mes_ini).aggregate(t=Sum('valor_total'))['t'] or Decimal('0')
    pag_mes = Pagamento.objects.filter(data_pagamento__gte=mes_ini).count()
    
    # Carteira activa: soma dos créditos não pagos de empréstimos activos/vencidos/incumprimento
    carteira = Credito.active_objects.filter(
        emprestimo__status__in=['ativo', 'vencido', 'incumprimento'],
        pago=False
    ).aggregate(t=Sum('valor'))['t'] or Decimal('0')
    
    # Corrigido: empréstimos activos (não quitados)
    num_ativos = Emprestimo.objects.filter(status__in=['ativo', 'vencido', 'incumprimento']).count()
    
    num_venc   = Emprestimo.objects.filter(status__in=['vencido', 'incumprimento']).count()
    val_venc   = Credito.active_objects.filter(
        emprestimo__status__in=['vencido', 'incumprimento'],
        pago=False
    ).aggregate(t=Sum('valor'))['t'] or Decimal('0')
    
    stats = {
        'total_recebido': total_rec,
        'num_pagamentos': Pagamento.objects.count(),
        'carteira_activa': carteira,
        'num_ativos': num_ativos,
        'total_vencido': val_venc,
        'num_vencidos': num_venc,
        'recebido_mes': rec_mes,
        'pagamentos_mes': pag_mes,
    }
    return render(request, 'osm/pagamentos_app/pagamentos.html', {
        'pagamentos': qs,
        'stats': stats,
        'q': q,
        'filtro_de': filtro_de,
        'filtro_ate': filtro_ate,
    })
# =============================================================================
# COBRANÇA / SMS
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_cobranca(request):
    if not request.user.perm_sms and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão para aceder à cobrança.')
        return redirect('painel')
    em_atraso = Emprestimo.objects.filter(status__in=['vencido', 'incumprimento']).select_related('cliente').order_by('-data_vencimento')
    comerciantes_em_atraso = Comerciante.objects.filter(multa_cancelada=False, enviado_tribunal=False, deleted_at__isnull=True).order_by('-criado_em')
    banco = ConfiguracaoBancaria.obter()
    tem_sms_config = bool(getattr(settings, 'MOZESMS_BEARER_TOKEN', None) or getattr(banco, 'bulksms_api_token', None))
    total_atraso = em_atraso.count() + comerciantes_em_atraso.count()
    email_tipos = [('atraso','Atraso','fa-solid fa-exclamation-triangle','#e65100'), ('urgente','Urgente','fa-solid fa-fire','#c62828'), ('juridico','Jurídico','fa-solid fa-scale-balanced','#4a148c'), ('lembrete','Lembrete','fa-solid fa-bell','#0277bd'), ('quitacao','Quitação','fa-solid fa-trophy','#2e7d32')]
    email_tipo_descricoes = [('atraso','Aviso de Atraso','Notifica o cliente da parcela em atraso, indica valor e dados de pagamento.','fa-solid fa-exclamation-triangle','#e65100'), ('urgente','Urgente','Para casos de incumprimento grave, exige acção imediata do cliente.','fa-solid fa-fire','#c62828'), ('juridico','Notificação Jurídica','Aviso formal de envio para tribunal se não regularizar em 48 horas.','fa-solid fa-scale-balanced','#4a148c'), ('lembrete','Lembrete','Lembrete amigável de vencimento próximo para prevenir atraso.','fa-solid fa-bell','#0277bd'), ('quitacao','Parabéns / Quitação','Email de felicitações enviado após quitação total do contrato.','fa-solid fa-trophy','#2e7d32')]
    context = {
        'em_atraso': em_atraso, 'comerciantes_em_atraso': comerciantes_em_atraso,
        'sms_log': LogSMS.objects.select_related('enviado_por').order_by('-criado_em')[:50], 'banco': banco,
        'banco_nome': banco.banco, 'banco_conta': banco.conta, 'banco_nib': banco.nib,
        'telefone_osm': getattr(banco, 'telefone_contacto', None) or '258872031215', 'tem_sms_config': tem_sms_config,
        'total_atraso': total_atraso, 'email_tipos': email_tipos, 'email_tipo_descricoes': email_tipo_descricoes,
    }
    return render(request, 'osm/pagamentos_app/cobranca.html', context)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_enviar_sms(request):
    if not request.user.perm_sms and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão para enviar SMS.')
        return redirect('cobranca')
    ids_emp = request.POST.getlist('dest_emp')
    ids_com = request.POST.getlist('dest_com')
    msg_template = request.POST.get('mensagem', '').strip()
    if not msg_template:
        messages.error(request, 'Escreva uma mensagem.')
        return redirect('cobranca')
    if not ids_emp and not ids_com:
        messages.error(request, 'Seleccione pelo menos um destinatário.')
        return redirect('cobranca')
    b = ConfiguracaoBancaria.obter()
    tem_moze = bool(getattr(settings, 'MOZESMS_BEARER_TOKEN', None))
    count = 0
    erros = 0
    def substituir_banco(msg):
        emola_str = f"{b.emola_numero} — {b.emola_titular}" if b.emola_numero else 'não disponível'
        return msg.replace('{banco}', b.banco).replace('{conta}', b.conta).replace('{nib}', b.nib).replace('{emola}', emola_str).replace('{telefone}', getattr(b, 'telefone', '') or '')
    for pk in ids_emp:
        try:
            e = Emprestimo.objects.get(pk=pk)
            if not e.telefone:
                continue
            m = substituir_banco(msg_template)
            m = m.replace('{nome}', e.nome).replace('{contrato}', e.numero_contrato).replace('{valor}', e.valor_fmt).replace('{mora}', str(round(float(e.mora_composta),2))).replace('{totalMora}', str(round(float(e.total_com_multa),2))).replace('{data}', e.data_vencimento.strftime('%d/%m/%Y') if e.data_vencimento else '—').replace('{capital}', str(round(float(e.valor),2))).replace('{parcela}', '—').replace('{diaPagamento}', '—').replace('{totalPago}', '—').replace('{diasRestantes}', '—').replace('{periodos_atraso}', str(e.dias_atraso)+'d')
            if tem_moze:
                ok, detalhe = enviar_sms_mozesms(e.telefone, m)
                status = 'enviado' if ok else f'erro:{detalhe[:50]}'
                if not ok:
                    erros += 1
            elif b.bulksms_api_token:
                ok, detalhe = enviar_sms_bulksms(e.telefone, m, b)
                status = 'enviado' if ok else f'erro:{detalhe[:50]}'
                if not ok:
                    erros += 1
            else:
                status = 'simulado'
            LogSMS.objects.create(nome=e.nome, telefone=e.telefone, mensagem=m, status=status, numero_contrato=e.numero_contrato, enviado_por=request.user)
            count += 1
        except Emprestimo.DoesNotExist:
            pass
    for pk in ids_com:
        try:
            c = Comerciante.objects.get(pk=pk)
            if not c.telefone:
                continue
            total_pago = float(c.total_pago) if hasattr(c,'total_pago') else 0
            parcela = float(c.parcela_atual) if hasattr(c,'parcela_atual') else 0
            periodos_p = c.periodos_pagos if hasattr(c,'periodos_pagos') else 0
            periodos_t = c.total_periodos if hasattr(c,'total_periodos') else 30
            dias_rest = max(0, periodos_t - periodos_p)
            mora_com = float(c.multa_valor) if hasattr(c,'multa_valor') else 0
            p_atraso = c.periodos_em_atraso if hasattr(c,'periodos_em_atraso') else 0
            m = substituir_banco(msg_template)
            m = m.replace('{nome}', c.nome).replace('{contrato}', c.numero_contrato).replace('{capital}', str(round(float(c.capital),2))).replace('{valor}', str(round(float(c.capital),2))).replace('{parcela}', str(round(parcela,2))).replace('{totalPago}', str(round(total_pago,2))).replace('{diaPagamento}', str(periodos_p)).replace('{diasRestantes}', str(dias_rest)).replace('{mora}', str(round(mora_com,2))).replace('{totalMora}', str(round(float(c.total_restante),2) if hasattr(c,'total_restante') else '0')).replace('{periodos_atraso}', str(p_atraso)).replace('{data}', c.data_inicio.strftime('%d/%m/%Y') if c.data_inicio else '—').replace('{motivo}', '—')
            if tem_moze:
                ok, detalhe = enviar_sms_mozesms(c.telefone, m)
                status = 'enviado' if ok else f'erro:{detalhe[:50]}'
                if not ok:
                    erros += 1
            elif b.bulksms_api_token:
                ok, detalhe = enviar_sms_bulksms(c.telefone, m, b)
                status = 'enviado' if ok else f'erro:{detalhe[:50]}'
                if not ok:
                    erros += 1
            else:
                status = 'simulado'
            LogSMS.objects.create(nome=c.nome, telefone=c.telefone, mensagem=m, status=status, numero_contrato=c.numero_contrato, enviado_por=request.user)
            count += 1
        except Comerciante.DoesNotExist:
            pass
    log('sms_enviado', f'SMS a {count} dest. (emp+com)', msg_template[:60], request)
    if erros:
        messages.warning(request, f'✓ {count} SMS processados, {erros} com erro. Verifique o log.')
    elif not tem_moze and not b.bulksms_api_token:
        messages.warning(request, f'✓ {count} SMS registados (modo simulação — configure Token MozeSMS ou BulkSMS nas Configurações).')
    else:
        messages.success(request, f'✅ {count} SMS enviado(s) com sucesso! ({len(ids_emp)} empréstimos · {len(ids_com)} comerciantes)')
    return redirect('cobranca')

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_sms_bulk(request):
    if not request.user.perm_sms and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('cobranca')
    b = ConfiguracaoBancaria.obter()
    count = 0
    erros = 0
    for e in Emprestimo.objects.filter(status__in=['vencido', 'incumprimento']).select_related('cliente'):
        if not e.telefone:
            continue
        tipo = 'urgente' if e.em_incumprimento else 'atraso'
        ok, _ = _auto_sms_emprestimo(e, tipo, request.user)
        if not ok:
            erros += 1
        count += 1
    for c in Comerciante.objects.filter(multa_cancelada=False, enviado_tribunal=False, deleted_at__isnull=True):
        if not c.telefone:
            continue
        p_atraso = c.periodos_em_atraso if hasattr(c,'periodos_em_atraso') else 0
        if p_atraso <= 0:
            continue
        ok, _ = _auto_sms_comerciante(c, 'comerciante_atraso', request.user)
        if not ok:
            erros += 1
        count += 1
    log('sms_bulk', f'Bulk {count} (erros={erros}) emp+com', '', request)
    tem_api = bool(getattr(settings, 'MOZESMS_BEARER_TOKEN', None)) or bool(b.bulksms_api_token)
    if not tem_api:
        messages.warning(request, f'✓ {count} SMS registados em modo simulação. Configure Token MozeSMS ou BulkSMS nas Configurações.')
    elif erros:
        messages.warning(request, f'✅ {count - erros} SMS enviados, {erros} falharam. Verifique o log.')
    else:
        messages.success(request, f'✅ {count} SMS de cobrança enviados (empréstimos + comerciantes)!')
    return redirect('cobranca')

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_email_cobranca_bulk(request):
    if not request.user.perm_sms and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('cobranca')
    tipo_email = request.POST.get('tipo_email', 'atraso')
    count = 0
    erros = 0
    sem_email = 0
    emprestimos_ids = request.POST.getlist('dest_emp')
    if emprestimos_ids:
        qs = Emprestimo.objects.filter(pk__in=emprestimos_ids).select_related('cliente')
    else:
        qs = Emprestimo.objects.filter(status__in=['vencido', 'incumprimento']).select_related('cliente')
    for emp in qs:
        if not emp.cliente or not emp.cliente.email:
            sem_email += 1
            continue
        ok, msg = enviar_cobranca_email(emp, tipo=tipo_email, request=request)
        if ok:
            count += 1
        else:
            erros += 1
    log('email_bulk', f'Email bulk {count} (erros={erros} sem_email={sem_email})', tipo_email, request)
    partes = []
    if count:
        partes.append(f'✅ {count} email(s) enviados')
    if erros:
        partes.append(f'❌ {erros} falhou')
    if sem_email:
        partes.append(f'⚠ {sem_email} sem email')
    msg_final = ' · '.join(partes) if partes else 'Nenhum email enviado.'
    if erros or sem_email:
        messages.warning(request, msg_final)
    else:
        messages.success(request, msg_final)
    return redirect('cobranca')

@login_required
@requer_perfil('superadmin')
@require_POST
def view_banco_editar(request):
    b = ConfiguracaoBancaria.obter()
    b.banco   = request.POST.get('banco', b.banco)
    b.nib     = request.POST.get('nib', b.nib)
    b.conta   = request.POST.get('conta', b.conta)
    b.titular = request.POST.get('titular', b.titular)
    b.nuit    = request.POST.get('nuit', b.nuit)
    b.atualizado_por = request.user
    b.save()
    log('banco_editado', 'Dados bancários actualizados', b.banco, request)
    messages.success(request, '✓ Dados bancários actualizados.')
    return redirect('cobranca')

@login_required
@requer_perfil('superadmin')
@require_POST
def view_sms_config_editar(request):
    b = ConfiguracaoBancaria.obter()
    b.bulksms_api_token = request.POST.get('bulksms_api_token', '').strip()
    b.bulksms_sender    = request.POST.get('bulksms_sender', 'OSM').strip()[:11]
    b.sms_alerta_dias   = int(request.POST.get('sms_alerta_dias', 3))
    b.sms_cobranca_auto = request.POST.get('sms_cobranca_auto') == '1'
    b.email_smtp_host = request.POST.get('email_smtp_host', '').strip()
    b.email_smtp_port = int(request.POST.get('email_smtp_port', 587) or 587)
    b.email_smtp_user = request.POST.get('email_smtp_user', '').strip()
    senha_nova = request.POST.get('email_smtp_pass', '').strip()
    if senha_nova:
        b.email_smtp_pass = senha_nova
    b.email_smtp_tls = request.POST.get('email_smtp_tls') == '1'
    b.email_ativo    = request.POST.get('email_ativo') == '1'
    b.atualizado_por = request.user
    b.save()
    log('sms_config_editado', 'Configurações SMS/Email actualizadas', '', request)
    messages.success(request, '✅ Configurações de SMS e Email guardadas com sucesso.')
    return redirect('configuracoes')

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_enviar_email_cobranca(request, pk):
    if not request.user.perm_sms and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('cobranca')
    emp = get_object_or_404(Emprestimo, pk=pk)
    tipo = request.POST.get('tipo_email', 'atraso')
    ok, detalhe = enviar_cobranca_email(emp, tipo, request)
    if ok:
        messages.success(request, f'✅ {detalhe}')
    else:
        messages.error(request, f'❌ Falha: {detalhe}')
    return redirect(request.POST.get('next', 'cobranca'))

@login_required
@requer_perfil('superadmin')
def view_gerar_aviso_cobranca_pdf(request, pk):
    from django.template.loader import render_to_string
    emp = get_object_or_404(Emprestimo, pk=pk)
    banco = ConfiguracaoBancaria.obter()
    ctx = {'emprestimo': emp, 'banco': banco, 'hoje': timezone.localdate().strftime('%d/%m/%Y')}
    html = render_to_string('pdfs/cobranca_aviso.html', ctx)
    try:
        from weasyprint import HTML as WP_HTML
        pdf_bytes = WP_HTML(string=html).write_pdf()
        resp = HttpResponse(pdf_bytes, content_type='application/pdf')
        resp['Content-Disposition'] = f'inline; filename="aviso_{emp.numero_contrato}.pdf"'
        return resp
    except ImportError:
        return HttpResponse(html, content_type='text/html')

@login_required
@requer_perfil('superadmin')
@require_POST
def view_testar_sms(request):
    tel = request.POST.get('telefone_teste', '').strip()
    if not tel:
        messages.error(request, 'Indique um número de telefone.')
        return redirect('configuracoes')
    if not settings.MOZESMS_BEARER_TOKEN:
        messages.error(request, '⚠ Configure o Token da MozeSMS nas variáveis de ambiente.')
        return redirect('configuracoes')
    ok, detalhe = enviar_sms_mozesms(tel, 'OSM Microcredito: Teste de SMS bem sucedido!')
    if ok:
        messages.success(request, f'✅ SMS de teste enviado para {tel} — {detalhe}')
    else:
        messages.error(request, f'❌ Falha ao enviar SMS: {detalhe}')
    return redirect('configuracoes')


# =============================================================================
# RELATÓRIOS
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_relatorios(request):
    if not request.user.perm_relatorios and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('painel')
    periodo = request.GET.get('periodo', 'mensal')
    hoje = timezone.localdate()
    if periodo == 'diario':
        dini = dfim = hoje
    elif periodo == 'semanal':
        dini = hoje - timedelta(days=hoje.weekday())
        dfim = dini + timedelta(days=6)
    elif periodo == 'trimestral':
        q = (hoje.month - 1) // 3
        dini = date(hoje.year, q*3+1, 1)
        dfim = date(hoje.year, (q*3+3), [31,28,31,30,31,30,31,31,30,31,30,31][q*3+2])
    elif periodo == 'anual':
        dini = date(hoje.year, 1, 1)
        dfim = date(hoje.year, 12, 31)
    else:
        dini = date(hoje.year, hoje.month, 1)
        mes_prox = hoje.month+1 if hoje.month<12 else 1
        ano_prox = hoje.year if hoje.month<12 else hoje.year+1
        dfim = date(ano_prox, mes_prox, 1) - timedelta(days=1)
    actividades = LogActividade.objects.filter(criado_em__date__gte=dini, criado_em__date__lte=dfim).select_related('utilizador')
    sms_p = LogSMS.objects.filter(criado_em__date__gte=dini, criado_em__date__lte=dfim)
    return render(request, 'osm/admin/relatorios.html', {
        'periodo': periodo, 'dini': dini, 'dfim': dfim, 'actividades': actividades[:100],
        'total_act': actividades.count(), 'novos_emp': actividades.filter(tipo='novo_emprestimo').count(),
        'pagamentos': actividades.filter(tipo='pagamento').count(), 'logins': actividades.filter(tipo='login').count(),
        'sms_count': sms_p.count(), 'kpis': calcular_kpis(), 'rel': calcular_relatorio_periodo(dini, dfim),
    })


# =============================================================================
# HISTÓRICO E EXPORTAR
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_historico(request):
    qs = Emprestimo.objects.select_related('registado_por').all()
    pg = Paginator(qs, 30)
    return render(request, 'osm/pagamentos_app/historico.html', {'page': pg.get_page(request.GET.get('page',1))})

@login_required
@requer_perfil('superadmin', 'gestor')
def view_exportar(request):
    if not request.user.perm_exportar and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão para exportar.')
        return redirect('painel')
    return render(request, 'osm/pagamentos_app/exportar.html')

@login_required
@requer_perfil('superadmin', 'gestor')
def view_exportar_csv(request):
    import csv
    if not request.user.perm_exportar and not request.user.eh_superadmin:
        messages.error(request, '⛔ Sem permissão.')
        return redirect('painel')
    resp = HttpResponse(content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="osm_emprestimos.csv"'
    resp.write('\ufeff')
    w = csv.writer(resp)
    w.writerow(['Contrato', 'Nome', 'NUIT', 'Telefone', 'Sector', 'Valor', 'TipoCliente', 'Status', 'Score', 'Data'])
    for e in Emprestimo.objects.all():
        w.writerow([e.numero_contrato, e.nome, e.nuit, e.telefone, e.sector, float(e.valor), e.tipo_cliente, e.status, e.score, e.data_registo.strftime('%d/%m/%Y')])
    log('exportar', 'CSV exportado', f'{Emprestimo.objects.count()} registos', request)
    return resp


# =============================================================================
# ACTIVIDADES
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_actividades(request):
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '')
    data = request.GET.get('data', '')
    qs = LogActividade.objects.select_related('utilizador').all()
    if q:
        qs = qs.filter(Q(descricao__icontains=q) | Q(detalhe__icontains=q))
    if tipo:
        qs = qs.filter(tipo=tipo)
    if data:
        qs = qs.filter(criado_em__date=data)
    tipos = LogActividade.objects.values_list('tipo', flat=True).distinct()
    pg = Paginator(qs, 50)
    return render(request, 'osm/admin/actividades.html', {'page': pg.get_page(request.GET.get('page',1)), 'q': q, 'tipo': tipo, 'data': data, 'tipos': sorted(set(tipos)), 'total': qs.count(), 'hoje': LogActividade.objects.filter(criado_em__date=timezone.localdate()).count()})


# =============================================================================
# CONFIGURAÇÕES
# =============================================================================
@login_required
def view_configuracoes(request):
    from django.utils import timezone as tz
    b = ConfiguracaoBancaria.obter()
    now = tz.now()
    mes_ini = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sms_total = LogSMS.objects.count()
    sms_mes = LogSMS.objects.filter(criado_em__gte=mes_ini).count()
    ultimo_sms = LogSMS.objects.order_by('-criado_em').values_list('criado_em', flat=True).first()
    return render(request, 'osm/admin/configuracoes.html', {'banco': b, 'user': request.user, 'total': Emprestimo.objects.count(), 'sms_total': sms_total, 'sms_mes': sms_mes, 'ultimo_sms': ultimo_sms})

@login_required
@requer_perfil('superadmin')
@require_POST
def view_taxas_editar(request):
    cfg = ConfiguracaoBancaria.obter()
    try:
        cfg.taxa_juros_padrao = Decimal(request.POST.get('taxa_juros_padrao', cfg.taxa_juros_padrao))
        cfg.taxa_multa_padrao = Decimal(request.POST.get('taxa_multa_padrao', cfg.taxa_multa_padrao))
        cfg.prazo_multa_dias  = int(request.POST.get('prazo_multa_dias', cfg.prazo_multa_dias))
        cfg.atualizado_por = request.user
        cfg.save()
        cache.delete('kpis_dashboard')
        log('taxas_editadas', f'Taxas: juro={cfg.taxa_juros_padrao}% multa={cfg.taxa_multa_padrao}% prazo={cfg.prazo_multa_dias}d', '', request)
        messages.success(request, f'✓ Taxas actualizadas — Juro: {cfg.taxa_juros_padrao}% · Multa: {cfg.taxa_multa_padrao}%/dia · Prazo: {cfg.prazo_multa_dias} dias')
    except Exception as e:
        messages.error(request, f'Erro: {e}')
    return redirect('configuracoes')


# =============================================================================
# PORTAL DO CLIENTE
# =============================================================================
@login_required
def view_portal_cliente(request):
    if request.user.perfil not in ('cliente',) and not request.user.eh_superadmin:
        return redirect('painel')
    emprestimos = Emprestimo.objects.filter(Q(cliente=request.user) | Q(nuit=request.user.nuit) | Q(telefone=request.user.telefone)).order_by('-data_registo') if request.user.perfil == 'cliente' else Emprestimo.objects.none()
    for e in emprestimos.filter(status__in=['ativo', 'vencido']).exclude(pago=True):
        e.atualizar_status_automatico()
    requisicoes = RequisicaoCliente.objects.filter(cliente=request.user).order_by('-data_requisicao')
    contratos_comerciante = Comerciante.objects.filter(cliente=request.user, deleted_at__isnull=True).order_by('-criado_em')
    banco = ConfiguracaoBancaria.obter()
    tem_tribunal = emprestimos.filter(status='incumprimento').exists()
    tem_ativo = emprestimos.filter(status__in=['ativo', 'vencido', 'pendente']).exists()
    return render(request, 'osm/cliente/portal_cliente.html', {'emprestimos': emprestimos, 'requisicoes': requisicoes, 'contratos_comerciante': contratos_comerciante, 'banco': banco, 'tem_tribunal': tem_tribunal, 'tem_ativo': tem_ativo})

@login_required
def view_requisicao_nova(request):
    if request.user.perfil != 'cliente' and not request.user.eh_superadmin:
        return redirect('painel')
    u = request.user
    if not u.pode_solicitar:
        messages.error(request, u.motivo_bloqueio_requisicao)
        return redirect('portal_cliente')
    if request.method == 'POST':
        p = request.POST
        try:
            valor = Decimal(p.get('valor', '0') or '0')
        except Exception:
            valor = Decimal('0')
        if valor < 1000:
            messages.error(request, 'Valor mínimo é MT 1.000.')
            return redirect('requisicao_nova')
        tipo_cli = p.get('tipo_cliente', u.tipo_cliente)
        req = RequisicaoCliente.objects.create(cliente=u, tipo_cliente=tipo_cli, valor_pedido=valor, finalidade=p.get('finalidade', '').strip(), garantia_desc=p.get('garantia', '').strip())
        log('nova_requisicao', f'Requisição: {request.user.nome_completo}', f'MT {float(valor):,.0f}', request)
        messages.success(request, '✓ Pedido submetido com sucesso! Aguarde resposta.')
        return redirect('portal_cliente')
    return render(request, 'osm/cliente/requisicao_form.html')


# =============================================================================
# API JSON
# =============================================================================
@login_required
def api_kpis(request):
    return JsonResponse(calcular_kpis())

@login_required
def api_emprestimos(request):
    q = request.GET.get('q', '')
    qs = Emprestimo.objects.all()
    if q:
        qs = qs.filter(Q(nome__icontains=q) | Q(numero_contrato__icontains=q))
    data = [{'id': e.pk, 'contrato': e.numero_contrato, 'nome': e.nome, 'valor': str(e.valor), 'status': e.status, 'progresso': e.progresso} for e in qs[:30]]
    return JsonResponse({'results': data})


# =============================================================================
# LANÇAMENTOS DE PAGAMENTO DE EMPRÉSTIMO
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_lancamentos_lista(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    lancamentos = LancamentoPagamento.objects.filter(emprestimo=emp).select_related('submetido_por', 'validado_por').order_by('-criado_em')
    validados = lancamentos.filter(status='validado')
    pendentes_val = lancamentos.filter(status='pendente').count()
    n_validados = validados.count()
    total_lancado = validados.aggregate(t=Sum('valor_pago'))['t'] or 0
    return render(request, 'osm/emprestimos/lancamentos_lista.html', {'emp': emp, 'lancamentos': lancamentos, 'pendentes_val': pendentes_val, 'n_validados': n_validados, 'total_lançado': total_lancado})

@login_required
def view_lancamento_novo(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    user = request.user
    if emp.pago or emp.status == 'quitado':
        messages.error(request, 'Este empréstimo já está quitado.')
        return redirect('emprestimo_detalhe', pk=pk)
    if emp.status in ('pendente', 'rejeitado'):
        messages.error(request, 'Empréstimo pendente de aprovação ou rejeitado.')
        return redirect('emprestimo_detalhe', pk=pk)
    eh_staff = user.perfil in ('superadmin', 'gestor') or user.is_superuser
    if request.method == 'POST':
        p = request.POST
        metodo = p.get('metodo', '')
        if metodo == 'dinheiro' and not eh_staff:
            messages.error(request, '⛔ Apenas gestores podem lançar dinheiro físico.')
            return redirect('lancamento_novo', pk=pk)
        try:
            valor = Decimal(p.get('valor_pago', '0') or '0')
        except Exception:
            valor = Decimal('0')
        if valor <= 0:
            messages.error(request, 'Valor inválido.')
            return redirect('lancamento_novo', pk=pk)
        foto = request.FILES.get('foto_comprovativo')
        tipo_pag = p.get('tipo_pagamento', 'total')
        if tipo_pag not in ('parcial', 'total'):
            tipo_pag = 'total'
        lancamento = LancamentoPagamento.objects.create(emprestimo=emp, metodo=metodo, valor_pago=valor, tipo_pagamento=tipo_pag, data_pagamento=p.get('data_pagamento') or timezone.localdate(), referencia=p.get('referencia', '').strip(), notas=p.get('notas', '').strip(), foto_comprovativo=foto, submetido_por=user, status='pendente')
        if metodo == 'dinheiro' and eh_staff:
            lancamento.validar(user)
            log('lancamento_validado', f'Pagamento dinheiro físico: {emp.nome}', f'{emp.numero_contrato} MT {float(valor):,.0f}', request)
            messages.success(request, f'✓ Pagamento de MT {float(valor):,.2f} registado e validado!')
        else:
            log('lancamento_submetido', f'Pagamento submetido ({lancamento.get_metodo_display()}): {emp.nome}', f'{emp.numero_contrato} MT {float(valor):,.0f} Ref:{lancamento.referencia}', request)
            messages.success(request, '✓ Pagamento submetido! Aguarda validação do gestor.')
        return redirect('lancamentos_lista', pk=pk)
    return render(request, 'osm/emprestimos/lancamento_form.html', {'emp': emp, 'eh_staff': eh_staff, 'hoje': timezone.localdate().isoformat(), 'total_a_pagar': emp.total_a_pagar, 'total_com_multa': emp.total_com_multa, 'tem_multa': emp.multa_valor > 0})

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_lancamento_validar(request, pk):
    from django.db import transaction
    if not request.user.pode_aprovar:
        messages.error(request, '⛔ Sem permissão para validar pagamentos.')
        emp_id = LancamentoPagamento.objects.filter(pk=pk).values_list('emprestimo_id', flat=True).first()
        return redirect('lancamentos_lista', pk=emp_id or 1)
    with transaction.atomic():
        try:
            lanc = LancamentoPagamento.objects.select_for_update().get(pk=pk, status='pendente')
        except LancamentoPagamento.DoesNotExist:
            messages.warning(request, 'Este lançamento já foi processado ou não existe.')
            lanc_any = LancamentoPagamento.objects.filter(pk=pk).first()
            if lanc_any:
                return redirect('lancamentos_lista', pk=lanc_any.emprestimo_id)
            return redirect('emprestimos')
        lanc.validar(request.user)
    lanc.refresh_from_db()
    emp = lanc.emprestimo
    emp.refresh_from_db()
    log('lancamento_validado', f'Pagamento validado: {emp.nome}', f'{emp.numero_contrato} MT {float(lanc.valor_pago):,.0f}', request)
    if emp.telefone:
        tipo_sms = 'quitado' if emp.pago else 'pagamento_parcial' if lanc.tipo_pagamento == 'parcial' else 'pagamento_confirmado'
        _auto_sms_emprestimo(emp, tipo_sms, request.user)
    b = ConfiguracaoBancaria.obter()
    if b.email_ativo and emp.cliente and emp.cliente.email:
        try:
            tipo_email = 'quitacao' if emp.pago else 'lembrete'
            enviar_cobranca_email(emp, tipo=tipo_email, request=request)
        except Exception:
            pass
    messages.success(request, f'✅ Pagamento de MT {float(lanc.valor_pago):,.2f} validado e aplicado! <a href="/lancamentos/{lanc.pk}/recibo/" target="_blank">Recibo</a> | <a href="/lancamentos/{lanc.pk}/fatura/" target="_blank">Fatura</a>')
    return redirect('lancamentos_lista', pk=emp.pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_lancamento_rejeitar(request, pk):
    lanc = get_object_or_404(LancamentoPagamento, pk=pk, status='pendente')
    motivo = request.POST.get('motivo', '').strip() or 'Não especificado'
    lanc.status = 'rejeitado'
    lanc.motivo_rejeicao = motivo
    lanc.validado_por = request.user
    lanc.data_validacao = timezone.now()
    lanc.save()
    log('lancamento_rejeitado', f'Pagamento rejeitado: {lanc.emprestimo.nome}', f'{lanc.emprestimo.numero_contrato} — {motivo}', request)
    messages.warning(request, f'Lançamento rejeitado: {motivo}')
    return redirect('emprestimo_detalhe', pk=lanc.emprestimo.pk)


# =============================================================================
# SOLICITAÇÕES PÚBLICAS
# =============================================================================
def view_solicitar_publico(request):
    if request.user.is_authenticated:
        if request.user.perfil == 'cliente':
            return redirect('portal_cliente')
        return redirect('painel')
    if request.method == 'POST':
        p = request.POST
        nome = p.get('nome_completo', '').strip()
        telefone = p.get('telefone', '').strip()
        finalidade = p.get('finalidade', '').strip()
        try:
            valor = Decimal(p.get('valor_pedido', '0') or '0')
        except Exception:
            valor = Decimal('0')
        erros = []
        if not nome:
            erros.append('Nome completo é obrigatório.')
        if not telefone:
            erros.append('Telefone é obrigatório.')
        if valor < 500:
            erros.append('Valor mínimo é MT 500.')
        if not finalidade:
            erros.append('Finalidade é obrigatória.')
        if erros:
            for e in erros:
                messages.error(request, e)
            return render(request, 'osm/cliente/solicitar_publico.html', {'valores': p})
        doc = request.FILES.get('documento_pdf')
        SolicitacaoPublica.objects.create(nome_completo=nome, email=p.get('email', '').strip(), telefone=telefone, bi=p.get('bi', '').strip(), nuit=p.get('nuit', '').strip(), bairro=p.get('bairro', '').strip(), estado_civil=p.get('estado_civil', '').strip(), valor_pedido=valor, finalidade=finalidade, garantia_desc=p.get('garantia_desc', '').strip(), documento_pdf=doc, ip_origem=get_ip(request))
        log('solicitacao_publica', f'Nova solicitação: {nome}', f'MT {float(valor):,.0f} — {telefone}')
        return redirect('solicitar_sucesso')
    return render(request, 'osm/cliente/solicitar_publico.html', {'valores': {}})

def view_solicitar_sucesso(request):
    return render(request, 'osm/cliente/solicitar_sucesso.html')

@login_required
@requer_perfil('superadmin', 'gestor')
def view_solicitacoes_lista(request):
    status_filtro = request.GET.get('status', '')
    qs = SolicitacaoPublica.objects.select_related('avaliado_por', 'utilizador_criado')
    if status_filtro:
        qs = qs.filter(status=status_filtro)
    total_subm = SolicitacaoPublica.objects.filter(status='submetido').count()
    total_analise = SolicitacaoPublica.objects.filter(status='em_analise').count()
    return render(request, 'osm/cliente/solicitacoes_lista.html', {'solicitacoes': qs, 'status_filtro': status_filtro, 'total_subm': total_subm, 'total_analise': total_analise})

@login_required
@requer_perfil('superadmin', 'gestor')
def view_solicitacao_detalhe(request, pk):
    sol = get_object_or_404(SolicitacaoPublica, pk=pk)
    return render(request, 'osm/cliente/solicitacao_detalhe.html', {'sol': sol})

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_solicitacao_em_analise(request, pk):
    sol = get_object_or_404(SolicitacaoPublica, pk=pk, status='submetido')
    sol.status = 'em_analise'
    sol.avaliado_por = request.user
    sol.save()
    log('solicitacao_analise', f'Em análise: {sol.nome_completo}', f'MT {float(sol.valor_pedido):,.0f}', request)
    messages.info(request, f'Solicitação de {sol.nome_completo} marcada como Em Análise.')
    return redirect('solicitacao_detalhe', pk=pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_solicitacao_aprovar(request, pk):
    if not request.user.pode_aprovar:
        messages.error(request, '⛔ Sem permissão para aprovar solicitações.')
        return redirect('solicitacao_detalhe', pk=pk)
    sol = get_object_or_404(SolicitacaoPublica, pk=pk)
    if sol.status == 'aprovado':
        messages.warning(request, 'Solicitação já aprovada.')
        return redirect('solicitacao_detalhe', pk=pk)
    try:
        valor = Decimal(request.POST.get('valor_aprovado') or str(sol.valor_pedido))
    except Exception:
        valor = sol.valor_pedido
    cfg = ConfiguracaoBancaria.obter()
    username_novo = gerar_username()
    senha_nova = gerar_senha()
    novo_user = Utilizador.objects.create_user(username=username_novo, first_name=sol.nome_completo.split()[0], last_name=' '.join(sol.nome_completo.split()[1:]), email=sol.email, telefone=sol.telefone, bi=sol.bi, nuit=sol.nuit, perfil='cliente', activo=True, deve_trocar_senha=True, senha_inicial=senha_nova, criado_por=request.user)
    novo_user.set_password(senha_nova)
    novo_user.save()
    novo_user.tipo_cliente = sol.tipo_cliente
    novo_user.save(update_fields=['tipo_cliente'])
    emp = Emprestimo.objects.create(cliente=novo_user, tipo_cliente=sol.tipo_cliente, nome=sol.nome_completo, telefone=sol.telefone, bi=sol.bi, nuit=sol.nuit, bairro=sol.bairro, estado_civil=sol.estado_civil, taxa_juros=cfg.taxa_juros_padrao, taxa_multa=cfg.taxa_multa_padrao, prazo_multa_dias=cfg.prazo_multa_dias, finalidade=sol.finalidade, garantia=sol.garantia_desc, status='ativo', registado_por=request.user, aprovado_por=request.user, data_aprovacao=timezone.now())
    Credito.objects.create(emprestimo=emp, valor=valor, taxa_juros=cfg.taxa_juros_padrao, taxa_multa=cfg.taxa_multa_padrao, prazo_multa_dias=cfg.prazo_multa_dias, data_inicio=emp.data_inicio, data_vencimento=emp.data_vencimento)
    sol.status = 'aprovado'
    sol.avaliado_por = request.user
    sol.nota_gestor = request.POST.get('nota_gestor', '').strip()
    sol.data_resposta = timezone.now()
    sol.utilizador_criado = novo_user
    sol.emprestimo_criado = emp
    sol.save()
    enviar_email_credenciais(novo_user, senha_nova)
    log('solicitacao_aprovada', f'Aprovada: {sol.nome_completo} → {username_novo}', f'{emp.numero_contrato} MT {float(valor):,.0f}', request)
    messages.success(request, f'✓ Solicitação aprovada! Utilizador: {username_novo} | Senha: {senha_nova} | Contrato: {emp.numero_contrato}')
    return redirect('solicitacao_detalhe', pk=pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_solicitacao_rejeitar(request, pk):
    sol = get_object_or_404(SolicitacaoPublica, pk=pk)
    motivo = request.POST.get('motivo', '').strip() or 'Não especificado'
    sol.status = 'rejeitado'
    sol.avaliado_por = request.user
    sol.motivo_rejeicao = motivo
    sol.data_resposta = timezone.now()
    sol.save()
    if sol.utilizador_criado:
        sol.utilizador_criado.bloqueado_ate = timezone.localdate()
        sol.utilizador_criado.save(update_fields=['bloqueado_ate'])
    log('solicitacao_rejeitada', f'Rejeitada: {sol.nome_completo}', f'Motivo: {motivo}', request)
    messages.warning(request, f'Solicitação de {sol.nome_completo} rejeitada.')
    return redirect('solicitacao_detalhe', pk=pk)


# =============================================================================
# LICENÇA DO SISTEMA
# =============================================================================
from .models import LicencaSistema

@login_required
@requer_perfil('superadmin')
def view_licenca_painel(request):
    codigo_valido = request.session.get('licenca_code_verified', False)
    if request.method == 'POST':
        codigo_digitado = request.POST.get('codigo_acesso')
        if codigo_digitado == '878572292':
            request.session['licenca_code_verified'] = True
            return redirect('licenca_painel')
        else:
            return render(request, 'osm/admin/licenca_painel.html', {'codigo_erro': True, 'show_modal': True, 'lic': None, 'historico': []})
    if not codigo_valido:
        return render(request, 'osm/admin/licenca_painel.html', {'show_modal': True, 'codigo_erro': False, 'lic': None, 'historico': []})
    lic = LicencaSistema.obter_ou_criar()
    lic.actualizar_estado()
    historico = LicencaSistema.objects.order_by('-data_emissao')[:10]
    return render(request, 'osm/admin/licenca_painel.html', {'show_modal': False, 'lic': lic, 'historico': historico})

@login_required
@requer_perfil('superadmin')
@require_POST
def view_licenca_renovar(request):
    lic = LicencaSistema.obter_ou_criar()
    nova = lic.renovar(utilizador=request.user)
    log('licenca_renovada', f'Licença renovada → código {nova.codigo}', f'Expira: {nova.data_expiracao:%d/%m/%Y}', request)
    messages.success(request, f'✓ Licença renovada! Novo código: {nova.codigo} · Válida até {nova.data_expiracao:%d/%m/%Y}')
    return redirect('licenca_painel')

@login_required
@requer_perfil('superadmin')
@require_POST
def view_licenca_pausar(request):
    lic = LicencaSistema.obter_ou_criar()
    if lic.estado in ('activa', 'alerta'):
        motivo = request.POST.get('motivo', 'Pausa manual pelo administrador').strip()
        lic.pausar(utilizador=request.user, motivo=motivo)
        log('licenca_pausada', f'Sistema pausado — código {lic.codigo}', motivo, request)
        messages.warning(request, f'⚠ Sistema pausado. Tens 7 dias para efectuar a cobrança mensal e renovar. Após {lic.pausa_expira:%d/%m/%Y %H:%M} o sistema será bloqueado.')
    else:
        messages.error(request, 'Não é possível pausar uma licença neste estado.')
    return redirect('licenca_painel')


# =============================================================================
# PWA — Service Worker, Manifest, Offline
# =============================================================================
def view_pwa_manifest(request):
    import json
    manifest = {
        "name": "OSM Microcrédito", "short_name": "OSM", "description": "Plataforma de gestão de microcrédito e empréstimos",
        "id": "osm-microcredito-v1", "start_url": "/painel/", "scope": "/", "display": "standalone",
        "display_override": ["window-controls-overlay", "standalone"], "background_color": "#0a1628",
        "theme_color": "#1565c0", "orientation": "portrait-primary", "lang": "pt",
        "icons": [
            {"src": "/static/images/logo/icon-72.png", "sizes": "72x72", "type": "image/png"},
            {"src": "/static/images/logo/icon-96.png", "sizes": "96x96", "type": "image/png"},
            {"src": "/static/images/logo/icon-128.png", "sizes": "128x128", "type": "image/png"},
            {"src": "/static/images/logo/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/images/logo/icon-192-maskable.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "/static/images/logo/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/static/images/logo/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "categories": ["finance", "business", "productivity"],
        "shortcuts": [
            {"name": "Painel", "url": "/painel/", "description": "Dashboard", "icons": [{"src": "/static/images/logo/icon-96.png", "sizes": "96x96"}]},
            {"name": "Empréstimos", "url": "/emprestimos/", "description": "Gestão de empréstimos", "icons": [{"src": "/static/images/logo/icon-96.png", "sizes": "96x96"}]},
            {"name": "Lançamentos", "url": "/painel/", "description": "Pagamentos pendentes", "icons": [{"src": "/static/images/logo/icon-96.png", "sizes": "96x96"}]},
        ]
    }
    return HttpResponse(json.dumps(manifest, ensure_ascii=False), content_type='application/manifest+json', headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

def view_offline(request):
    return render(request, 'osm/sistema/offline.html')


# =============================================================================
# RECIBO E FATURA — PDF após validação de pagamento
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_lancamento_recibo(request, pk):
    lanc = get_object_or_404(LancamentoPagamento, pk=pk, status='validado')
    buf = gerar_recibo(lanc)
    num = f'REC-{lanc.emprestimo.numero_contrato}-{lanc.pk:04d}'
    resp = HttpResponse(buf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{num}.pdf"'
    return resp

@login_required
@requer_perfil('superadmin', 'gestor')
def view_lancamento_fatura(request, pk):
    lanc = get_object_or_404(LancamentoPagamento, pk=pk, status='validado')
    buf = gerar_fatura(lanc)
    num = f'FAT-{lanc.emprestimo.numero_contrato}-{lanc.pk:04d}'
    resp = HttpResponse(buf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{num}.pdf"'
    return resp

@login_required
@requer_perfil('superadmin', 'gestor')
def view_lancamento_fatura_dupla(request, pk):
    lanc = get_object_or_404(LancamentoPagamento, pk=pk, status='validado')
    buf = gerar_fatura_dupla(lanc)
    num = f'DUP-{lanc.emprestimo.numero_contrato}-{lanc.pk:04d}'
    resp = HttpResponse(buf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{num}.pdf"'
    log('pdf_fatura_dupla', f'Fatura dupla: {lanc.emprestimo.nome}', lanc.emprestimo.numero_contrato, request)
    return resp

@login_required
@requer_perfil('superadmin', 'gestor')
def view_lancamento_recibo_pos(request, pk):
    lanc = get_object_or_404(LancamentoPagamento, pk=pk, status='validado')
    buf = gerar_recibo_pos(lanc)
    num = f'POS-{lanc.emprestimo.numero_contrato}-{lanc.pk:04d}'
    resp = HttpResponse(buf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{num}.pdf"'
    log('pdf_recibo_pos', f'Recibo POS: {lanc.emprestimo.nome}', lanc.emprestimo.numero_contrato, request)
    return resp

@login_required
@requer_perfil('superadmin', 'gestor')
def view_lancamento_fatura_turbohost(request, pk):
    lanc = get_object_or_404(LancamentoPagamento, pk=pk, status='validado')
    buf = gerar_fatura_turbohost(lanc)
    num = f'INV-{lanc.emprestimo.numero_contrato}-{lanc.pk:04d}'
    resp = HttpResponse(buf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{num}.pdf"'
    log('pdf_fatura_turbohost', f'Fatura Turbohost: {lanc.emprestimo.nome}', lanc.emprestimo.numero_contrato, request)
    return resp


# =============================================================================
# CONVERTER TIPO DE CLIENTE / LISTA NEGRA
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_converter_tipo_cliente(request, pk):
    u = get_object_or_404(Utilizador, pk=pk, perfil='cliente')
    novo_tipo = 'comerciante' if u.tipo_cliente == 'normal' else 'normal'
    u.tipo_cliente = novo_tipo
    u.save(update_fields=['tipo_cliente'])
    log('converter_tipo_cliente', f'Tipo alterado: {u.nome_completo}', f'{u.tipo_cliente}', request)
    messages.success(request, f'<i class="fa-solid fa-arrows-rotate"></i> Tipo de cliente alterado para {u.label_tipo_cliente}.')
    return redirect('utilizador_editar', pk=pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_lista_negra_toggle(request, pk):
    u = get_object_or_404(Utilizador, pk=pk, perfil='cliente')
    u.lista_negra = not u.lista_negra
    u.motivo_lista_negra = request.POST.get('motivo', '').strip()
    u.save(update_fields=['lista_negra', 'motivo_lista_negra'])
    estado = 'adicionado à lista negra' if u.lista_negra else 'removido da lista negra'
    log('lista_negra', f'{u.nome_completo} {estado}', u.motivo_lista_negra, request)
    messages.warning(request, f'<i class="fa-solid fa-ban"></i> {u.nome_completo} {estado}.')
    return redirect('utilizadores')


# =============================================================================
# PAGAMENTO PARCIAL
# =============================================================================
@login_required
def view_lancamento_parcial(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    user = request.user
    if emp.pago or emp.status == 'quitado':
        messages.error(request, 'Este empréstimo já está quitado.')
        return redirect('emprestimo_detalhe', pk=pk)
    if emp.status in ('pendente', 'rejeitado'):
        messages.error(request, 'Empréstimo pendente ou rejeitado.')
        return redirect('emprestimo_detalhe', pk=pk)
    eh_staff = user.perfil in ('superadmin', 'gestor') or user.is_superuser
    if request.method == 'POST':
        p = request.POST
        metodo = p.get('metodo', '')
        try:
            valor = Decimal(p.get('valor_pago', '0') or '0')
        except Exception:
            valor = Decimal('0')
        if valor <= 0:
            messages.error(request, 'Valor inválido.')
            return redirect('lancamento_parcial', pk=pk)
        saldo_atual = emp.saldo_restante if emp.saldo_restante is not None else emp.total_com_multa
        if valor > saldo_atual:
            messages.error(request, f'Valor ({float(valor):,.2f} MT) superior ao saldo devedor ({float(saldo_atual):,.2f} MT).')
            return redirect('lancamento_parcial', pk=pk)
        foto = request.FILES.get('foto_comprovativo')
        lancamento = LancamentoPagamento.objects.create(emprestimo=emp, metodo=metodo, valor_pago=valor, data_pagamento=p.get('data_pagamento') or timezone.localdate(), referencia=p.get('referencia', '').strip(), notas=p.get('notas', '').strip(), foto_comprovativo=foto, submetido_por=user, tipo_pagamento='parcial', status='pendente')
        if metodo == 'dinheiro' and eh_staff:
            lancamento.validar(user)
            saldo_novo = emp.saldo_restante
            log('pagamento_parcial', f'Parcial: {emp.nome}', f'{emp.numero_contrato} MT {float(valor):,.0f} | Saldo: MT {float(saldo_novo or 0):,.0f}', request)
            messages.success(request, f'<i class="fa-solid fa-check"></i> Pagamento parcial de MT {float(valor):,.2f} aplicado! Novo saldo: MT {float(saldo_novo or 0):,.2f}')
        else:
            log('parcial_submetido', f'Parcial submetido: {emp.nome}', f'{emp.numero_contrato} MT {float(valor):,.0f}', request)
            messages.success(request, '<i class="fa-solid fa-clock"></i> Pagamento parcial submetido! Aguarda validação.')
        return redirect('lancamentos_lista', pk=pk)
    saldo_atual = emp.saldo_restante if emp.saldo_restante is not None else emp.total_com_multa
    return render(request, 'osm/emprestimos/lancamento_parcial_form.html', {'emp': emp, 'eh_staff': eh_staff, 'hoje': timezone.localdate().isoformat(), 'saldo_atual': saldo_atual, 'mora_hoje': emp.mora_composta})


# =============================================================================
# ACÇÕES DE EMPRÉSTIMO — lista negra, tribunal, cancelar multa
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_emprestimo_lista_negra(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    if emp.cliente:
        motivo = request.POST.get('motivo', '').strip()
        emp.cliente.lista_negra = True
        emp.cliente.motivo_lista_negra = motivo
        emp.cliente.save(update_fields=['lista_negra', 'motivo_lista_negra'])
        log('lista_negra', f'{emp.nome} adicionado à lista negra', motivo, request)
        messages.warning(request, f'<i class="fa-solid fa-ban"></i> {emp.nome} adicionado à lista negra.')
    return redirect('emprestimo_detalhe', pk=pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_cancelar_multa(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    if not (request.user.pode_aprovar or getattr(request.user, 'perm_tribunal', False) or request.user.eh_superadmin):
        messages.error(request, '⛔ Sem permissão para cancelar multas.')
        return redirect('emprestimo_detalhe', pk=pk)
    motivo = request.POST.get('motivo', '').strip()
    if emp.multa_cancelada:
        emp.reativar_multa(request.user)
        log('multa_reativada', f'Multa reactivada: {emp.nome}', emp.numero_contrato, request)
        messages.success(request, f'✓ Multa reactivada para {emp.nome}.')
    else:
        emp.cancelar_multa(request.user, motivo)
        log('multa_cancelada', f'Multa cancelada: {emp.nome}', f'{emp.numero_contrato} — {motivo}', request)
        messages.success(request, f'✓ Multa cancelada para {emp.nome}. Mora zerada.')
    return redirect('emprestimo_detalhe', pk=pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_enviar_tribunal(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    if not (request.user.pode_aprovar or getattr(request.user, 'perm_tribunal', False) or request.user.eh_superadmin):
        messages.error(request, '⛔ Sem permissão para enviar para tribunal.')
        return redirect('emprestimo_detalhe', pk=pk)
    if emp.pago or emp.status == 'quitado':
        messages.warning(request, 'Empréstimo já quitado.')
        return redirect('emprestimo_detalhe', pk=pk)
    motivo = request.POST.get('motivo', '').strip()
    emp.enviar_para_tribunal(request.user, motivo)
    log('tribunal', f'Enviado para tribunal: {emp.nome}', f'{emp.numero_contrato} — {motivo}', request)
    messages.warning(request, f'⚖️ Caso de {emp.nome} enviado para tribunal. Mora congelada.')
    return redirect('emprestimo_detalhe', pk=pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_retirar_tribunal(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    emp.enviado_tribunal = False
    emp.multa_cancelada = False
    emp.motivo_cancelamento_multa = ''
    emp.save(update_fields=['enviado_tribunal', 'multa_cancelada', 'motivo_cancelamento_multa'])
    emp.atualizar_status_automatico()
    log('retirar_tribunal', f'Retirado do tribunal: {emp.nome}', emp.numero_contrato, request)
    messages.info(request, f'↩️ Caso de {emp.nome} retirado do tribunal. Cobrança retomada.')
    return redirect('emprestimo_detalhe', pk=pk)


# =============================================================================
# EMPRÉSTIMO SEM CONTA
# =============================================================================
@login_required
@requer_perfil('superadmin', 'gestor')
def view_emprestimo_sem_conta(request):
    if request.method == 'POST':
        from django.db import transaction
        p = request.POST
        cfg = ConfiguracaoBancaria.obter()
        try:
            valor = Decimal(p.get('valor', '0').replace(',', '.'))
            taxa_juros = Decimal(p.get('taxa_juros', str(cfg.taxa_juros_padrao)))
            taxa_multa = Decimal(p.get('taxa_multa', str(cfg.taxa_multa_padrao)))
            prazo_multa = int(p.get('prazo_multa_dias', cfg.prazo_multa_dias))
        except Exception:
            messages.error(request, 'Valores inválidos.')
            return redirect('emprestimo_sem_conta')
        with transaction.atomic():
            emp = Emprestimo.objects.create(cliente=None, tipo_cliente=p.get('tipo_cliente', 'normal'), nome=p.get('nome', '').strip(), nuit=p.get('nuit', '').strip(), bi=p.get('bi', '').strip(), telefone=p.get('telefone', '').strip(), estado_civil=p.get('estado_civil', '').strip(), bairro=p.get('bairro', '').strip(), empregador=p.get('empregador', '').strip(), nome_pai=p.get('nome_pai', '').strip(), nome_mae=p.get('nome_mae', '').strip(), sector=p.get('sector', 'Comercio'), taxa_juros=taxa_juros, taxa_multa=taxa_multa, prazo_multa_dias=prazo_multa, finalidade=p.get('finalidade', '').strip(), garantia=p.get('garantia', '').strip(), score=p.get('score', 'A'), data_inicio=p.get('data_inicio') or timezone.localdate(), status='pendente', registado_por=request.user)
            Credito.objects.create(emprestimo=emp, valor=valor, taxa_juros=taxa_juros, taxa_multa=taxa_multa, prazo_multa_dias=prazo_multa, data_inicio=emp.data_inicio, data_vencimento=emp.data_vencimento)
            log('emprestimo_sem_conta', f'Empréstimo sem conta: {emp.nome}', f'{emp.numero_contrato} MT {float(valor):,.0f}', request)
            messages.success(request, f'✓ Empréstimo {emp.numero_contrato} criado para {emp.nome} (sem conta). Pode criar conta depois em Utilizadores.')
            return redirect('emprestimo_detalhe', pk=emp.pk)
    cfg = ConfiguracaoBancaria.obter()
    return render(request, 'osm/emprestimos/emprestimo_sem_conta.html', {'cfg': cfg, 'hoje': timezone.localdate().isoformat()})

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_associar_conta(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk, cliente=None)
    uid = request.POST.get('utilizador_id', '').strip()
    if uid:
        try:
            u = Utilizador.objects.get(pk=uid, perfil='cliente')
            emp.cliente = u
            emp.save(update_fields=['cliente'])
            log('associar_conta', f'Conta associada: {emp.nome} → {u.nome_completo}', emp.numero_contrato, request)
            messages.success(request, f'✓ Conta de {u.nome_completo} associada ao empréstimo {emp.numero_contrato}.')
        except Utilizador.DoesNotExist:
            messages.error(request, 'Utilizador não encontrado.')
    return redirect('emprestimo_detalhe', pk=pk)

@login_required
@requer_perfil('superadmin', 'gestor')
@require_POST
def view_converter_tipo_emprestimo(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    novo_tipo = request.POST.get('tipo_cliente', emp.tipo_cliente)
    emp.tipo_cliente = novo_tipo
    emp.save(update_fields=['tipo_cliente'])
    if emp.cliente:
        emp.cliente.tipo_cliente = novo_tipo
        emp.cliente.save(update_fields=['tipo_cliente'])
    log('converter_tipo_emprestimo', f'Tipo alterado: {emp.nome} → {novo_tipo}', emp.numero_contrato, request)
    messages.success(request, f'✓ Tipo de cliente alterado para {"Comerciante" if novo_tipo == "comerciante" else "Normal"}.')
    return redirect('emprestimo_detalhe', pk=pk)


# =============================================================================
# VERIFICAÇÃO DE CÓDIGO ADMIN
# =============================================================================
def view_verificar_codigo_admin(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if not getattr(request.user, 'eh_superadmin', False):
        return redirect('painel')
    erro = False
    if request.method == 'POST':
        codigo = request.POST.get('codigo', '').strip()
        if codigo == '878572292':
            request.session['codigo_superadmin_ok'] = True
            return redirect('licenca_painel')
        else:
            erro = True
    return render(request, 'osm/auth/verificar_codigo_admin.html', {'erro': erro})


# =============================================================================
# API PARCELA POR DATA E REDIRECIONAMENTO LEGADO
# =============================================================================
def detalhes_parcela_por_data(request, comerciante_id):
    from decimal import Decimal
    com = get_object_or_404(Comerciante, pk=comerciante_id)
    data_str = request.GET.get('data')
    if not data_str:
        return JsonResponse({'error': 'Data não fornecida'}, status=400)
    try:
        data = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Formato de data inválido'}, status=400)
    delta = (data - com.data_inicio).days
    if delta < 0 or delta >= com.prazo_dias:
        return JsonResponse({'error': 'Data fora do período do contrato'}, status=400)
    numero_periodo = delta + 1
    valor_parcela = float(com.parcela_atual)
    ja_pago = com.ja_pagou_data(data)
    periodos_atr = max(0, com.periodos_em_atraso) if not ja_pago else 0
    multa = float(com.multa_parcela_em_atraso) if periodos_atr > 0 else 0
    valor_total = valor_parcela + multa
    return JsonResponse({'data': data_str, 'numero_periodo': numero_periodo, 'total_periodos': com.total_periodos, 'valor_parcela': round(valor_parcela,2), 'multa': round(multa,2), 'valor_total': round(valor_total,2), 'ja_pago': ja_pago, 'modalidade': com.modalidade_pagamento})

def confirmar_pagamento_data(request, comerciante_id):
    return view_confirmar_pagamento(request, pk=comerciante_id)






# =============================================================================
# CRÉDITOS – HTMX (substitui o modal)
# =============================================================================

@login_required
@requer_perfil('superadmin', 'gestor')
def creditos_lista(request, pk):
    """Retorna apenas o fragmento HTML da lista de créditos (para HTMX)."""
    emp = get_object_or_404(Emprestimo, pk=pk)
    creditos = emp.creditos.filter(deleted_at__isnull=True).order_by('-data_inicio')
    creditos_activos = [c for c in creditos if not c.esta_quitado]
    creditos_quitados = [c for c in creditos if c.esta_quitado]
    return render(request, 'osm/includes/creditos_lista.html', {
        'emp': emp,
        'creditos_activos': creditos_activos,
        'creditos_quitados': creditos_quitados,
    })

@login_required
@requer_perfil('superadmin', 'gestor')
def creditos_lista_comerciantes(request, pk):
    """Retorna apenas o fragmento HTML da lista de créditos (para HTMX)."""
    emp = get_object_or_404(Emprestimo, pk=pk)
    creditos = emp.creditos.filter(deleted_at__isnull=True).order_by('-data_inicio')
    creditos_activos = [c for c in creditos if not c.esta_quitado]
    creditos_quitados = [c for c in creditos if c.esta_quitado]
    return render(request, 'osm/includes/creditos_comerciante_lista.html', {
        'emp': emp,
        'creditos_activos': creditos_activos,
        'creditos_quitados': creditos_quitados,
    })

@login_required
@requer_perfil('superadmin', 'gestor')
def adicionar_credito_form(request, pk):
    """Retorna o formulário para adicionar crédito (HTMX)."""
    emp = get_object_or_404(Emprestimo, pk=pk)
    return render(request, 'osm/includes/credito_form.html', {'emp': emp})

@login_required
@requer_perfil('superadmin', 'gestor')
def adicionar_credito(request, pk):
    """
    Processa o formulário de adição de crédito.
    Se for HTMX, retorna a lista actualizada; senão, redirecciona para o detalhe.
    """
    emp = get_object_or_404(Emprestimo, pk=pk)
    if request.method == 'POST':
        try:
            valor = Decimal(request.POST.get('valor', '0'))
            taxa_juros = Decimal(request.POST.get('taxa_juros', '30'))
            taxa_multa = Decimal(request.POST.get('taxa_multa', '2'))
            prazo_multa_dias = int(request.POST.get('prazo_multa_dias', 5))
            data_inicio_str = request.POST.get('data_inicio')
            data_vencimento_str = request.POST.get('data_vencimento')
            
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else timezone.localdate()
            data_vencimento = datetime.strptime(data_vencimento_str, '%Y-%m-%d').date() if data_vencimento_str else None
            
            Credito.objects.create(
                emprestimo=emp,
                valor=valor,
                taxa_juros=taxa_juros,
                taxa_multa=taxa_multa,
                prazo_multa_dias=prazo_multa_dias,
                data_inicio=data_inicio,
                data_vencimento=data_vencimento,
                pago=False,
                # Os campos calculados (juros, multa) serão geridos pelo método save() do modelo
            )
            messages.success(request, f'✅ Crédito de MT {valor:,.2f} adicionado com sucesso!')
            log('adicionar_credito', f'Novo crédito: {emp.nome}', f'{emp.numero_contrato} MT {valor:,.2f}', request)
        except Exception as e:
            messages.error(request, f'❌ Erro ao adicionar crédito: {str(e)}')
    
    # Se for requisição HTMX, devolve a lista actualizada
    if request.headers.get('HX-Request'):
        return creditos_lista(request, pk)
    
    # Fallback para POST normal (não HTMX)
    return redirect('emprestimo_detalhe', pk=emp.pk)


@login_required
@requer_perfil('superadmin', 'gestor')
def creditos_detalhe_ajax(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk)
    creditos = emp.creditos.filter(deleted_at__isnull=True).order_by('-data_inicio')
    return render(request, 'osm/includes/creditos_detalhe_ajax.html', {'creditos': creditos, 'emp': emp})

