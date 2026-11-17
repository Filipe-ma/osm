"""
OSM Microcrédito v3 — Template Tags Centralizadas
Formatação consistente em todos os templates.
"""
from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def fmt_mt(value):
    """Formata valor em MT — consistente em todos os templates."""
    try:
        v = float(value)
        if v >= 1_000_000:
            return f'{v/1_000_000:.1f}M MT'
        if v >= 1_000:
            return f'{v:,.0f} MT'
        return f'{v:.2f} MT'
    except (TypeError, ValueError):
        return f'{value} MT'


@register.filter
def fmt_mt_full(value):
    """Formata valor com 2 casas decimais."""
    try:
        return f'{float(value):,.2f} MT'
    except (TypeError, ValueError):
        return f'{value} MT'


@register.filter
def status_badge(status):
    """Classe CSS por status — consistente em todos os templates."""
    mapa = {
        'ativo':         'badge-ativo',
        'vencido':       'badge-vencido',
        'quitado':       'badge-quitado',
        'pendente':      'badge-pendente',
        'incumprimento': 'badge-tribunal',
        'rejeitado':     'badge-rejeitado',
        'atraso':        'badge-vencido',
        'validado':      'badge-quitado',
        'em_analise':    'badge-pendente',
        'submetido':     'badge-pendente',
        'aprovado':      'badge-quitado',
    }
    return mapa.get(status, 'badge-default')


@register.filter
def status_label(status):
    """Label legível por status."""
    mapa = {
        'ativo':         'Ativo',
        'vencido':       'Vencido',
        'quitado':       'Quitado',
        'pendente':      'Pendente',
        'incumprimento': 'Caso de Tribunal',
        'rejeitado':     'Rejeitado',
        'atraso':        'Em Atraso',
        'validado':      'Validado',
        'em_analise':    'Em Análise',
        'submetido':     'Submetido',
        'aprovado':      'Aprovado',
        'diario':        'Diário',
        'semanal':       'Semanal',
        'normal':        'Cliente Normal',
        'comerciante':   'Comerciante',
    }
    return mapa.get(status, status.capitalize() if status else '')


@register.filter
def tipo_cliente_icon(tipo):
    """Ícone Font Awesome por tipo de cliente."""
    if tipo == 'comerciante':
        return 'fa-solid fa-store'
    return 'fa-solid fa-user'


@register.filter
def pagamento_status_class(status):
    """Classe CSS para estado do pagamento."""
    mapa = {
        'validado':  'status-confirmado',
        'rejeitado': 'status-rejeitado',
        'pendente':  'status-pendente',
    }
    return mapa.get(status, '')


@register.simple_tag
def mora_exemplo(saldo, taxa_dia=2, dias=1):
    """Calcula mora composta para exibição no template."""
    try:
        s = float(saldo)
        t = float(taxa_dia) / 100
        return round(s * ((1 + t) ** int(dias)) - s, 2)
    except (TypeError, ValueError):
        return 0


# ── VALOR POR EXTENSO (Português de Moçambique) ──────────────────────────────
def _num_por_extenso(n):
    """Converte inteiro (0–999.999.999) para extenso em português."""
    if n == 0:
        return 'zero'
    unidades = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis',
                'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze',
                'catorze', 'quinze', 'dezasseis', 'dezassete', 'dezoito', 'dezanove']
    dezenas  = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta',
                'sessenta', 'setenta', 'oitenta', 'noventa']
    centenas = ['', 'cem', 'duzentos', 'trezentos', 'quatrocentos',
                'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']

    def _centena(x):
        if x == 0:
            return ''
        if x == 100:
            return 'cem'
        partes = []
        c = x // 100
        resto = x % 100
        if c:
            partes.append('cento' if c == 1 else centenas[c])
        if resto < 20:
            if resto:
                partes.append(unidades[resto])
        else:
            d = dezenas[resto // 10]
            u = unidades[resto % 10]
            partes.append(d + (' e ' + u if u else ''))
        return ' e '.join(partes)

    partes = []
    milhoes = n // 1_000_000
    resto   = n % 1_000_000
    milhar  = resto // 1_000
    resto   = resto % 1_000

    if milhoes:
        ext = _centena(milhoes)
        partes.append(ext + (' milhão' if milhoes == 1 else ' milhões'))
    if milhar:
        ext = _centena(milhar)
        partes.append(ext + (' mil' if ext else 'mil'))
    if resto:
        partes.append(_centena(resto))

    return ' e '.join(partes)


@register.filter
def por_extenso(value):
    """
    Converte um valor numérico (Decimal, float, int) para extenso em PT-MZ.
    Ex: 12500.50 → "doze mil e quinhentos meticais e cinquenta centavos"
    """
    try:
        from decimal import Decimal as D
        v   = D(str(value)).quantize(D('0.01'))
        int_part  = int(v)
        cent_part = int(round((v - int_part) * 100))

        resultado = _num_por_extenso(int_part)
        resultado += ' metical' if int_part == 1 else ' meticais'
        if cent_part:
            resultado += ' e ' + _num_por_extenso(cent_part)
            resultado += ' centavo' if cent_part == 1 else ' centavos'
        return resultado.capitalize()
    except Exception:
        return str(value)


@register.filter
def attr(obj, attr_name):
    """Retorna o valor do atributo/campo de um objecto por nome (string)."""
    try:
        return getattr(obj, attr_name, False)
    except Exception:
        return False


@register.filter
def progresso_cor(status):
    """Cor da barra de progresso por status do contrato."""
    return {
        'quitado':       '#2e7d32',
        'atraso':        '#c62828',
        'incumprimento': '#b71c1c',
        'ativo':         '#1565c0',
    }.get(status, '#1565c0')
