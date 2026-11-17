# Organização dos Templates OSM v7

## Estrutura por módulo

### auth/ (autenticação)
- login.html, trocar_senha.html, ip_bloqueado.html, verificar_codigo_admin.html

### emprestimos/ (gestão de empréstimos)
- emprestimos.html, emprestimo_detalhe.html, emprestimo_form.html
- emprestimo_sem_conta.html, lancamento_form.html, lancamento_parcial_form.html
- lancamentos_lista.html, aprovacoes.html, inadimplencia.html

### comerciantes_app/ (gestão de comerciantes)
- comerciantes.html, comerciante_detalhe.html, comerciante_form.html

### pagamentos_app/ (pagamentos e cobrança)
- pagamentos.html, cobranca.html, exportar.html, historico.html

### admin/ (administração)
- utilizadores.html, utilizador_form.html, utilizador_ficha.html
- configuracoes.html, relatorios.html, actividades.html
- licenca_painel.html, licenca_bloqueada.html

### cliente/ (portal do cliente)
- portal_cliente.html, requisicao_form.html
- solicitar_publico.html, solicitar_sucesso.html
- solicitacoes_lista.html, solicitacao_detalhe.html

### sistema/ (sistema geral)
- base.html, painel.html, landing.html, offline.html

### includes/ (fragmentos HTMX)
- credito_form.html, creditos_lista.html

### ../pdfs/ (PDFs)
- contrato.html, cobranca_aviso.html

### ../emails/ (Emails)
- cobranca_email.html

---
Nota: Os ficheiros mantêm os seus caminhos originais (osm/nome.html)
para compatibilidade com as views. Esta estrutura documenta a organização lógica.
