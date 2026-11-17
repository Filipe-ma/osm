from django.urls import path
from . import views

urlpatterns = [
    # Landing & Auth
    path('ladim/', views.view_landing, name='landing'),
    path('', views.view_login, name='login'),
    path('logout/', views.view_logout, name='logout'),
    path('trocar-senha/', views.view_trocar_senha, name='trocar_senha'),
 
    # Painel
    path('painel/', views.view_painel, name='painel'),
    # Na secção de Empréstimos (ou crie uma nova secção "Créditos")
    path('creditos/cliente/<int:pk>/', views.view_creditos_cliente, name='creditos_cliente'),
        # Empréstimos
    path('emprestimos/', views.view_emprestimos, name='emprestimos'),
    path('emprestimos/novo/', views.view_emprestimo_novo, name='emprestimo_novo'),
    path('emprestimos/<int:pk>/', views.view_emprestimo_detalhe, name='emprestimo_detalhe'),
    path('emprestimos/<int:pk>/editar/', views.view_emprestimo_editar, name='emprestimo_editar'),
    path('emprestimos/<int:pk>/eliminar/', views.view_emprestimo_eliminar, name='emprestimo_eliminar'),
    path('emprestimos/<int:pk>/pagar/', views.view_registar_pagamento, name='registar_pagamento'),
    path('emprestimos/<int:pk>/declaracao.pdf', views.view_pdf_declaracao, name='pdf_declaracao'),
    path('emprestimos/<int:pk>/contrato/visualizar/', views.visualizar_contrato, name='visualizar_contrato'),
    path('emprestimos/<int:pk>/contrato/baixar/', views.baixar_contrato, name='baixar_contrato'),
    path('emprestimos/<int:pk>/lista-negra/', views.view_emprestimo_lista_negra, name='emprestimo_lista_negra'),
    path('pagamentos/', views.view_pagamentos, name='pagamentos'),

    # Aprovações
    path('aprovacoes/', views.view_aprovacoes, name='aprovacoes'),
    path('aprovacoes/<int:pk>/aprovar/', views.view_aprovar, name='aprovar'),
    path('aprovacoes/<int:pk>/rejeitar/', views.view_rejeitar, name='rejeitar'),

    # Inadimplência
    path('inadimplencia/', views.view_inadimplencia, name='inadimplencia'),

    # Comerciantes
    path('comerciantes/', views.view_comerciantes, name='comerciantes'),
    path('comerciantes/novo/', views.view_comerciante_novo, name='comerciante_novo'),
    path('comerciantes/<int:pk>/', views.view_comerciante_detalhe, name='comerciante_detalhe'),
    path('comerciantes/<int:pk>/creditos/', views.view_creditos_comerciante, name='creditos_comerciante'),
    path('comerciantes/<int:pk>/editar/', views.view_comerciante_editar, name='comerciante_editar'),
    path('comerciantes/<int:pk>/pagar/', views.view_confirmar_pagamento, name='confirmar_pagamento'),
    path('comerciantes/<int:pk>/pagar/<str:data>/', views.view_confirmar_pagamento, name='confirmar_pagamento_data'),
    path('comerciantes/<int:pk>/cancelar/', views.view_cancelar_pagamento, name='cancelar_pagamento'),
    path('comerciantes/<int:pk>/anular-data/', views.view_anular_pagamento_data, name='anular_pagamento_data'),
    path('comerciante/<int:pk>/recibo/<int:pagamento_pk>/', views.view_recibo_comerciante_pdf, name='recibo_comerciante_pdf'),

    # Créditos – Empréstimos (HTMX)
    path('emprestimo/<int:pk>/creditos/', views.creditos_lista, name='creditos_lista'),
    path('emprestimo/<int:pk>/creditos/comerciante/', views.creditos_lista_comerciante, name='comerciante_credito'),
  
    path('emprestimo/<int:pk>/credito/novo/form/', views.adicionar_credito_form, name='adicionar_credito_form'),
    path('emprestimo/<int:pk>/credito/novo/', views.adicionar_credito, name='adicionar_credito'),
    path('emprestimo/<int:pk>/creditos/detalhe/', views.creditos_detalhe_ajax, name='creditos_detalhe_ajax'),
 
    # Créditos – Comerciantes (HTMX)
    path('comerciante/<int:pk>/creditos/', views.creditos_lista_comerciantes, name='creditos_lista_comerciante'),
    path('comerciante/<int:pk>/credito/novo/form/', views.adicionar_credito_comerciante_form, name='adicionar_credito_comerciante_form'),
    path('comerciante/<int:pk>/credito/novo/', views.adicionar_credito_comerciante, name='adicionar_credito_comerciante'),

    # Cobrança
    path('cobranca/', views.view_cobranca, name='cobranca'),
    path('cobranca/sms/', views.view_enviar_sms, name='enviar_sms'),
    path('cobranca/bulk/', views.view_sms_bulk, name='sms_bulk'),
    path('cobranca/email-bulk/', views.view_email_cobranca_bulk, name='email_cobranca_bulk'),
    path('cobranca/banco/', views.view_banco_editar, name='banco_editar'),
    path('cobranca/email/<int:pk>/', views.view_enviar_email_cobranca, name='enviar_email_cobranca'),

    # Relatórios
    path('relatorios/', views.view_relatorios, name='relatorios'),
    path('historico/', views.view_historico, name='historico'),
    path('exportar/', views.view_exportar, name='exportar'),
    path('exportar/csv/', views.view_exportar_csv, name='exportar_csv'),

    # Utilizadores
    path('utilizadores/', views.view_utilizadores, name='utilizadores'),
    path('utilizadores/novo/', views.view_utilizador_novo, name='utilizador_novo'),
    path('utilizadores/<int:pk>/editar/', views.view_utilizador_editar, name='utilizador_editar'),
    path('utilizadores/<int:pk>/toggle/', views.view_utilizador_toggle, name='utilizador_toggle'),
    path('utilizadores/<int:pk>/eliminar/', views.view_utilizador_eliminar, name='utilizador_eliminar'),
    path('utilizadores/<int:pk>/ficha/', views.view_utilizador_ficha_pdf, name='utilizador_ficha_pdf'),
    path('utilizadores/<int:pk>/ficha.pdf', views.view_utilizador_pdf, name='utilizador_pdf'),
    path('utilizadores/<int:pk>/converter-tipo/', views.view_converter_tipo_cliente, name='converter_tipo_cliente'),
    path('utilizadores/<int:pk>/lista-negra/', views.view_lista_negra_toggle, name='lista_negra_toggle'),

    # Configurações
    path('actividades/', views.view_actividades, name='actividades'),
    path('configuracoes/', views.view_configuracoes, name='configuracoes'),
    path('configuracoes/taxas/', views.view_taxas_editar, name='taxas_editar'),
    path('configuracoes/sms-email/', views.view_sms_config_editar, name='sms_config_editar'),
    path('configuracoes/testar-sms/', views.view_testar_sms, name='testar_sms'),
    path('emprestimos/<int:pk>/aviso-pdf/', views.view_gerar_aviso_cobranca_pdf, name='aviso_cobranca_pdf'),

    # Portal Cliente
    path('minha-conta/', views.view_portal_cliente, name='portal_cliente'),
    path('minha-conta/requisicao/', views.view_requisicao_nova, name='requisicao_nova'),

    # Lançamentos de Pagamento
    path('emprestimos/<int:pk>/lancamentos/', views.view_lancamentos_lista, name='lancamentos_lista'),
    path('emprestimos/<int:pk>/lancamentos/novo/', views.view_lancamento_novo, name='lancamento_novo'),
    path('emprestimos/<int:pk>/lancamentos/parcial/', views.view_lancamento_parcial, name='lancamento_parcial'),
    path('lancamentos/<int:pk>/validar/', views.view_lancamento_validar, name='lancamento_validar'),
    path('lancamentos/<int:pk>/rejeitar/', views.view_lancamento_rejeitar, name='lancamento_rejeitar'),
    path('lancamentos/<int:pk>/recibo/', views.view_lancamento_recibo, name='lancamento_recibo'),
    path('lancamentos/<int:pk>/fatura/', views.view_lancamento_fatura, name='lancamento_fatura'),
    path('lancamentos/<int:pk>/fatura-dupla/', views.view_lancamento_fatura_dupla, name='lancamento_fatura_dupla'),
    path('lancamentos/<int:pk>/recibo-pos/', views.view_lancamento_recibo_pos, name='lancamento_recibo_pos'),
    path('lancamentos/<int:pk>/fatura-invoice/', views.view_lancamento_fatura_turbohost, name='lancamento_fatura_turbohost'),

    # Solicitações Públicas
    path('solicitar/', views.view_solicitar_publico, name='solicitar_publico'),
    path('solicitar/sucesso/', views.view_solicitar_sucesso, name='solicitar_sucesso'),
    path('solicitacoes/', views.view_solicitacoes_lista, name='solicitacoes_lista'),
    path('solicitacoes/<int:pk>/', views.view_solicitacao_detalhe, name='solicitacao_detalhe'),
    path('solicitacoes/<int:pk>/aprovar/', views.view_solicitacao_aprovar, name='solicitacao_aprovar'),
    path('solicitacoes/<int:pk>/rejeitar/', views.view_solicitacao_rejeitar, name='solicitacao_rejeitar'),
    path('solicitacoes/<int:pk>/em-analise/', views.view_solicitacao_em_analise, name='solicitacao_em_analise'),

    # API
    path('api/kpis/', views.api_kpis, name='api_kpis'),
    path('api/emprestimos/', views.api_emprestimos, name='api_emprestimos'),
    path('api/comerciante/<int:comerciante_id>/parcela/', views.detalhes_parcela_por_data, name='detalhes_parcela'),

    # Licença (superadmin)
    path('licenca/', views.view_licenca_painel, name='licenca_painel'),
    path('licenca/renovar/', views.view_licenca_renovar, name='licenca_renovar'),
    path('licenca/pausar/', views.view_licenca_pausar, name='licenca_pausar'),
    path('verificar-codigo-admin/', views.view_verificar_codigo_admin, name='verificar_codigo_admin'),

    # Tribunal, Multa, Sem Conta
    path('emprestimos/<int:pk>/cancelar-multa/', views.view_cancelar_multa, name='cancelar_multa'),
    path('emprestimos/<int:pk>/tribunal/', views.view_enviar_tribunal, name='enviar_tribunal'),
    path('emprestimos/<int:pk>/retirar-tribunal/', views.view_retirar_tribunal, name='retirar_tribunal'),
    path('emprestimos/<int:pk>/associar-conta/', views.view_associar_conta, name='associar_conta'),
    path('emprestimos/<int:pk>/converter-tipo/', views.view_converter_tipo_emprestimo, name='converter_tipo_emprestimo'),
    path('emprestimos/sem-conta/', views.view_emprestimo_sem_conta, name='emprestimo_sem_conta'),

    # PWA
    path('manifest.json', views.view_pwa_manifest, name='pwa_manifest'),
    path('offline.html', views.view_offline, name='pwa_offline'),
]