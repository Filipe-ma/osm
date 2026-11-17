import os
import django
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from osm.models import (
    Utilizador, Emprestimo, ConfiguracaoBancaria, Comerciante, PagamentoDiario,
    LogActividade, LicencaSistema, RequisicaoCliente, LancamentoPagamento,
    SolicitacaoPublica, Pagamento
)

User = get_user_model()

print("\n🚀 A carregar dados de teste...\n")

# ===================== USERS =====================
admin, _ = User.objects.get_or_create(
    username='admin',
    defaults={
        'email': 'admin@test.com',
        'is_superuser': True,
        'is_staff': True,
        'perfil': 'superadmin',
    }
)
if admin.password != 'admin123':
    admin.set_password('admin123')
    admin.save()

gestor, _ = User.objects.get_or_create(
    username='gestor',
    defaults={
        'first_name': 'Carlos',
        'last_name': 'Gestor',
        'perfil': 'gestor',
        'perm_aprovar': True,
        'limite_emprestimo': Decimal('100000'),
    }
)
gestor.set_password('123456')
gestor.save()

# Clientes com diferentes configurações
clientes_data = [
    {'username': 'cliente0', 'tipo_cliente': 'normal', 'limite_emprestimo': Decimal('50000'), 'lista_negra': False},
    {'username': 'cliente1', 'tipo_cliente': 'normal', 'limite_emprestimo': Decimal('30000'), 'lista_negra': False},
    {'username': 'cliente2', 'tipo_cliente': 'comerciante', 'limite_emprestimo': Decimal('40000'), 'lista_negra': False},
    {'username': 'cliente3', 'tipo_cliente': 'normal', 'limite_emprestimo': Decimal('20000'), 'lista_negra': True, 'motivo_lista_negra': 'Incumprimento passado'},
    {'username': 'cliente4', 'tipo_cliente': 'normal', 'limite_emprestimo': Decimal('10000'), 'bloqueado_ate': timezone.now().date() + timedelta(days=10)},
    {'username': 'cliente5', 'tipo_cliente': 'normal', 'limite_emprestimo': Decimal('0')},
]
clientes = []
for data in clientes_data:
    user, created = User.objects.get_or_create(
        username=data['username'],
        defaults={
            'first_name': data['username'].capitalize(),
            'last_name': 'Teste',
            'perfil': 'cliente',
            'telefone': f'25884{100000+int(data["username"][-1])}',
            'tipo_cliente': data['tipo_cliente'],
            'limite_emprestimo': data['limite_emprestimo'],
            'lista_negra': data.get('lista_negra', False),
            'motivo_lista_negra': data.get('motivo_lista_negra', ''),
            'bloqueado_ate': data.get('bloqueado_ate', None),
        }
    )
    if created:
        user.set_password('123456')
        user.save()
        print(f"✔ Cliente {data['username']} criado")
    clientes.append(user)

# ===================== CONFIG =====================
conf = ConfiguracaoBancaria.obter()
conf.banco = "FNB"
conf.titular = "OSM Microcredito"
conf.conta = "4551596810001"
conf.taxa_juros_padrao = Decimal('30')
conf.taxa_multa_padrao = Decimal('2')
conf.prazo_multa_dias = 5
conf.save()
print("✔ Configuração bancária OK")

# ===================== EMPRESTIMOS =====================
emprestimos = []

# Cliente0: empréstimo activo com pagamento parcial
emp0 = Emprestimo.objects.create(
    cliente=clientes[0],
    nome=clientes[0].nome_completo,
    telefone=clientes[0].telefone,
    valor=Decimal('10000'),
    taxa_juros=30,
    registado_por=gestor,
    aprovado_por=gestor,
    data_aprovacao=timezone.now(),
    data_inicio=timezone.now().date() - timedelta(days=5),
)
emp0.registar_pagamento_parcial(
    valor_pago=Decimal('2000'),
    registado_por=gestor,
    metodo='dinheiro',
    observacoes='Pagamento parcial'
)
emprestimos.append(emp0)
print(f"✔ Empréstimo com pagamento parcial: {emp0.numero_contrato}")

# Cliente1: empréstimo totalmente pago
emp1 = Emprestimo.objects.create(
    cliente=clientes[1],
    nome=clientes[1].nome_completo,
    telefone=clientes[1].telefone,
    valor=Decimal('8000'),
    taxa_juros=30,
    registado_por=gestor,
    aprovado_por=gestor,
    data_aprovacao=timezone.now(),
    data_inicio=timezone.now().date() - timedelta(days=30),
)
emp1.registar_pagamento(
    valor_pago=emp1.total_com_multa,
    registado_por=gestor
)
emprestimos.append(emp1)
print(f"✔ Empréstimo quitado: {emp1.numero_contrato}")

# Cliente2: empréstimo em atraso (multa)
emp2 = Emprestimo.objects.create(
    cliente=clientes[2],
    nome=clientes[2].nome_completo,
    telefone=clientes[2].telefone,
    valor=Decimal('15000'),
    taxa_juros=30,
    registado_por=gestor,
    aprovado_por=gestor,
    data_aprovacao=timezone.now(),
    data_inicio=timezone.now().date() - timedelta(days=32),  # atraso de 2 dias (prazo multa = 5)
)
emprestimos.append(emp2)
print(f"✔ Empréstimo em atraso: {emp2.numero_contrato} (dias atraso: {emp2.dias_atraso})")

# Cliente3: empréstimo em incumprimento (>5 dias)
emp3 = Emprestimo.objects.create(
    cliente=clientes[3],
    nome=clientes[3].nome_completo,
    telefone=clientes[3].telefone,
    valor=Decimal('12000'),
    taxa_juros=30,
    registado_por=gestor,
    aprovado_por=gestor,
    data_aprovacao=timezone.now(),
    data_inicio=timezone.now().date() - timedelta(days=40),  # atraso 10 dias
)
emprestimos.append(emp3)
print(f"✔ Empréstimo incumprimento: {emp3.numero_contrato} (dias atraso: {emp3.dias_atraso})")

# Cliente4: empréstimo rejeitado
emp4 = Emprestimo.objects.create(
    cliente=clientes[4],
    nome=clientes[4].nome_completo,
    telefone=clientes[4].telefone,
    valor=Decimal('5000'),
    taxa_juros=30,
    registado_por=gestor,
    status='rejeitado',
    motivo_rejeicao='Documentação incompleta'
)
emprestimos.append(emp4)
print(f"✔ Empréstimo rejeitado: {emp4.numero_contrato}")

# Cliente5: empréstimo com multa cancelada
emp5 = Emprestimo.objects.create(
    cliente=clientes[5],
    nome=clientes[5].nome_completo,
    telefone=clientes[5].telefone,
    valor=Decimal('7000'),
    taxa_juros=30,
    registado_por=gestor,
    aprovado_por=gestor,
    data_aprovacao=timezone.now(),
    data_inicio=timezone.now().date() - timedelta(days=35),
)
emp5.cancelar_multa(gestor, 'Cliente entrou em acordo')
emprestimos.append(emp5)
print(f"✔ Empréstimo com multa cancelada: {emp5.numero_contrato}")

# Cliente0 (mesmo) um empréstimo enviado para tribunal (não pode ter outro activo mas vamos criar outro cliente)
emp6 = Emprestimo.objects.create(
    cliente=clientes[0],
    nome=clientes[0].nome_completo,
    telefone=clientes[0].telefone,
    valor=Decimal('20000'),
    taxa_juros=30,
    registado_por=gestor,
    aprovado_por=gestor,
    data_aprovacao=timezone.now(),
    data_inicio=timezone.now().date() - timedelta(days=50),
)
emp6.enviar_para_tribunal(gestor, 'Incumprimento grave')
emprestimos.append(emp6)
print(f"✔ Empréstimo enviado para tribunal: {emp6.numero_contrato}")

# Empréstimo soft deleted
emp_soft = Emprestimo.objects.create(
    cliente=clientes[1],
    nome=clientes[1].nome_completo,
    telefone=clientes[1].telefone,
    valor=Decimal('3000'),
    taxa_juros=30,
    registado_por=gestor,
    aprovado_por=gestor,
)
emp_soft.delete()  # soft delete
emprestimos.append(emp_soft)
print(f"✔ Empréstimo eliminado (soft delete): {emp_soft.numero_contrato}")

# ===================== COMERCIANTES =====================
comerciantes = []

# Comerciante diário, pagamento em dia
com0 = Comerciante.objects.create(
    cliente=clientes[0],
    nome=clientes[0].nome_completo,
    telefone=clientes[0].telefone,
    capital=Decimal('20000'),
    taxa_juros=30,
    prazo_dias=30,
    modalidade_pagamento='diario',
    registado_por=gestor,
    data_inicio=timezone.now().date() - timedelta(days=10),
)
# Registrar pagamentos dos últimos 5 dias
for d in range(5):
    PagamentoDiario.objects.get_or_create(
        comerciante=com0,
        data=timezone.now().date() - timedelta(days=d),
        defaults={'valor_pago': com0.parcela_diaria, 'registado_por': gestor}
    )
comerciantes.append(com0)
print(f"✔ Comerciante diário com pagamentos: {com0.numero_contrato}")

# Comerciante diário em atraso
com1 = Comerciante.objects.create(
    cliente=clientes[1],
    nome=clientes[1].nome_completo,
    telefone=clientes[1].telefone,
    capital=Decimal('15000'),
    taxa_juros=30,
    prazo_dias=30,
    modalidade_pagamento='diario',
    registado_por=gestor,
    data_inicio=timezone.now().date() - timedelta(days=15),
)
# Pagamento apenas no primeiro dia
PagamentoDiario.objects.get_or_create(
    comerciante=com1,
    data=timezone.now().date() - timedelta(days=14),
    defaults={'valor_pago': com1.parcela_diaria, 'registado_por': gestor}
)
comerciantes.append(com1)
print(f"✔ Comerciante diário em atraso: {com1.numero_contrato}")

# Comerciante semanal
com2 = Comerciante.objects.create(
    cliente=clientes[2],
    nome=clientes[2].nome_completo,
    telefone=clientes[2].telefone,
    capital=Decimal('25000'),
    taxa_juros=30,
    prazo_dias=28,  # 4 semanas
    modalidade_pagamento='semanal',
    registado_por=gestor,
    data_inicio=timezone.now().date() - timedelta(days=14),
)
# Pagamento da primeira semana
data_primeira_semana = (timezone.now().date() - timedelta(days=14))
PagamentoDiario.objects.get_or_create(
    comerciante=com2,
    data=data_primeira_semana,
    defaults={'valor_pago': com2.parcela_semanal, 'registado_por': gestor}
)
comerciantes.append(com2)
print(f"✔ Comerciante semanal: {com2.numero_contrato}")

# Comerciante com multa cancelada
com3 = Comerciante.objects.create(
    cliente=clientes[3],
    nome=clientes[3].nome_completo,
    telefone=clientes[3].telefone,
    capital=Decimal('10000'),
    taxa_juros=30,
    prazo_dias=30,
    modalidade_pagamento='diario',
    registado_por=gestor,
    data_inicio=timezone.now().date() - timedelta(days=10),
)
com3.cancelar_multa(gestor, 'Cliente negociou')
comerciantes.append(com3)
print(f"✔ Comerciante com multa cancelada: {com3.numero_contrato}")

# Comerciante enviado para tribunal
com4 = Comerciante.objects.create(
    cliente=clientes[4],
    nome=clientes[4].nome_completo,
    telefone=clientes[4].telefone,
    capital=Decimal('18000'),
    taxa_juros=30,
    prazo_dias=30,
    modalidade_pagamento='diario',
    registado_por=gestor,
    data_inicio=timezone.now().date() - timedelta(days=20),
)
com4.enviar_para_tribunal(gestor, 'Múltiplos atrasos')
comerciantes.append(com4)
print(f"✔ Comerciante enviado para tribunal: {com4.numero_contrato}")

# Comerciante soft deleted
com_soft = Comerciante.objects.create(
    cliente=clientes[5],
    nome=clientes[5].nome_completo,
    telefone=clientes[5].telefone,
    capital=Decimal('5000'),
    taxa_juros=30,
    prazo_dias=30,
    modalidade_pagamento='diario',
    registado_por=gestor,
)
com_soft.delete()
comerciantes.append(com_soft)
print(f"✔ Comerciante eliminado (soft delete): {com_soft.numero_contrato}")

# ===================== REQUISIÇÕES =====================
req1 = RequisicaoCliente.objects.create(
    cliente=clientes[0],
    valor_pedido=Decimal('15000'),
    finalidade='Expansão do negócio',
    status='submetido',
)
print(f"✔ Requisição submetida: {req1}")

req2 = RequisicaoCliente.objects.create(
    cliente=clientes[1],
    valor_pedido=Decimal('8000'),
    finalidade='Compra de mercadoria',
    status='em_analise',
    resposta_por=gestor,
    data_resposta=timezone.now(),
)
print(f"✔ Requisição em análise: {req2}")

# Requisição aprovada com empréstimo associado
emp_req = Emprestimo.objects.create(
    cliente=clientes[2],
    nome=clientes[2].nome_completo,
    telefone=clientes[2].telefone,
    valor=Decimal('12000'),
    taxa_juros=30,
    registado_por=gestor,
    aprovado_por=gestor,
    data_aprovacao=timezone.now(),
)
req3 = RequisicaoCliente.objects.create(
    cliente=clientes[2],
    valor_pedido=Decimal('12000'),
    finalidade='Capital de giro',
    status='aprovado',
    emprestimo=emp_req,
    resposta_por=gestor,
    data_resposta=timezone.now(),
)
print(f"✔ Requisição aprovada: {req3}")

# Requisição rejeitada
req4 = RequisicaoCliente.objects.create(
    cliente=clientes[3],
    valor_pedido=Decimal('5000'),
    finalidade='Pagamento de dívidas',
    status='rejeitado',
    resposta_por=gestor,
    data_resposta=timezone.now(),
    nota_gestor='Crédito recusado por análise de risco',
)
print(f"✔ Requisição rejeitada: {req4}")

# ===================== LANÇAMENTOS DE PAGAMENTO =====================
lanc1 = LancamentoPagamento.objects.create(
    emprestimo=emp0,
    metodo='transferencia',
    valor_pago=Decimal('1000'),
    tipo_pagamento='parcial',
    submetido_por=clientes[0],
    status='pendente',
)
print(f"✔ Lançamento pendente: {lanc1}")

# Validar um lançamento
lanc1.validar(gestor)
print(f"✔ Lançamento validado: {lanc1}")

lanc2 = LancamentoPagamento.objects.create(
    emprestimo=emp2,
    metodo='mpesa',
    valor_pago=Decimal('2000'),
    tipo_pagamento='total',
    submetido_por=clientes[2],
    status='pendente',
)
print(f"✔ Lançamento pendente: {lanc2}")

# ===================== SOLICITAÇÕES PÚBLICAS =====================
sol1 = SolicitacaoPublica.objects.create(
    nome_completo='João da Silva',
    telefone='25884567890',
    valor_pedido=Decimal('10000'),
    finalidade='Compra de equipamento',
    status='submetido',
    ip_origem='192.168.1.1',
)
print(f"✔ Solicitação pública submetida: {sol1}")

sol2 = SolicitacaoPublica.objects.create(
    nome_completo='Maria José',
    telefone='25884567891',
    valor_pedido=Decimal('5000'),
    finalidade='Pagamento de fornecedores',
    status='em_analise',
)
print(f"✔ Solicitação pública em análise: {sol2}")

# ===================== LOGS =====================
LogActividade.registar(
    tipo='sistema',
    descricao='Carga automática de dados de teste',
    utilizador=admin
)
LogActividade.registar(
    tipo='acesso',
    descricao='Teste de login',
    utilizador=gestor,
    request=None
)
print("✔ Logs registados")

# ===================== LICENÇA =====================
lic = LicencaSistema.obter_ou_criar()
print(f"✔ Licença: {lic}")

print("\n✅ Dados carregados com sucesso!\n")
print("===== RESUMO =====")
print(f"Utilizadores: {User.objects.count()}")
print(f"Empréstimos: {Emprestimo.objects.count()} (activos: {Emprestimo.active_objects.count()})")
print(f"Comerciantes: {Comerciante.objects.count()} (activos: {Comerciante.active_objects.count()})")
print(f"Requisições: {RequisicaoCliente.objects.count()}")
print(f"Lançamentos: {LancamentoPagamento.objects.count()}")
print(f"Solicitações públicas: {SolicitacaoPublica.objects.count()}")
print("==================\n")