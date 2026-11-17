"""
OSM Microcrédito v5 — Services Layer (centralizado)
Adaptado para modelos com Credito (Emprestimo e Comerciante delegam).
Toda a lógica de negócio permanece em Python.
"""
from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum, Count, Q, OuterRef, Subquery
from django.core.cache import cache
from django.utils import timezone


def calcular_kpis():
    """
    KPIs centralizados com cache de 5 minutos.
    Adaptado para usar modelos Credito, Emprestimo, Comerciante.
    """
    kpis = cache.get('kpis_dashboard')
    if kpis:
        return kpis

    from .models import (Emprestimo, Utilizador, Pagamento,
                         Comerciante, ConfiguracaoBancaria, Credito)

    hoje = date.today()

    # ------------------------------------------------------------------
    # 1. Actualização de estado automática (apenas empréstimos com créditos não quitados)
    #    Evita loop individual usando bulk update? Como o status depende de lógica complexa,
    #    mantemos loop mas apenas para os que realmente precisam.
    # ------------------------------------------------------------------
    emps_a_atualizar = Emprestimo.active_objects.filter(
        Q(status__in=['ativo', 'vencido', 'incumprimento']),
        Q(data_vencimento__lte=hoje) | Q(creditos__pago=False),
    ).distinct()
    for emp in emps_a_atualizar:
        emp.atualizar_status_automatico()

    # ------------------------------------------------------------------
    # 2. Métricas baseadas em Créditos (não em Emprestimo directamente)
    # ------------------------------------------------------------------
    # Soma do capital dos créditos activos (que pertencem a empréstimos não quitados)
    carteira = Credito.active_objects.filter(
        emprestimo__isnull=False,
        pago=False,
        emprestimo__status__in=['ativo', 'vencido', 'incumprimento']
    ).aggregate(t=Sum('valor'))['t'] or Decimal('0')

    # Contagem de empréstimos por status (usando active_objects)
    total_emp = Emprestimo.active_objects.count()
    vencidos = Emprestimo.active_objects.filter(status='vencido').count()
    incump = Emprestimo.active_objects.filter(status='incumprimento').count()
    ativos = Emprestimo.active_objects.filter(status='ativo', pago=False).count()
    quitados = Emprestimo.active_objects.filter(status='quitado').count()
    pendentes = Emprestimo.active_objects.filter(status='pendente').count()

    # Mora total acumulada: soma da mora de todos os créditos em atraso/incumprimento
    # Isto é mais eficiente do que iterar sobre empréstimos e somar property.
    mora_total = Credito.active_objects.filter(
        Q(emprestimo__status='vencido') | Q(emprestimo__status='incumprimento'),
        pago=False
    ).aggregate(t=Sum('mora_composta'))['t'] or Decimal('0')
    mora_total = float(mora_total)

    # ------------------------------------------------------------------
    # 3. Juros do mês corrente (via Pagamento.credito)
    # ------------------------------------------------------------------
    mes_ini = hoje.replace(day=1)
    juros_mes = Pagamento.active_objects.filter(
        data_pagamento__gte=mes_ini
    ).aggregate(t=Sum('valor_juros'))['t'] or Decimal('0')

    # ------------------------------------------------------------------
    # 4. Comerciantes – contar status via property é pesado.
    #    Idealmente adicionar um campo 'status' no modelo Comerciante e actualizar periodicamente.
    #    Por enquanto, usamos iteração, mas apenas uma vez e com cache.
    # ------------------------------------------------------------------
    comerciantes_total = Comerciante.active_objects.count()
    comerciantes_atraso = 0
    comerciantes_incum = 0
    for c in Comerciante.active_objects.prefetch_related('creditos'):
        if c.status == 'atraso':
            comerciantes_atraso += 1
        elif c.status == 'incumprimento':
            comerciantes_incum += 1

    # ------------------------------------------------------------------
    # 5. Utilizadores (clientes) – usar active_objects
    # ------------------------------------------------------------------
    cfg = ConfiguracaoBancaria.obter()

    kpis = {
        'carteira':           float(carteira),
        'em_atraso':          vencidos + incump,
        'vencidos':           vencidos,
        'incumprimento':      incump,
        'pct_atraso':         round((vencidos + incump) / max(total_emp, 1) * 100, 1),
        'total_contratos':    total_emp,
        'quitados':           quitados,
        'pendentes':          pendentes,
        'mora_total':         round(mora_total, 2),
        'multa_total':        round(mora_total, 2),

        'emprestimos_ativos': ativos,
        'juros_total_mes':    float(juros_mes),

        'total_gestores':         Utilizador.active_objects.filter(perfil='gestor', activo=True).count(),
        'total_superadmins':      Utilizador.active_objects.filter(perfil='superadmin', activo=True).count(),
        'total_funcionarios':     Utilizador.active_objects.filter(perfil__in=['gestor', 'superadmin'], activo=True).count(),
        'clientes_ativos':        Utilizador.active_objects.filter(perfil='cliente', activo=True).count(),
        'total_clientes_normais': Utilizador.active_objects.filter(perfil='cliente', tipo_cliente='normal', activo=True).count(),
        'total_comerciantes_cli': Utilizador.active_objects.filter(perfil='cliente', tipo_cliente='comerciante', activo=True).count(),

        'total_comerciantes':     comerciantes_total,
        'comerciantes_atraso':    comerciantes_atraso,
        'comerciantes_incum':     comerciantes_incum,

        'taxa_juros_padrao': float(cfg.taxa_juros_padrao),
        'taxa_multa_padrao': float(cfg.taxa_multa_padrao),
        'prazo_multa_dias':  cfg.prazo_multa_dias,
    }
    cache.set('kpis_dashboard', kpis, 300)  # 5 minutos
    return kpis


def calcular_saldo_devedor(emprestimo):
    """Saldo devedor total do empréstimo (inclui mora de todos os créditos)."""
    if emprestimo.esta_quitado:
        return Decimal('0')
    return emprestimo.total_com_multa


def calcular_relatorio_periodo(dini, dfim):
    """
    Relatório financeiro para um período.
    Adaptado para usar Pagamento -> Credito -> Emprestimo.
    Nota: Inclui apenas pagamentos validados (status='validado' em LancamentoPagamento,
    mas aqui usamos o modelo Pagamento que já regista pagamentos efectivos).
    """
    from .models import Pagamento, Emprestimo, Credito

    pagamentos = Pagamento.active_objects.filter(
        data_pagamento__gte=dini, data_pagamento__lte=dfim
    )

    # Novos empréstimos criados no período (data_registo)
    novos = Emprestimo.active_objects.filter(
        data_registo__date__gte=dini, data_registo__date__lte=dfim
    )
    # Valor total dos novos empréstimos = soma dos créditos associados
    valor_novos = Credito.active_objects.filter(
        emprestimo__in=novos
    ).aggregate(t=Sum('valor'))['t'] or Decimal('0')

    # Contratos quitados no período: empréstimos cujo último pagamento foi na data e estão quitados
    quitados = Emprestimo.active_objects.filter(
        status='quitado',
        data_pagamento__gte=dini, data_pagamento__lte=dfim
    )

    return {
        'total_recebido':   pagamentos.aggregate(t=Sum('valor_total'))['t'] or Decimal('0'),
        'juros_recebidos':  pagamentos.aggregate(t=Sum('valor_juros'))['t'] or Decimal('0'),
        'multa_recebida':   pagamentos.aggregate(t=Sum('valor_multa'))['t'] or Decimal('0'),
        'receita_sms':      pagamentos.aggregate(t=Sum('custo_sms'))['t'] or Decimal('0'),
        'novos_emprestimos': novos.count(),
        'valor_novos':      valor_novos,
        'contratos_quitados': quitados.count(),
        'num_pagamentos':   pagamentos.count(),
    }