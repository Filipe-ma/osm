"""
OSM Microcrédito v5.0 — Modelos de Dados (VERSÃO COMPLETA COM CRÉDITO UNIVERSAL)
v5.0: Modelo Credito introduzido para Emprestimo e Comerciante (1:N).
      Ambos os modelos mantêm TODOS os métodos/propriedades originais (v3.4),
      agora delegando para os seus créditos.
      Validadores: BI (12 números + 1 letra), NUIT (9 números), Telefone (9 dígitos).
      Soft delete em todos os modelos. Multa calculada como JUROS SIMPLES.
      Auto incremento de contratos: OSM-ANO-NNNN e COM-ANO-NNNN.
"""
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
from decimal import Decimal
import secrets
import string
import math
from django.core.cache import cache
from django.core.exceptions import ValidationError

# -------------------------------------------------------------------
# CONSTANTES GLOBAIS
# -------------------------------------------------------------------
SMS_CUSTO = Decimal('0')  # Custo por SMS enviado ao cliente, em Meticais


# -------------------------------------------------------------------
# VALIDADORES PERSONALIZADOS
# -------------------------------------------------------------------
def validar_bi(value):
    """BI: 12 números seguidos de 1 letra maiúscula (ex: 123456789012A)"""
    if not value:
        return
    import re
    if not re.match(r'^\d{12}[A-Z]$', value):
        raise ValidationError('BI deve ter 12 números seguidos de 1 letra maiúscula (ex: 123456789012A).')


def validar_nuit(value):
    """NUIT: exactamente 9 dígitos"""
    if not value:
        return
    if not value.isdigit() or len(value) != 9:
        raise ValidationError('NUIT deve conter exactamente 9 dígitos.')


def validar_telefone(value):
    """Telefone: exactamente 9 dígitos (sem código do país)"""
    if not value:
        return
    if not value.isdigit() or len(value) != 9:
        raise ValidationError('Telefone deve conter exactamente 9 dígitos (ex: 821234567).')


# -------------------------------------------------------------------
# USER MANAGER
# -------------------------------------------------------------------
class UserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError("Username obrigatório")
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        if not password:
            raise ValueError('Password obrigatória para superusuário.')
        return self.create_user(username, email, password, **extra_fields)


# -------------------------------------------------------------------
# GERADORES DE USERNAME E SENHA
# -------------------------------------------------------------------
def gerar_username():
    chars = string.ascii_lowercase + string.digits
    while True:
        username = 'osm_' + ''.join(secrets.choice(chars) for _ in range(6))
        if not Utilizador.objects.filter(username=username).exists():
            return username


def gerar_senha():
    chars = string.ascii_letters + string.digits + '!@#$'
    senha = (
        secrets.choice(string.ascii_uppercase) +
        secrets.choice(string.ascii_lowercase) +
        secrets.choice(string.digits) +
        secrets.choice('!@#$') +
        ''.join(secrets.choice(chars) for _ in range(6))
    )
    return ''.join(secrets.SystemRandom().sample(senha, len(senha)))


# -------------------------------------------------------------------
# MANAGERS SOFT DELETE
# -------------------------------------------------------------------
class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class ActiveUserManager(UserManager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)




# -------------------------------------------------------------------
# UTILIZADOR
# -------------------------------------------------------------------
class Utilizador(AbstractUser):
    PERFIL_CHOICES = [
        ('superadmin', 'Super Administrador'),
        ('gestor',     'Gestor de Crédito'),
        ('cliente',    'Cliente'),
    ]
    TIPO_CLIENTE_CHOICES = [
        ('normal',      'Cliente Normal'),
        ('comerciante', 'Cliente Comerciante'),
    ]

    perfil             = models.CharField(max_length=20, choices=PERFIL_CHOICES, default='gestor')
    telefone           = models.CharField(max_length=30, blank=True, validators=[validar_telefone],
                                          help_text='9 dígitos (ex: 821234567)')
    nuit               = models.CharField(max_length=20, blank=True, validators=[validar_nuit],
                                          help_text='9 dígitos')
    bi                 = models.CharField(max_length=20, blank=True, validators=[validar_bi],
                                          help_text='12 números + 1 letra maiúscula (ex: 123456789012A)')
    cargo              = models.CharField(max_length=100, blank=True)
    data_nasc          = models.DateField(null=True, blank=True)
    activo             = models.BooleanField(default=True)
    senha_inicial      = models.CharField(max_length=30, blank=True)
    deve_trocar_senha  = models.BooleanField(default=True)
    email_confirmado   = models.BooleanField(default=False)
    criado_por         = models.ForeignKey('self', on_delete=models.SET_NULL,
                                           null=True, blank=True, related_name='criados')
    data_registo       = models.DateTimeField(auto_now_add=True)
    ultimo_login_ip    = models.GenericIPAddressField(null=True, blank=True)

    tipo_cliente       = models.CharField(max_length=20, choices=TIPO_CLIENTE_CHOICES, default='normal',
                                          help_text='Normal (mensal) ou Comerciante (diario/semanal)')
    lista_negra        = models.BooleanField(default=False, help_text='Bloqueia novas requisicoes permanentemente')
    motivo_lista_negra = models.TextField(blank=True)
    bloqueado_ate      = models.DateField(null=True, blank=True,
                                          help_text='Bloqueio temporario de requisicao apos rejeicao do gestor')

    bairro             = models.CharField(max_length=100, blank=True)
    distrito           = models.CharField(max_length=100, blank=True, default='Chimoio')
    provincia          = models.CharField(max_length=100, blank=True, default='Manica')

    perm_aprovar       = models.BooleanField(default=False)
    perm_eliminar      = models.BooleanField(default=False)
    perm_exportar      = models.BooleanField(default=True)
    perm_sms           = models.BooleanField(default=True)
    perm_comerciantes  = models.BooleanField(default=True)
    perm_relatorios    = models.BooleanField(default=True)
    perm_utilizadores  = models.BooleanField(default=False, help_text='Gerir utilizadores (criar, editar, activar/desactivar)')
    perm_config        = models.BooleanField(default=False, help_text='Aceder às configurações do sistema')
    perm_inadimplencia = models.BooleanField(default=True, help_text='Aceder ao painel de inadimplência')
    perm_tribunal      = models.BooleanField(default=False, help_text='Enviar casos para tribunal e cancelar multas')
    perm_lista_negra   = models.BooleanField(default=False, help_text='Gerir lista negra de clientes')
    perm_lancamentos   = models.BooleanField(default=True, help_text='Registar e submeter lançamentos de pagamento')
    perm_solicitacoes  = models.BooleanField(default=True, help_text='Ver e analisar solicitações públicas')
    limite_emprestimo  = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    # Soft delete
    deleted_at         = models.DateTimeField(null=True, blank=True, editable=False)

    objects = UserManager()
    active_objects = ActiveUserManager()

    class Meta:
        verbose_name = 'Utilizador'
        verbose_name_plural = 'Utilizadores'
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return self.nome_completo or self.username

    @property
    def nome_completo(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @property
    def iniciais(self):
        partes = self.nome_completo.split()
        return ''.join(p[0].upper() for p in partes[:2]) if partes else '??'

    @property
    def label_perfil(self):
        return dict(self.PERFIL_CHOICES).get(self.perfil, self.perfil)

    @property
    def label_tipo_cliente(self):
        return dict(self.TIPO_CLIENTE_CHOICES).get(self.tipo_cliente, self.tipo_cliente)

    @property
    def eh_superadmin(self):
        return self.perfil == 'superadmin' or self.is_superuser

    @property
    def pode_aprovar(self):
        return self.eh_superadmin or self.perm_aprovar

    @property
    def pode_eliminar(self):
        return self.eh_superadmin or self.perm_eliminar

    # -------------------------------------------------------------------
    # REGRAS PARA SOLICITAR NOVO EMPRÉSTIMO
    # -------------------------------------------------------------------
    @property
    def tem_emprestimos_activos(self):
        from .models import Emprestimo, Comerciante
        for emp in Emprestimo.active_objects.filter(cliente=self):
            if not emp.esta_quitado and emp.status not in ('rejeitado', 'quitado'):
                return True
        for com in Comerciante.active_objects.filter(cliente=self):
            if not com.esta_quitado and com.status != 'quitado':
                return True
        return False

    @property
    def total_divida_activa(self):
        from .models import Emprestimo, Comerciante
        total = Decimal('0')
        for emp in Emprestimo.active_objects.filter(cliente=self):
            if not emp.esta_quitado and emp.status not in ('rejeitado', 'quitado'):
                total += emp.total_com_multa
        for com in Comerciante.active_objects.filter(cliente=self):
            if not com.esta_quitado and com.status != 'quitado':
                total += com.total_restante
        return total

    @property
    def limite_disponivel(self):
        return max(Decimal('0'), self.limite_emprestimo - self.total_divida_activa)

    @property
    def tem_requisicao_pendente(self):
        from .models import RequisicaoCliente
        return RequisicaoCliente.active_objects.filter(
            cliente=self, status__in=['submetido', 'em_analise']
        ).exists()

    @property
    def pode_solicitar(self):
        if self.lista_negra:
            return False
        if self.bloqueado_ate and self.bloqueado_ate >= timezone.localdate():
            return False
        if self.tem_emprestimos_activos:
            return False
        if self.tem_requisicao_pendente:
            return False
        if self.limite_emprestimo <= 0:
            return False
        return True

    @property
    def motivo_bloqueio_requisicao(self):
        if self.lista_negra:
            return 'A sua conta esta bloqueada. Finalize os seus pagamentos em aberto.'
        if self.bloqueado_ate and self.bloqueado_ate >= timezone.localdate():
            return 'Finalize seu pagamento para proxima requisicao.'
        if self.tem_emprestimos_activos:
            return 'Possui empréstimos ou contratos em aberto. Quite todos antes de solicitar novo.'
        if self.tem_requisicao_pendente:
            return 'Já possui um pedido em análise. Aguarde a resposta do gestor.'
        if self.limite_emprestimo <= 0:
            return 'Limite de crédito não definido ou insuficiente. Contacte o gestor.'
        return ''

    # -------------------------------------------------------------------
    # SOFT DELETE
    # -------------------------------------------------------------------
    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])

    def hard_delete(self):
        super().delete()


# -------------------------------------------------------------------
# CONFIGURAÇÃO BANCÁRIA
# -------------------------------------------------------------------
class ConfiguracaoBancaria(models.Model):
    banco             = models.CharField(max_length=100, default='FNB — First National Bank')
    titular           = models.CharField(max_length=200, default='Office Semente Microcredito EI.')
    conta             = models.CharField(max_length=50,  default='4551596810001')
    nib               = models.CharField(max_length=60,  default='0014 0000 45515968101 86')
    nuit              = models.CharField(max_length=30,  blank=True, validators=[validar_nuit])
    agencia           = models.CharField(max_length=200, blank=True)
    telefone          = models.CharField(max_length=30,  blank=True, validators=[validar_telefone])
    emola_numero      = models.CharField(max_length=30, default='872031215',
                                         help_text='Numero e-Mola para transferencias de comerciantes')
    emola_titular     = models.CharField(max_length=200, default='Office Bernardo Ofece Semente',
                                         help_text='Titular da conta e-Mola')
    taxa_juros_padrao = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('30'))
    taxa_multa_padrao = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2'),
                                            help_text='Mora diaria %/dia')
    prazo_multa_dias  = models.PositiveIntegerField(default=5)

    # SMS (BulkSMS)
    bulksms_api_token = models.CharField(max_length=200, blank=True,
                                         help_text='API Token do BulkSMS (https://www.bulksms.com/account/)')
    bulksms_sender    = models.CharField(max_length=11, blank=True, default='OSM',
                                         help_text='Nome do remetente SMS (máx. 11 caracteres)')
    sms_alerta_dias   = models.PositiveIntegerField(default=3,
                                                    help_text='Enviar alerta SMS X dias antes do vencimento')
    sms_cobranca_auto = models.BooleanField(default=False,
                                            help_text='Enviar SMS automático a clientes em atraso diariamente')

    # Email
    email_smtp_host   = models.CharField(max_length=200, blank=True, default='smtp.gmail.com')
    email_smtp_port   = models.PositiveIntegerField(default=587)
    email_smtp_user   = models.CharField(max_length=200, blank=True,
                                         help_text='Email remetente (ex: noreply@ossm.co.mz)')
    email_smtp_pass   = models.CharField(max_length=200, blank=True,
                                         help_text='Senha de aplicação (não a senha da conta)')
    email_smtp_tls    = models.BooleanField(default=True)
    email_ativo       = models.BooleanField(default=False, help_text='Activar envio de emails pelo sistema')

    atualizado_em     = models.DateTimeField(auto_now=True)
    atualizado_por    = models.ForeignKey(Utilizador, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = 'Configuracao do Sistema'

    def __str__(self):
        return f"{self.banco} — {self.conta}"

    @classmethod
    def obter(cls):
        cached = cache.get('config_bancaria')
        if cached:
            return cached
        obj, _ = cls.objects.get_or_create(pk=1)
        cache.set('config_bancaria', obj, 600)
        return obj

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete('config_bancaria')


# -------------------------------------------------------------------
# MODELO CRÉDITO (USADO POR EMPRESTIMO E COMERCIANTE)
# -------------------------------------------------------------------
class Credito(models.Model):
    """
    Representa uma tranche de crédito concedida.
    Pode pertencer a um Emprestimo ou a um Comerciante (relação 1:N).
    Contém todos os campos financeiros e métodos de cálculo de multa e pagamentos.
    """
    # Relacionamentos (um crédito pertence a um Emprestimo OU a um Comerciante)
    emprestimo = models.ForeignKey('Emprestimo', on_delete=models.CASCADE,
                                   null=True, blank=True, related_name='creditos')
    comerciante = models.ForeignKey('Comerciante', on_delete=models.CASCADE,
                                    null=True, blank=True, related_name='creditos')

    # Campos financeiros
    valor            = models.DecimalField(max_digits=14, decimal_places=2,
                                           help_text='Capital da tranche')
    taxa_juros       = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('30'),
                                           help_text='Taxa de juro percentual (%)')
    taxa_multa       = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2'),
                                           help_text='Mora diária percentual (%)')
    prazo_multa_dias = models.PositiveIntegerField(default=5,
                                                   help_text='Dias de tolerância antes de incumprimento')

    # Pagamentos parciais
    saldo_restante        = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                                help_text='NULL = sem pagamentos parciais ainda')
    total_pago_parcial    = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    data_ultimo_pagamento = models.DateField(null=True, blank=True)

    # Controlo de multa e tribunal
    multa_cancelada           = models.BooleanField(default=False,
                                                    help_text='Admin cancelou a multa — mora zerada até próximo vencimento')
    motivo_cancelamento_multa = models.TextField(blank=True)
    cancelamento_multa_por    = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                                  null=True, blank=True, related_name='multas_canceladas_credito')
    enviado_tribunal          = models.BooleanField(default=False,
                                                    help_text='Admin enviou para tribunal — mora congela')
    data_envio_tribunal       = models.DateField(null=True, blank=True)
    enviado_tribunal_por      = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                                  null=True, blank=True, related_name='casos_tribunal_credito')

    pago           = models.BooleanField(default=False)
    data_pagamento = models.DateField(null=True, blank=True)
    data_vencimento = models.DateField(null=True, blank=True,
                                       help_text='Se vazio, usa a data_vencimento do Emprestimo ou a data_inicio+prazo do Comerciante')
    data_inicio    = models.DateField(default=timezone.localdate)

    # Soft delete
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        verbose_name = 'Crédito'
        verbose_name_plural = 'Créditos'
        ordering = ['-data_inicio']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(emprestimo__isnull=False, comerciante__isnull=True) |
                    models.Q(emprestimo__isnull=True, comerciante__isnull=False)
                ),
                name='credito_pertence_a_apenas_um'
            )
        ]

    def __str__(self):
        if self.emprestimo:
            return f"Crédito #{self.pk} — {self.emprestimo.numero_contrato}"
        else:
            return f"Crédito #{self.pk} — {self.comerciante.numero_contrato}"

    # -------------------------------------------------------------------
    # PROPRIEDADES FINANCEIRAS BASE
    # -------------------------------------------------------------------
    @property
    def total_a_pagar(self):
        """Capital + juros (1 período) + custo SMS."""
        base = Decimal(str(round(float(self.valor) * (1 + float(self.taxa_juros) / 100), 2)))
        return base + SMS_CUSTO

    @property
    def juros_valor(self):
        """Juros puros (sem capital, sem SMS)."""
        return self.total_a_pagar - self.valor - SMS_CUSTO

    @property
    def juros_valor_com_sms(self):
        return self.total_a_pagar - self.valor

    @property
    def saldo_devedor_base(self):
        if self.saldo_restante is not None:
            return self.saldo_restante
        return self.total_a_pagar

    @property
    def hoje(self):
        return timezone.localdate()

    @property
    def vencimento(self):
        if self.data_vencimento:
            return self.data_vencimento
        if self.emprestimo and self.emprestimo.data_vencimento:
            return self.emprestimo.data_vencimento
        if self.comerciante:
            # Para comerciante, o vencimento é calculado com base na data_inicio + prazo_dias
            from datetime import timedelta
            return self.data_inicio + timedelta(days=self.comerciante.prazo_dias)
        from datetime import timedelta
        return self.data_inicio + timedelta(days=30)

    @property
    def dias_desde_vencimento(self):
        from datetime import timedelta
        venc = self.vencimento
        if not venc:
            return 0
        base = venc
        if self.data_ultimo_pagamento and self.data_ultimo_pagamento >= venc:
            base = self.data_ultimo_pagamento + timedelta(days=1)
        return max(0, (self.hoje - base).days)

    @property
    def dias_atraso(self):
        return self.dias_desde_vencimento

    @property
    def esta_vencido(self):
        if self.enviado_tribunal:
            return False
        d = self.dias_desde_vencimento
        return 0 < d <= self.prazo_multa_dias

    @property
    def em_incumprimento(self):
        if self.enviado_tribunal:
            return True
        return self.dias_desde_vencimento > self.prazo_multa_dias

    @property
    def dias_multa_restantes(self):
        if not self.esta_vencido:
            return 0
        return self.prazo_multa_dias - self.dias_desde_vencimento

    @property
    def mora_composta(self):
        """Mora em JUROS SIMPLES. Congela se enviado_tribunal ou multa_cancelada."""
        if self.pago or not self.vencimento:
            return Decimal('0')
        if self.multa_cancelada:
            return Decimal('0')
        dias = self.dias_desde_vencimento
        if dias <= 0:
            return Decimal('0')
        dias = min(dias, self.prazo_multa_dias)
        saldo = float(self.saldo_devedor_base)
        taxa  = float(self.taxa_multa) / 100
        multa = saldo * taxa * dias
        return Decimal(str(round(multa, 2)))

    @property
    def multa_valor(self):
        return self.mora_composta

    @property
    def total_com_multa(self):
        return self.saldo_devedor_base + self.mora_composta

    @property
    def esta_quitado(self):
        return self.pago or (self.saldo_restante == Decimal('0'))

    @property
    def is_parcial(self):
        return self.saldo_restante is not None and self.saldo_restante > 0 and not self.pago

    @property
    def percentual_pago(self):
        if self.pago:
            return 100
        total = float(self.total_a_pagar)
        if total <= 0:
            return 0
        pago = float(self.total_pago_parcial)
        return int((pago / total) * 100) if pago > 0 else 0

    # -------------------------------------------------------------------
    # MÉTODOS DE CONTROLO (MULTA / TRIBUNAL)
    # -------------------------------------------------------------------
    def cancelar_multa(self, utilizador, motivo=''):
        self.multa_cancelada = True
        self.motivo_cancelamento_multa = motivo
        self.cancelamento_multa_por = utilizador
        self.save(update_fields=['multa_cancelada', 'motivo_cancelamento_multa', 'cancelamento_multa_por'])

    def reativar_multa(self, utilizador):
        self.multa_cancelada = False
        self.motivo_cancelamento_multa = ''
        self.cancelamento_multa_por = None
        self.save(update_fields=['multa_cancelada', 'motivo_cancelamento_multa', 'cancelamento_multa_por'])

    def enviar_para_tribunal(self, utilizador, motivo=''):
        self.enviado_tribunal = True
        self.data_envio_tribunal = timezone.localdate()
        self.enviado_tribunal_por = utilizador
        self.multa_cancelada = True
        self.motivo_cancelamento_multa = f'Caso enviado para tribunal em {timezone.localdate():%d/%m/%Y}. Motivo: {motivo}'
        self.save(update_fields=['enviado_tribunal', 'data_envio_tribunal', 'enviado_tribunal_por',
                                 'multa_cancelada', 'motivo_cancelamento_multa'])

    # -------------------------------------------------------------------
    # MÉTODOS DE PAGAMENTO
    # -------------------------------------------------------------------
    def registar_pagamento_parcial(self, valor_pago: Decimal, registado_por=None, metodo='dinheiro',
                                   referencia='', observacoes='', cobrar_sms=True):
        from django.db import transaction
        with transaction.atomic():
            custo_sms_val = SMS_CUSTO if cobrar_sms else Decimal('0')
            saldo_atual = self.saldo_restante if self.saldo_restante is not None else self.total_com_multa
            novo_saldo = max(Decimal('0'), saldo_atual - valor_pago)
            self.total_pago_parcial += valor_pago
            self.data_ultimo_pagamento = timezone.localdate()
            self.saldo_restante = novo_saldo
            if novo_saldo == Decimal('0'):
                self.pago = True
                self.data_pagamento = self.data_ultimo_pagamento
            else:
                self.pago = False
            self.save()
            Pagamento.objects.create(
                credito=self,
                valor_capital=Decimal('0'),
                valor_juros=Decimal('0'),
                valor_multa=Decimal('0'),
                valor_total=valor_pago,
                custo_sms=custo_sms_val,
                data_pagamento=self.data_ultimo_pagamento,
                registado_por=registado_por,
                dias_atraso=self.dias_atraso,
                observacoes=f"Pagamento parcial de {valor_pago} via {metodo}. {observacoes} Ref: {referencia}"
            )
            cache.delete('kpis_dashboard')
            cache.delete(f'cred_{self.pk}')

    def registar_pagamento_total(self, valor_pago: Decimal = None, registado_por=None, metodo='dinheiro',
                                 referencia='', observacoes='', cobrar_sms=True):
        from django.db import transaction
        with transaction.atomic():
            custo_sms_val = SMS_CUSTO if cobrar_sms else Decimal('0')
            if valor_pago is None:
                valor_pago = self.total_com_multa if self.saldo_restante is None else self.saldo_restante
            self.total_pago_parcial += valor_pago
            self.saldo_restante = Decimal('0')
            self.pago = True
            self.data_pagamento = timezone.localdate()
            self.data_ultimo_pagamento = self.data_pagamento
            self.save()
            Pagamento.objects.create(
                credito=self,
                valor_capital=self.valor,
                valor_juros=self.juros_valor,
                valor_multa=self.mora_composta,
                valor_total=valor_pago,
                custo_sms=custo_sms_val,
                data_pagamento=self.data_pagamento,
                registado_por=registado_por,
                dias_atraso=self.dias_atraso,
                observacoes=f"Pagamento final de {valor_pago} via {metodo}. {observacoes} Ref: {referencia}"
            )
            cache.delete('kpis_dashboard')
            cache.delete(f'cred_{self.pk}')

    # -------------------------------------------------------------------
    # SOFT DELETE
    # -------------------------------------------------------------------
    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])

    def hard_delete(self):
        super().delete()


# -------------------------------------------------------------------
# EMPRÉSTIMO (COM CRÉDITOS)
# -------------------------------------------------------------------
class Emprestimo(models.Model):
    STATUS_CHOICES = [
        ('pendente',      'Pendente'),
        ('ativo',         'Ativo'),
        ('vencido',       'Vencido'),
        ('incumprimento', 'Caso de Tribunal'),
        ('quitado',       'Quitado'),
        ('rejeitado',     'Rejeitado'),
    ]
    SCORE_CHOICES = [('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')]
    SECTOR_CHOICES = [
        ('Comercio',    'Comercio'),
        ('Servicos',    'Servicos'),
        ('Producao',    'Producao'),
        ('Agricultura', 'Agricultura'),
        ('Pescas',      'Pescas'),
        ('Construcao',  'Construcao'),
    ]
    TIPO_CLIENTE_CHOICES = [
        ('normal',      'Cliente Normal'),
        ('comerciante', 'Cliente Comerciante'),
    ]

    numero_contrato  = models.CharField(max_length=30, unique=True, editable=False)
    cliente          = models.ForeignKey(Utilizador, on_delete=models.PROTECT,
                                         null=True, blank=True, related_name='emprestimos_cliente')
    tipo_cliente     = models.CharField(max_length=20, choices=TIPO_CLIENTE_CHOICES, default='normal')

    nome             = models.CharField(max_length=200)
    nuit             = models.CharField(max_length=20, blank=True, validators=[validar_nuit])
    bi               = models.CharField(max_length=20, blank=True, validators=[validar_bi])
    telefone         = models.CharField(max_length=30, blank=True, validators=[validar_telefone])
    estado_civil     = models.CharField(max_length=30,  blank=True)
    bairro           = models.CharField(max_length=100, blank=True)
    empregador       = models.CharField(max_length=200, blank=True)
    nome_pai         = models.CharField(max_length=200, blank=True)
    nome_mae         = models.CharField(max_length=200, blank=True)
    distrito         = models.CharField(max_length=100, blank=True, default='Chimoio')
    provincia        = models.CharField(max_length=100, blank=True, default='Manica')
    local_emissao_bi = models.CharField(max_length=100, blank=True, default='Chimoio')
    data_emissao_bi  = models.DateField(null=True, blank=True)
    nacionalidade    = models.CharField(max_length=50, default='Mocambicana')

    sector           = models.CharField(max_length=30, choices=SECTOR_CHOICES, default='Comercio')
    finalidade       = models.CharField(max_length=200, blank=True)
    garantia         = models.TextField(blank=True)
    score            = models.CharField(max_length=1, choices=SCORE_CHOICES, default='A')

    data_inicio      = models.DateField(default=timezone.localdate)
    data_vencimento  = models.DateField(null=True, blank=True)
    data_registo     = models.DateTimeField(auto_now_add=True)

    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    registado_por    = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='registados')
    aprovado_por     = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='aprovados')
    data_aprovacao   = models.DateTimeField(null=True, blank=True)
    motivo_rejeicao  = models.TextField(blank=True)

    # Soft delete
    deleted_at       = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        verbose_name = 'Emprestimo'
        verbose_name_plural = 'Emprestimos'
        ordering = ['-data_registo']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['nome']),
            models.Index(fields=['data_registo']),
            models.Index(fields=['data_vencimento']),
            models.Index(fields=['deleted_at']),
        ]

    def __str__(self):
        return f"{self.numero_contrato} — {self.nome}"

    def save(self, *args, **kwargs):
        if not self.numero_contrato:
            ano = timezone.localdate().year
            n   = Emprestimo.objects.filter(numero_contrato__startswith=f'OSM-{ano}-').count()
            self.numero_contrato = f'OSM-{ano}-{n+1:04d}'
        if self.data_inicio and not self.data_vencimento:
            from datetime import timedelta
            self.data_vencimento = self.data_inicio + timedelta(days=30)
        super().save(*args, **kwargs)
        cache.delete(f'emp_{self.pk}')
        cache.delete('kpis_dashboard')

    # -------------------------------------------------------------------
    # ACESSO AOS CRÉDITOS
    # -------------------------------------------------------------------
    @property
    def creditos_activos(self):
        return self.creditos.filter(deleted_at__isnull=True)

    # -------------------------------------------------------------------
    # PROPRIEDADES AGREGADAS (DELEGAM AOS CRÉDITOS)
    # -------------------------------------------------------------------
    @property
    def valor(self):
        return sum(c.valor for c in self.creditos_activos) or Decimal('0')

    @property
    def total_a_pagar(self):
        return sum(c.total_a_pagar for c in self.creditos_activos) or Decimal('0')

    @property
    def juros_valor(self):
        return sum(c.juros_valor for c in self.creditos_activos) or Decimal('0')

    @property
    def juros_valor_com_sms(self):
        return sum(c.juros_valor_com_sms for c in self.creditos_activos) or Decimal('0')

    @property
    def valor_fmt(self):
        v = float(self.valor)
        if v >= 1_000_000:
            return f"{v/1_000_000:.1f}M MT"
        if v >= 1_000:
            return f"{int(v/1_000)}K MT"
        return f"{int(v)} MT"

    @property
    def taxa_juros(self):
        primeiro = self.creditos_activos.first()
        if primeiro:
            return primeiro.taxa_juros
        return ConfiguracaoBancaria.obter().taxa_juros_padrao

    @property
    def taxa_multa(self):
        primeiro = self.creditos_activos.first()
        if primeiro:
            return primeiro.taxa_multa
        return ConfiguracaoBancaria.obter().taxa_multa_padrao

    @property
    def prazo_multa_dias(self):
        primeiro = self.creditos_activos.first()
        if primeiro:
            return primeiro.prazo_multa_dias
        return ConfiguracaoBancaria.obter().prazo_multa_dias

    @property
    def saldo_restante(self):
        total = Decimal('0')
        for c in self.creditos_activos:
            if c.saldo_restante is not None:
                total += c.saldo_restante
        return total

    @property
    def total_pago_parcial(self):
        return sum(c.total_pago_parcial for c in self.creditos_activos) or Decimal('0')

    @property
    def saldo_devedor_base(self):
        return sum(c.saldo_devedor_base for c in self.creditos_activos) or Decimal('0')

    @property
    def data_ultimo_pagamento(self):
        datas = [c.data_ultimo_pagamento for c in self.creditos_activos if c.data_ultimo_pagamento]
        return max(datas) if datas else None

    @property
    def multa_cancelada(self):
        return all(c.multa_cancelada for c in self.creditos_activos)

    @property
    def enviado_tribunal(self):
        return any(c.enviado_tribunal for c in self.creditos_activos)

    @property
    def hoje(self):
        return timezone.localdate()

    @property
    def dias_desde_vencimento(self):
        return max((c.dias_desde_vencimento for c in self.creditos_activos), default=0)

    @property
    def dias_atraso(self):
        return self.dias_desde_vencimento

    @property
    def esta_vencido(self):
        return any(c.esta_vencido for c in self.creditos_activos) and not self.em_incumprimento

    @property
    def em_incumprimento(self):
        return any(c.em_incumprimento for c in self.creditos_activos)

    @property
    def dias_multa_restantes(self):
        return max((c.dias_multa_restantes for c in self.creditos_activos), default=0)

    @property
    def mora_composta(self):
        return sum(c.mora_composta for c in self.creditos_activos) or Decimal('0')

    @property
    def multa_valor(self):
        return self.mora_composta

    @property
    def total_com_multa(self):
        return sum(c.total_com_multa for c in self.creditos_activos) or Decimal('0')

    @property
    def is_parcial(self):
        return any(c.is_parcial for c in self.creditos_activos)

    @property
    def pago(self):
        return self.esta_quitado

    @property
    def data_pagamento(self):
        datas = [c.data_pagamento for c in self.creditos_activos if c.data_pagamento]
        return max(datas) if datas else None

    @property
    def esta_quitado(self):
        creditos = list(self.creditos_activos)
        if not creditos:
            return False
        return all(c.esta_quitado for c in creditos)

    @property
    def percentual_pago(self):
        if self.esta_quitado:
            return 100
        total = float(self.total_a_pagar)
        if total <= 0:
            return 0
        pago = float(self.total_pago_parcial)
        return int((pago / total) * 100) if pago > 0 else 0

    @property
    def progresso(self):
        return self.percentual_pago

    @property
    def status_display(self):
        """Status rico para UI — mantido igual à v3.4."""
        hoje = self.hoje
        if self.esta_quitado:
            return ('quitado', 'Quitado')
        dup = self.data_ultimo_pagamento
        if dup and self.data_vencimento and dup < self.data_vencimento:
            return ('adiantado', 'Pagamento adiantado')
        if self.data_vencimento and hoje < self.data_vencimento:
            if self.total_pago_parcial > 0:
                return ('andamento', 'Pagamento em andamento')
            return ('aguardar', 'A aguardar pagamento')
        dias = self.dias_desde_vencimento
        if dias > 0:
            if self.enviado_tribunal:
                return ('tribunal', 'Em incumprimento (Tribunal)')
            if dias > self.prazo_multa_dias:
                return ('multa', f'Em atraso com multa ({dias} dias)')
            return ('atraso', f'Em atraso ({dias} dias)')
        return ('ativo', 'Ativo')

    # -------------------------------------------------------------------
    # MÉTODOS DE CONTROLO (MULTA / TRIBUNAL)
    # -------------------------------------------------------------------
    def cancelar_multa(self, utilizador, motivo=''):
        for c in self.creditos_activos:
            c.cancelar_multa(utilizador, motivo)

    def reativar_multa(self, utilizador):
        for c in self.creditos_activos:
            c.reativar_multa(utilizador)

    def enviar_para_tribunal(self, utilizador, motivo=''):
        for c in self.creditos_activos:
            c.enviar_para_tribunal(utilizador, motivo)
        self.status = 'incumprimento'
        self.save(update_fields=['status'])

    def atualizar_status_automatico(self):
        if self.status in ('rejeitado', 'pendente'):
            return
        if self.esta_quitado:
            self.status = 'quitado'
        elif self.enviado_tribunal or self.em_incumprimento:
            self.status = 'incumprimento'
        elif self.esta_vencido:
            self.status = 'vencido'
        else:
            self.status = 'ativo'
        self.save(update_fields=['status'])

    # -------------------------------------------------------------------
    # MÉTODOS DE PAGAMENTO
    # -------------------------------------------------------------------
    def registar_pagamento_parcial(self, valor_pago: Decimal, registado_por=None, metodo='dinheiro',
                                   referencia='', observacoes='', cobrar_sms=True):
        credito = self.creditos_activos.filter(pago=False).first()
        if credito:
            credito.registar_pagamento_parcial(valor_pago, registado_por, metodo,
                                               referencia, observacoes, cobrar_sms)
            self.atualizar_status_automatico()

    def registar_pagamento(self, valor_pago: Decimal = None, registado_por=None, metodo='dinheiro',
                           referencia='', observacoes='', cobrar_sms=True):
        credito = self.creditos_activos.filter(pago=False).first()
        if credito:
            credito.registar_pagamento_total(valor_pago, registado_por, metodo,
                                             referencia, observacoes, cobrar_sms)
            self.atualizar_status_automatico()

    # -------------------------------------------------------------------
    # SOFT DELETE
    # -------------------------------------------------------------------
    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])

    def hard_delete(self):
        super().delete()


# -------------------------------------------------------------------
# PAGAMENTO (histórico de Crédito)
# -------------------------------------------------------------------
class Pagamento(models.Model):
    """
    Histórico de pagamentos associado a um Crédito.
    Permite múltiplos registos (parciais + total).
    """
    credito        = models.ForeignKey(Credito, on_delete=models.CASCADE, related_name='pagamentos')
    valor_capital  = models.DecimalField(max_digits=14, decimal_places=2)
    valor_juros    = models.DecimalField(max_digits=14, decimal_places=2)
    valor_multa    = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    valor_total    = models.DecimalField(max_digits=14, decimal_places=2)
    custo_sms      = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'),
                                         help_text='Custo do SMS enviado ao cliente (1.20 MT por SMS)')
    data_pagamento = models.DateField(default=timezone.localdate)
    registado_por  = models.ForeignKey(Utilizador, on_delete=models.SET_NULL, null=True, blank=True)
    dias_atraso    = models.PositiveIntegerField(default=0)
    observacoes    = models.TextField(blank=True)
    criado_em      = models.DateTimeField(auto_now_add=True)

    # Soft delete
    deleted_at     = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-data_pagamento']

    def __str__(self):
        return f"Pagamento Crédito #{self.credito.pk} — MT {self.valor_total} ({self.data_pagamento})"

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])


# -------------------------------------------------------------------
# FOTO GARANTIA
# -------------------------------------------------------------------
class FotoGarantia(models.Model):
    emprestimo = models.ForeignKey(Emprestimo, on_delete=models.CASCADE, related_name='fotos_garantia')
    foto       = models.ImageField(upload_to='garantias/%Y/%m/')
    criado_em  = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])


# -------------------------------------------------------------------
# REQUISIÇÃO CLIENTE
# -------------------------------------------------------------------
class RequisicaoCliente(models.Model):
    STATUS_CHOICES = [
        ('submetido',  'Submetido'),
        ('em_analise', 'Em Analise'),
        ('aprovado',   'Aprovado'),
        ('rejeitado',  'Rejeitado'),
    ]
    TIPO_CLIENTE_CHOICES = [
        ('normal',      'Cliente Normal'),
        ('comerciante', 'Cliente Comerciante'),
    ]

    cliente         = models.ForeignKey(Utilizador, on_delete=models.CASCADE, related_name='requisicoes')
    tipo_cliente    = models.CharField(max_length=20, choices=TIPO_CLIENTE_CHOICES, default='normal')
    valor_pedido    = models.DecimalField(max_digits=14, decimal_places=2)
    finalidade      = models.CharField(max_length=300)
    garantia_desc   = models.TextField(blank=True)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submetido')
    emprestimo      = models.OneToOneField(Emprestimo, on_delete=models.SET_NULL,
                                           null=True, blank=True, related_name='requisicao')
    data_requisicao = models.DateTimeField(auto_now_add=True)
    data_resposta   = models.DateTimeField(null=True, blank=True)
    resposta_por    = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='respostas_req')
    nota_gestor     = models.TextField(blank=True)
    deleted_at      = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-data_requisicao']
        verbose_name = 'Requisicao de Cliente'

    def __str__(self):
        return f"{self.cliente} — MT {self.valor_pedido} ({self.status})"

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])


# -------------------------------------------------------------------
# COMERCIANTE (COM CRÉDITOS)
# -------------------------------------------------------------------
class Comerciante(models.Model):
    """
    Mantém lógica original completa de parcelamento diário/semanal,
    agora utilizando um ou mais Créditos para os dados financeiros.
    Os métodos originais (parcela_diaria, periodos_em_atraso, etc.)
    são recalculados com base no primeiro crédito activo (ou soma de todos).
    """
    TIPO_CHOICES = [
        ('Retalhista', 'Retalhista'), ('Grossista', 'Grossista'),
        ('Mercado',    'Mercado'),    ('Barraca',   'Barraca'),
        ('Cantina',    'Cantina'),    ('Salao',     'Salao'),
        ('Oficina',    'Oficina'),    ('Outro',     'Outro'),
    ]
    MODALIDADE_CHOICES = [
        ('diario',  'Diario'),
        ('semanal', 'Semanal'),
    ]

    numero_contrato      = models.CharField(max_length=30, unique=True, editable=False)
    cliente              = models.ForeignKey(Utilizador, on_delete=models.PROTECT,
                                             null=True, blank=True, related_name='contratos_comerciante')
    nome                 = models.CharField(max_length=200)
    tipo_comercio        = models.CharField(max_length=30, choices=TIPO_CHOICES, default='Retalhista')
    nuit                 = models.CharField(max_length=20, blank=True, validators=[validar_nuit])
    bi                   = models.CharField(max_length=20, blank=True, validators=[validar_bi])
    telefone             = models.CharField(max_length=30, blank=True, validators=[validar_telefone])
    bairro               = models.CharField(max_length=100, blank=True)
    garantia             = models.TextField(blank=True)
    data_inicio          = models.DateField(default=timezone.localdate)
    modalidade_pagamento = models.CharField(max_length=10, choices=MODALIDADE_CHOICES, default='diario',
                                            help_text='Diario ou Semanal — multa 2% por parcela em atraso')
    prazo_dias           = models.PositiveIntegerField(default=30)

    # Controlo de pagamentos (agora delegado aos créditos, mas mantido para compatibilidade)
    data_ultimo_pagamento = models.DateField(null=True, blank=True,
                                             help_text='Última data em que foi registado um pagamento')

    # Controlo de multa e tribunal (delegado aos créditos)
    multa_cancelada           = models.BooleanField(default=False,
                                                    help_text='Admin cancelou a multa — mora zerada até próximo período')
    motivo_cancelamento_multa = models.TextField(blank=True)
    cancelamento_multa_por    = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                                  null=True, blank=True, related_name='multas_canceladas_comerciante')
    enviado_tribunal          = models.BooleanField(default=False,
                                                    help_text='Admin enviou para tribunal — mora congela, status incumprimento')
    data_envio_tribunal       = models.DateField(null=True, blank=True)
    enviado_tribunal_por      = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                                  null=True, blank=True, related_name='casos_tribunal_comerciante')

    registado_por = models.ForeignKey(Utilizador, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em     = models.DateTimeField(auto_now_add=True)
    deleted_at    = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['data_inicio']),
            models.Index(fields=['deleted_at']),
        ]

    def __str__(self):
        return f"{self.numero_contrato} — {self.nome}"

    def save(self, *args, **kwargs):
        if not self.numero_contrato:
            ano = timezone.localdate().year
            n   = Comerciante.objects.count()
            self.numero_contrato = f'COM-{ano}-{n+1:04d}'
        super().save(*args, **kwargs)

    # -------------------------------------------------------------------
    # ACESSO AOS CRÉDITOS
    # -------------------------------------------------------------------
    @property
    def creditos_activos(self):
        return self.creditos.filter(deleted_at__isnull=True)

    @property
    def credito_principal(self):
        """Primeiro crédito activo (assume-se que cada comerciante tem um crédito principal)."""
        return self.creditos_activos.first()

    # -------------------------------------------------------------------
    # PROPRIEDADES FINANCEIRAS (DELEGAM AO CRÉDITO)
    # -------------------------------------------------------------------
    @property
    def capital(self):
        cred = self.credito_principal
        return cred.valor if cred else Decimal('0')

    @property
    def taxa_juros(self):
        cred = self.credito_principal
        return cred.taxa_juros if cred else ConfiguracaoBancaria.obter().taxa_juros_padrao

    @property
    def total_a_pagar(self):
        cred = self.credito_principal
        return cred.total_a_pagar if cred else Decimal('0')

    @property
    def juros_valor(self):
        cred = self.credito_principal
        return cred.juros_valor if cred else Decimal('0')

    @property
    def total_pago(self):
        return sum(c.total_pago_parcial for c in self.creditos_activos) or Decimal('0')

    @property
    def total_restante(self):
        return sum(c.total_com_multa for c in self.creditos_activos) or Decimal('0')

    @property
    def total_restante_sem_multa(self):
        return max(Decimal('0'), self.total_a_pagar - self.total_pago)

    @property
    def esta_quitado(self):
        return all(c.esta_quitado for c in self.creditos_activos)

    # -------------------------------------------------------------------
    # CÁLCULO DE PARCELAS E PERÍODOS (ORIGINAL, ADAPTADO AO CRÉDITO)
    # -------------------------------------------------------------------
    @property
    def parcela_diaria(self):
        if not self.prazo_dias:
            return Decimal('0')
        total = float(self.capital) * (1 + float(self.taxa_juros) / 100)
        return Decimal(str(math.floor(total / self.prazo_dias * 100) / 100))

    @property
    def num_semanas(self):
        return max(1, self.prazo_dias // 7)

    @property
    def parcela_semanal(self):
        return Decimal(str(round(float(self.total_a_pagar) / self.num_semanas, 2)))

    @property
    def parcela_atual(self):
        if self.modalidade_pagamento == 'semanal':
            return self.parcela_semanal
        return self.parcela_diaria

    @property
    def hoje(self):
        return timezone.localdate()

    @property
    def dias_pagos(self):
        return self.pagamentos_diarios.count()

    @property
    def semanas_pagas(self):
        datas = self.pagamentos_diarios.values_list('data', flat=True)
        semanas = set()
        for d in datas:
            semanas.add(d.isocalendar()[:2])
        return len(semanas)

    @property
    def periodos_pagos(self):
        if self.modalidade_pagamento == 'semanal':
            return self.semanas_pagas
        return self.dias_pagos

    @property
    def total_periodos(self):
        if self.modalidade_pagamento == 'semanal':
            return self.num_semanas
        return self.prazo_dias

    @property
    def periodos_esperados(self):
        if not self.data_inicio:
            return 0
        hoje = self.hoje
        if self.data_ultimo_pagamento and self.data_ultimo_pagamento >= self.data_inicio:
            base = self.data_ultimo_pagamento
            if base >= hoje:
                return self.periodos_pagos
        else:
            base = self.data_inicio
        diff = (hoje - base).days
        if self.modalidade_pagamento == 'semanal':
            esperados = diff // 7 + 1
        else:
            esperados = diff + 1
        esperados = min(esperados, self.total_periodos)
        return max(esperados, self.periodos_pagos)

    @property
    def periodos_em_atraso(self):
        if self.enviado_tribunal:
            return 0
        return max(0, self.periodos_esperados - self.periodos_pagos)

    @property
    def esta_vencido(self):
        if self.enviado_tribunal:
            return False
        atraso = self.periodos_em_atraso
        return 0 < atraso <= 5

    @property
    def em_incumprimento(self):
        if self.enviado_tribunal:
            return True
        return self.periodos_em_atraso > 5

    @property
    def multa_parcela_em_atraso(self):
        if self.multa_cancelada or self.enviado_tribunal:
            return Decimal('0')
        periodos = self.periodos_em_atraso
        if periodos <= 0:
            return Decimal('0')
        saldo = float(self.parcela_atual) * periodos
        taxa = 0.02
        mora = saldo * taxa * periodos
        return Decimal(str(round(mora, 2)))

    @property
    def multa_valor(self):
        return self.multa_parcela_em_atraso

    @property
    def total_em_atraso(self):
        return Decimal(str(round(float(self.parcela_atual) * self.periodos_em_atraso, 2)))

    @property
    def status(self):
        if self.esta_quitado:
            return 'quitado'
        if self.enviado_tribunal:
            return 'incumprimento'
        if self.em_incumprimento:
            return 'incumprimento'
        if self.periodos_em_atraso > 0:
            return 'atraso'
        return 'ativo'

    @property
    def progresso(self):
        if self.total_periodos == 0:
            return 0
        pct = (self.periodos_pagos / self.total_periodos) * 100
        return min(100, max(0, int(round(pct))))

    # -------------------------------------------------------------------
    # UTILIDADES
    # -------------------------------------------------------------------
    def pagou_hoje(self):
        return self.pagamentos_diarios.filter(data=self.hoje).exists()

    def pagou_esta_semana(self):
        from datetime import timedelta
        hoje = self.hoje
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        fim_semana    = inicio_semana + timedelta(days=6)
        return self.pagamentos_diarios.filter(data__gte=inicio_semana, data__lte=fim_semana).exists()

    def ja_pagou_periodo_atual(self):
        if self.modalidade_pagamento == 'semanal':
            return self.pagou_esta_semana()
        return self.pagou_hoje()

    def ja_pagou_data(self, data):
        return self.pagamentos_diarios.filter(data=data).exists()

    def numero_periodo_para_data(self, data):
        delta = (data - self.data_inicio).days
        if delta < 0 or delta >= self.prazo_dias:
            return None
        return delta + 1

    # -------------------------------------------------------------------
    # MÉTODOS DE CONTROLO (MULTA / TRIBUNAL)
    # -------------------------------------------------------------------
    def cancelar_multa(self, utilizador, motivo=''):
        self.multa_cancelada = True
        self.motivo_cancelamento_multa = motivo
        self.cancelamento_multa_por = utilizador
        self.save(update_fields=['multa_cancelada', 'motivo_cancelamento_multa', 'cancelamento_multa_por'])
        # Propagar para os créditos associados
        for c in self.creditos_activos:
            c.cancelar_multa(utilizador, motivo)

    def reativar_multa(self, utilizador):
        self.multa_cancelada = False
        self.motivo_cancelamento_multa = ''
        self.cancelamento_multa_por = None
        self.save(update_fields=['multa_cancelada', 'motivo_cancelamento_multa', 'cancelamento_multa_por'])
        for c in self.creditos_activos:
            c.reativar_multa(utilizador)

    def enviar_para_tribunal(self, utilizador, motivo=''):
        self.enviado_tribunal = True
        self.data_envio_tribunal = timezone.localdate()
        self.enviado_tribunal_por = utilizador
        self.multa_cancelada = True
        self.motivo_cancelamento_multa = f'Caso enviado para tribunal em {timezone.localdate():%d/%m/%Y}. Motivo: {motivo}'
        self.save(update_fields=['enviado_tribunal', 'data_envio_tribunal', 'enviado_tribunal_por',
                                 'multa_cancelada', 'motivo_cancelamento_multa'])
        for c in self.creditos_activos:
            c.enviar_para_tribunal(utilizador, motivo)

    # -------------------------------------------------------------------
    # MÉTODO DE PAGAMENTO
    # -------------------------------------------------------------------
    def registar_pagamento(self, valor_pago: Decimal, registado_por=None, data_pagamento=None, cobrar_sms=True):
        from django.db import transaction
        if data_pagamento is None:
            data_pagamento = self.hoje
        custo_sms_val = SMS_CUSTO if cobrar_sms else Decimal('0')
        with transaction.atomic():
            PagamentoDiario.objects.update_or_create(
                comerciante=self, data=data_pagamento,
                defaults={'valor_pago': valor_pago, 'custo_sms': custo_sms_val,
                          'registado_por': registado_por, 'confirmado': True}
            )
            if data_pagamento >= (self.data_ultimo_pagamento or self.data_inicio):
                self.data_ultimo_pagamento = data_pagamento
                self.save(update_fields=['data_ultimo_pagamento'])
            # Propagar o pagamento para o primeiro crédito activo (ou para todos?)
            credito = self.creditos_activos.filter(pago=False).first()
            if credito:
                credito.registar_pagamento_total(valor_pago, registado_por, 'dinheiro',
                                                 '', '', cobrar_sms)
            cache.delete('kpis_dashboard')
            cache.delete(f'com_{self.pk}')

    # -------------------------------------------------------------------
    # SOFT DELETE
    # -------------------------------------------------------------------
    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])

    def hard_delete(self):
        super().delete()


# -------------------------------------------------------------------
# PAGAMENTO DIÁRIO (comerciante)
# -------------------------------------------------------------------
class PagamentoDiario(models.Model):
    comerciante   = models.ForeignKey(Comerciante, on_delete=models.CASCADE, related_name='pagamentos_diarios')
    data          = models.DateField(default=timezone.localdate)
    valor_pago    = models.DecimalField(max_digits=14, decimal_places=2)
    custo_sms     = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'),
                                        help_text='Custo do SMS enviado ao cliente (1.20 MT por SMS)')
    registado_por = models.ForeignKey(Utilizador, on_delete=models.SET_NULL, null=True, blank=True)
    confirmado    = models.BooleanField(default=True, help_text='Confirmado — não pode ser editado após confirmação')
    criado_em     = models.DateTimeField(auto_now_add=True)
    deleted_at    = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        unique_together = ('comerciante', 'data')
        ordering = ['-data']

    def __str__(self):
        return f"{self.comerciante.numero_contrato} — {self.data}: MT {self.valor_pago}"

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])


# -------------------------------------------------------------------
# LOGS
# -------------------------------------------------------------------
class LogActividade(models.Model):
    tipo       = models.CharField(max_length=50, db_index=True)
    descricao  = models.CharField(max_length=300)
    detalhe    = models.CharField(max_length=300, blank=True)
    utilizador = models.ForeignKey(Utilizador, on_delete=models.SET_NULL, null=True, blank=True)
    ip         = models.GenericIPAddressField(null=True, blank=True)
    criado_em  = models.DateTimeField(auto_now_add=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-criado_em']
        indexes = [models.Index(fields=['tipo', 'criado_em']), models.Index(fields=['deleted_at'])]

    @classmethod
    def registar(cls, tipo, descricao, detalhe='', utilizador=None, request=None):
        ip = None
        if request:
            ip = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                  or request.META.get('REMOTE_ADDR'))
        cls.objects.create(tipo=tipo, descricao=descricao, detalhe=detalhe,
                           utilizador=utilizador, ip=ip)

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])


class LogSMS(models.Model):
    nome            = models.CharField(max_length=200)
    telefone        = models.CharField(max_length=30, validators=[validar_telefone])
    mensagem        = models.TextField()
    status          = models.CharField(max_length=30, default='enviado')
    regra           = models.CharField(max_length=200, blank=True)
    numero_contrato = models.CharField(max_length=30, blank=True)
    enviado_por     = models.ForeignKey(Utilizador, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em       = models.DateTimeField(auto_now_add=True)
    deleted_at      = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-criado_em']

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])


# -------------------------------------------------------------------
# LANÇAMENTO DE PAGAMENTO
# -------------------------------------------------------------------
class LancamentoPagamento(models.Model):
    METODO_CHOICES = [
        ('dinheiro',      'Dinheiro Fisico'),
        ('transferencia', 'Transferencia Bancaria'),
        ('mpesa',         'M-Pesa'),
        ('mkesh',         'mKesh'),
        ('emola',         'eWallet / Emola'),
        ('outro',         'Outro'),
    ]
    STATUS_CHOICES = [
        ('pendente',  'Pendente de Validacao'),
        ('validado',  'Validado'),
        ('rejeitado', 'Rejeitado'),
    ]
    TIPO_PAG_CHOICES = [
        ('parcial', 'Parcial'),
        ('total',   'Total'),
    ]

    emprestimo        = models.ForeignKey(Emprestimo, on_delete=models.CASCADE, related_name='lancamentos')
    metodo            = models.CharField(max_length=20, choices=METODO_CHOICES)
    valor_pago        = models.DecimalField(max_digits=14, decimal_places=2)
    data_pagamento    = models.DateField(default=timezone.localdate)
    referencia        = models.CharField(max_length=200, blank=True)
    foto_comprovativo = models.ImageField(upload_to='comprovantes/%Y/%m/', null=True, blank=True)
    notas             = models.TextField(blank=True)
    tipo_pagamento    = models.CharField(max_length=10, choices=TIPO_PAG_CHOICES, default='parcial')
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    submetido_por     = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='lancamentos_submetidos')
    validado_por      = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='lancamentos_validados')
    data_validacao    = models.DateTimeField(null=True, blank=True)
    motivo_rejeicao   = models.TextField(blank=True)
    criado_em         = models.DateTimeField(auto_now_add=True)
    deleted_at        = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f"{self.emprestimo.numero_contrato} — MT {self.valor_pago} ({self.status})"

    def save(self, *args, **kwargs):
        if self.pk:
            original = LancamentoPagamento.objects.filter(pk=self.pk).first()
            if original and original.status == 'validado':
                self.valor_pago    = original.valor_pago
                self.metodo        = original.metodo
                self.data_pagamento = original.data_pagamento
                self.emprestimo_id = original.emprestimo_id
                self.tipo_pagamento = original.tipo_pagamento
        super().save(*args, **kwargs)

    @property
    def pode_editar(self):
        return self.status == 'pendente'

    def validar(self, utilizador):
        from django.db import transaction
        with transaction.atomic():
            self.status        = 'validado'
            self.validado_por  = utilizador
            self.data_validacao = timezone.now()
            self.save(update_fields=['status', 'validado_por', 'data_validacao'])

            emp = self.emprestimo
            emp.refresh_from_db()
            credito = emp.creditos_activos.filter(pago=False).first()
            if credito:
                if self.tipo_pagamento == 'parcial':
                    credito.registar_pagamento_parcial(
                        valor_pago=self.valor_pago,
                        registado_por=utilizador,
                        metodo=self.metodo,
                        referencia=self.referencia,
                        observacoes=self.notas,
                        cobrar_sms=True,
                    )
                else:
                    credito.registar_pagamento_total(
                        valor_pago=self.valor_pago,
                        registado_por=utilizador,
                        metodo=self.metodo,
                        referencia=self.referencia,
                        observacoes=self.notas,
                        cobrar_sms=True,
                    )
                # Ajustar data para pagamentos adiantados
                data_pag = self.data_pagamento or timezone.localdate()
                if data_pag != timezone.localdate():
                    credito.data_ultimo_pagamento = data_pag
                    credito.save(update_fields=['data_ultimo_pagamento'])
                    ultimo_pag = credito.pagamentos.order_by('-id').first()
                    if ultimo_pag:
                        ultimo_pag.data_pagamento = data_pag
                        ultimo_pag.save(update_fields=['data_pagamento'])
            emp.atualizar_status_automatico()

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])


# -------------------------------------------------------------------
# SOLICITAÇÃO PÚBLICA
# -------------------------------------------------------------------
class SolicitacaoPublica(models.Model):
    STATUS_CHOICES = [
        ('submetido',  'Submetido'),
        ('em_analise', 'Em Analise'),
        ('aprovado',   'Aprovado'),
        ('rejeitado',  'Rejeitado'),
    ]
    TIPO_CLIENTE_CHOICES = [
        ('normal',      'Cliente Normal'),
        ('comerciante', 'Cliente Comerciante'),
    ]

    tipo_cliente      = models.CharField(max_length=20, choices=TIPO_CLIENTE_CHOICES, default='normal',
                                         help_text='Tipo escolhido pelo solicitante na landing page')
    nome_completo     = models.CharField(max_length=200)
    email             = models.CharField(max_length=200, blank=True)
    telefone          = models.CharField(max_length=30, validators=[validar_telefone])
    bi                = models.CharField(max_length=30, blank=True, validators=[validar_bi])
    nuit              = models.CharField(max_length=20, blank=True, validators=[validar_nuit])
    bairro            = models.CharField(max_length=100, blank=True)
    estado_civil      = models.CharField(max_length=30, blank=True)
    valor_pedido      = models.DecimalField(max_digits=14, decimal_places=2)
    finalidade        = models.CharField(max_length=300)
    garantia_desc     = models.TextField(blank=True)
    documento_pdf     = models.FileField(upload_to='solicitacoes/%Y/%m/', null=True, blank=True)
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submetido')
    ip_origem         = models.GenericIPAddressField(null=True, blank=True)
    data_submissao    = models.DateTimeField(auto_now_add=True)
    data_resposta     = models.DateTimeField(null=True, blank=True)
    avaliado_por      = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='solicitacoes_avaliadas')
    nota_gestor       = models.TextField(blank=True)
    motivo_rejeicao   = models.TextField(blank=True)
    utilizador_criado = models.OneToOneField(Utilizador, on_delete=models.SET_NULL,
                                             null=True, blank=True, related_name='solicitacao_origem')
    emprestimo_criado = models.OneToOneField(Emprestimo, on_delete=models.SET_NULL,
                                             null=True, blank=True, related_name='solicitacao_origem')
    deleted_at        = models.DateTimeField(null=True, blank=True, editable=False)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        verbose_name        = 'Solicitacao Publica'
        verbose_name_plural = 'Solicitacoes Publicas'
        ordering            = ['-data_submissao']

    def __str__(self):
        return f"{self.nome_completo} — MT {self.valor_pedido} [{self.status}]"

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])


# -------------------------------------------------------------------
# LICENÇA DO SISTEMA
# -------------------------------------------------------------------
class LicencaSistema(models.Model):
    ESTADO_CHOICES = [
        ('activa',   'Activa'),
        ('alerta',   'Alerta — A Expirar'),
        ('expirada', 'Expirada'),
        ('pausada',  'Pausada'),
    ]

    codigo          = models.CharField(max_length=7, unique=True, editable=False)
    estado          = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='activa')
    data_emissao    = models.DateTimeField(default=timezone.now)
    data_expiracao  = models.DateTimeField()
    data_alerta     = models.DateTimeField()
    pausada_em      = models.DateTimeField(null=True, blank=True)
    pausa_expira    = models.DateTimeField(null=True, blank=True)
    motivo_pausa    = models.TextField(blank=True)
    renovacoes      = models.PositiveIntegerField(default=0)
    renovada_por    = models.ForeignKey(Utilizador, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='licencas_renovadas')
    criada_em       = models.DateTimeField(auto_now_add=True)
    actualizada_em  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Licenca do Sistema'
        verbose_name_plural = 'Licencas do Sistema'
        ordering            = ['-data_emissao']

    def __str__(self):
        return f"Licenca {self.codigo} — {self.get_estado_display()} · Expira {self.data_expiracao:%d/%m/%Y}"

    @classmethod
    def _gerar_codigo(cls):
        import random
        while True:
            codigo = f"{random.randint(1000000, 9999999)}"
            if not cls.objects.filter(codigo=codigo).exists():
                return codigo

    @classmethod
    def obter_activa(cls):
        return cls.objects.filter(estado__in=['activa', 'alerta']).order_by('-data_emissao').first()

    @classmethod
    def obter_ou_criar(cls):
        lic = cls.objects.order_by('-data_emissao').first()
        if lic is None:
            lic = cls.criar_nova()
        return lic

    @classmethod
    def criar_nova(cls, renovada_por=None, base_dt=None):
        from datetime import timedelta
        agora  = base_dt or timezone.now()
        expira = agora + timedelta(days=365)
        alerta = expira - timedelta(days=14)
        return cls.objects.create(
            codigo=cls._gerar_codigo(),
            estado='activa',
            data_emissao=agora,
            data_expiracao=expira,
            data_alerta=alerta,
            renovada_por=renovada_por,
        )

    def actualizar_estado(self):
        agora   = timezone.now()
        changed = False
        if self.estado == 'pausada' and self.pausa_expira and agora > self.pausa_expira:
            self.estado = 'expirada'
            changed = True
        elif self.estado not in ('expirada', 'pausada'):
            if agora >= self.data_expiracao:
                novo = 'expirada'
            elif agora >= self.data_alerta:
                novo = 'alerta'
            else:
                novo = 'activa'
            if novo != self.estado:
                self.estado = novo
                changed = True
        if changed:
            self.save(update_fields=['estado', 'actualizada_em'])
        return self.estado

    @property
    def dias_restantes(self):
        delta = self.data_expiracao - timezone.now()
        return max(0, delta.days)

    @property
    def bloqueada(self):
        return self.estado in ('expirada',) or (
            self.estado == 'pausada' and self.pausa_expira and timezone.now() > self.pausa_expira
        )

    def renovar(self, utilizador=None):
        self.estado = 'expirada'
        self.save(update_fields=['estado', 'actualizada_em'])
        nova = LicencaSistema.criar_nova(renovada_por=utilizador)
        nova.renovacoes = self.renovacoes + 1
        nova.save(update_fields=['renovacoes'])
        return nova

    def pausar(self, utilizador=None, motivo=''):
        from datetime import timedelta
        self.estado       = 'pausada'
        self.pausada_em   = timezone.now()
        self.pausa_expira = timezone.now() + timedelta(days=7)
        self.motivo_pausa = motivo
        self.save()