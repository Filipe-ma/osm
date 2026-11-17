from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Q
from .models import (
    Utilizador, Emprestimo, Credito, Pagamento, Comerciante, PagamentoDiario,
    LogActividade, LogSMS, ConfiguracaoBancaria, FotoGarantia, RequisicaoCliente,
    LancamentoPagamento, SolicitacaoPublica, LicencaSistema
)


# ====================== AÇÕES PERSONALIZADAS ======================
def restaurar_selecionados(modeladmin, request, queryset):
    """Restaura registos marcados como deletados (deleted_at não nulo)."""
    count = queryset.filter(deleted_at__isnull=False).update(deleted_at=None)
    modeladmin.message_user(request, f'{count} registo(s) restaurado(s).')
restaurar_selecionados.short_description = 'Restaurar registos seleccionados'


def marcar_como_eliminado(modeladmin, request, queryset):
    """Marca registos como deletados (soft delete) em vez de apagar fisicamente."""
    from django.utils import timezone
    count = queryset.filter(deleted_at__isnull=True).update(deleted_at=timezone.now())
    modeladmin.message_user(request, f'{count} registo(s) marcado(s) como eliminado(s).')
marcar_como_eliminado.short_description = 'Marcar como eliminado (soft delete)'


# ====================== ADMIN ======================
@admin.register(Utilizador)
class UtilizadorAdmin(admin.ModelAdmin):
    list_display = ('username', 'nome_completo', 'email', 'perfil', 'tipo_cliente', 'lista_negra', 'activo', 'pode_solicitar_icon', 'data_registo')
    list_filter = ('perfil', 'tipo_cliente', 'lista_negra', 'activo', 'deleted_at')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'telefone')
    readonly_fields = ('data_registo', 'last_login', 'ultimo_login_ip', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]
    fieldsets = (
        ('Credenciais', {
            'fields': ('username', 'password', 'deve_trocar_senha', 'senha_inicial')
        }),
        ('Informação Pessoal', {
            'fields': ('first_name', 'last_name', 'email', 'telefone', 'nuit', 'bi', 'cargo', 'data_nasc')
        }),
        ('Endereço', {
            'fields': ('bairro', 'distrito', 'provincia')
        }),
        ('Permissões', {
            'fields': ('perfil', 'tipo_cliente', 'lista_negra', 'activo', 'is_staff', 'is_superuser',
                       'perm_aprovar', 'perm_eliminar', 'perm_sms', 'perm_exportar',
                       'perm_comerciantes', 'perm_relatorios', 'limite_emprestimo')
        }),
        ('Auditoria', {
            'fields': ('criado_por', 'data_registo', 'last_login', 'ultimo_login_ip', 'deleted_at')
        }),
    )

    def nome_completo(self, obj):
        return obj.nome_completo
    nome_completo.short_description = 'Nome'
    nome_completo.admin_order_field = ('first_name', 'last_name')

    def pode_solicitar_icon(self, obj):
        if obj.pode_solicitar:
            return format_html('<span style="color:green;">✓</span>')
        return format_html('<span style="color:red;">✗</span>')
    pode_solicitar_icon.short_description = 'Pode solicitar?'


@admin.register(Credito)
class CreditoAdmin(admin.ModelAdmin):
    list_display = ('id', 'emprestimo', 'comerciante', 'valor', 'total_a_pagar', 'saldo_restante', 'esta_quitado_icon', 'data_vencimento', 'deleted_at')
    list_filter = ('pago', 'multa_cancelada', 'enviado_tribunal', 'deleted_at')
    search_fields = ('emprestimo__numero_contrato', 'comerciante__numero_contrato')
    readonly_fields = ('deleted_at',)
    actions = [restaurar_selecionados, marcar_como_eliminado]
    fieldsets = (
        ('Associação', {
            'fields': ('emprestimo', 'comerciante')
        }),
        ('Valores', {
            'fields': ('valor', 'taxa_juros', 'taxa_multa', 'prazo_multa_dias')
        }),
        ('Pagamentos', {
            'fields': ('total_pago_parcial', 'saldo_restante', 'data_ultimo_pagamento', 'pago', 'data_pagamento')
        }),
        ('Controlo de Multa/Tribunal', {
            'fields': ('multa_cancelada', 'motivo_cancelamento_multa', 'cancelamento_multa_por',
                       'enviado_tribunal', 'data_envio_tribunal', 'enviado_tribunal_por')
        }),
        ('Datas', {
            'fields': ('data_inicio', 'data_vencimento')
        }),
        ('Auditoria', {
            'fields': ('deleted_at',)
        }),
    )

    def total_a_pagar(self, obj):
        return obj.total_a_pagar
    total_a_pagar.short_description = 'Total a pagar (sem multa)'

    def esta_quitado_icon(self, obj):
        if obj.esta_quitado:
            return format_html('<span style="color:green;">Quitado</span>')
        return format_html('<span style="color:red;">Em dívida</span>')
    esta_quitado_icon.short_description = 'Situação'


@admin.register(Emprestimo)
class EmprestimoAdmin(admin.ModelAdmin):
    list_display = ('numero_contrato', 'nome', 'valor', 'total_a_pagar', 'total_com_multa', 'status', 'esta_quitado_icon', 'score', 'data_vencimento')
    list_filter = ('status', 'score', 'sector', 'provincia', 'deleted_at')
    search_fields = ('numero_contrato', 'nome', 'telefone', 'nuit')
    readonly_fields = ('data_registo', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]
    fieldsets = (
        ('Cliente', {
            'fields': ('cliente', 'nome', 'nuit', 'bi', 'telefone', 'bairro', 'distrito', 'provincia')
        }),
        ('Dados do Empréstimo', {
            'fields': ('sector', 'finalidade', 'garantia', 'score')
        }),
        ('Documentos', {
            'fields': ('data_emissao_bi', 'local_emissao_bi', 'estado_civil',
                       'nome_pai', 'nome_mae', 'empregador')
        }),
        ('Datas e Estado', {
            'fields': ('data_inicio', 'data_vencimento', 'status', 'registado_por', 'aprovado_por',
                       'data_aprovacao', 'motivo_rejeicao', 'data_registo', 'deleted_at')
        }),
    )

    def valor(self, obj):
        return obj.valor
    valor.short_description = 'Valor total do crédito'

    def total_a_pagar(self, obj):
        return obj.total_a_pagar
    total_a_pagar.short_description = 'Total a pagar (sem multa)'

    def total_com_multa(self, obj):
        return obj.total_com_multa
    total_com_multa.short_description = 'Total com multa'

    def esta_quitado_icon(self, obj):
        if obj.esta_quitado:
            return format_html('<span style="color:green;">Quitado</span>')
        return format_html('<span style="color:red;">Em dívida</span>')
    esta_quitado_icon.short_description = 'Situação'


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = ('credito', 'valor_total', 'data_pagamento', 'registado_por', 'deleted_at')
    list_filter = ('data_pagamento', 'deleted_at')
    search_fields = ('credito__emprestimo__nome', 'credito__emprestimo__numero_contrato', 'credito__comerciante__nome')
    readonly_fields = ('criado_em', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]
    fieldsets = (
        ('Crédito', {
            'fields': ('credito',)
        }),
        ('Valores', {
            'fields': ('valor_capital', 'valor_juros', 'valor_multa', 'valor_total', 'custo_sms')
        }),
        ('Detalhes', {
            'fields': ('dias_atraso', 'observacoes', 'registado_por', 'data_pagamento')
        }),
        ('Auditoria', {
            'fields': ('criado_em', 'deleted_at')
        }),
    )


@admin.register(Comerciante)
class ComercianteAdmin(admin.ModelAdmin):
    list_display = ('numero_contrato', 'nome', 'capital', 'total_a_pagar', 'total_restante', 'status', 'esta_quitado_icon', 'periodos_em_atraso', 'data_inicio')
    list_filter = ('tipo_comercio', 'modalidade_pagamento', 'deleted_at')
    search_fields = ('numero_contrato', 'nome', 'telefone')
    readonly_fields = ('criado_em', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]
    fieldsets = (
        ('Informação', {
            'fields': ('cliente', 'nome', 'tipo_comercio', 'nuit', 'bi', 'telefone', 'bairro')
        }),
        ('Capital e Garantia', {
            'fields': ('garantia',)
        }),
        ('Taxas e Prazos', {
            'fields': ('prazo_dias', 'modalidade_pagamento')
        }),
        ('Pagamentos', {
            'fields': ('data_ultimo_pagamento',)
        }),
        ('Controlo', {
            'fields': ('registado_por', 'data_inicio', 'criado_em', 'deleted_at')
        }),
    )

    def capital(self, obj):
        return obj.capital
    capital.short_description = 'Capital'

    def total_a_pagar(self, obj):
        return obj.total_a_pagar
    total_a_pagar.short_description = 'Total a pagar'

    def total_restante(self, obj):
        return obj.total_restante
    total_restante.short_description = 'Saldo restante'

    def status(self, obj):
        return obj.status
    status.short_description = 'Estado'

    def esta_quitado_icon(self, obj):
        if obj.esta_quitado:
            return format_html('<span style="color:green;">Quitado</span>')
        return format_html('<span style="color:red;">Em dívida</span>')
    esta_quitado_icon.short_description = 'Situação'

    def periodos_em_atraso(self, obj):
        return obj.periodos_em_atraso
    periodos_em_atraso.short_description = 'Períodos em atraso'


@admin.register(PagamentoDiario)
class PagamentoDiarioAdmin(admin.ModelAdmin):
    list_display = ('comerciante', 'data', 'valor_pago', 'registado_por', 'deleted_at')
    list_filter = ('data', 'deleted_at')
    search_fields = ('comerciante__nome',)
    readonly_fields = ('criado_em', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]


@admin.register(LogActividade)
class LogActividadeAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'descricao', 'utilizador', 'criado_em', 'deleted_at')
    list_filter = ('tipo', 'criado_em', 'deleted_at')
    search_fields = ('descricao', 'detalhe')
    readonly_fields = ('criado_em', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]


@admin.register(LogSMS)
class LogSMSAdmin(admin.ModelAdmin):
    list_display = ('nome', 'telefone', 'status', 'criado_em', 'deleted_at')
    list_filter = ('status', 'criado_em', 'deleted_at')
    search_fields = ('nome', 'telefone', 'mensagem')
    readonly_fields = ('criado_em', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]


@admin.register(ConfiguracaoBancaria)
class ConfiguracaoBancariaAdmin(admin.ModelAdmin):
    list_display = ('banco', 'conta', 'nib', 'titular', 'atualizado_em')
    readonly_fields = ('atualizado_em',)


@admin.register(FotoGarantia)
class FotoGarantiaAdmin(admin.ModelAdmin):
    list_display = ('emprestimo', 'foto', 'deleted_at')
    search_fields = ('emprestimo__nome',)
    readonly_fields = ('criado_em', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]


@admin.register(RequisicaoCliente)
class RequisicaoClienteAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'valor_pedido', 'status', 'data_requisicao', 'deleted_at')
    list_filter = ('status', 'data_requisicao', 'deleted_at')
    search_fields = ('cliente__nome_completo',)
    readonly_fields = ('data_requisicao', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]


@admin.register(LancamentoPagamento)
class LancamentoPagamentoAdmin(admin.ModelAdmin):
    list_display = ('emprestimo', 'metodo', 'valor_pago', 'data_pagamento', 'status', 'submetido_por', 'criado_em', 'deleted_at')
    list_filter = ('status', 'metodo', 'criado_em', 'deleted_at')
    search_fields = ('emprestimo__numero_contrato', 'emprestimo__nome', 'referencia')
    readonly_fields = ('criado_em', 'data_validacao', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]


@admin.register(SolicitacaoPublica)
class SolicitacaoPublicaAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'telefone', 'valor_pedido', 'status', 'data_submissao', 'avaliado_por', 'deleted_at')
    list_filter = ('status', 'data_submissao', 'deleted_at')
    search_fields = ('nome_completo', 'telefone', 'bi', 'nuit', 'email')
    readonly_fields = ('data_submissao', 'ip_origem', 'deleted_at')
    actions = [restaurar_selecionados, marcar_como_eliminado]


@admin.register(LicencaSistema)
class LicencaSistemaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'estado', 'data_emissao', 'data_expiracao', 'dias_restantes', 'renovada_por')
    list_filter = ('estado',)
    readonly_fields = ('codigo', 'criada_em', 'actualizada_em', 'renovacoes', 'dias_restantes')

    def dias_restantes(self, obj):
        return f"{obj.dias_restantes} dias"
    dias_restantes.short_description = 'Dias Restantes'