# OSM Microcrédito v5 — Changelog

## 🔧 Correcções Críticas (Dados a Desaparecer)

### Causa Raiz Identificada
O problema de dados a desaparecerem após algumas horas era causado por **3 falhas combinadas**:

1. **Service Worker sem cache de sessão** — O SW antigo não guardava páginas autenticadas em cache.
   Quando o iOS limpava a cache do Safari, a sessão perdia-se e o utilizador era redirecionado para login
   sem aviso, dando a impressão de que os dados tinham desaparecido.

2. **`credentials: 'same-origin'` em falta** — O iOS Safari exige este header explicitamente em todos
   os requests do SW para manter a sessão autenticada. Sem ele, o Safari rejeita silenciosamente.

3. **Evento `online` não fiável no iOS** — O Safari iOS não dispara `window.online` de forma consistente,
   pelo que o `syncQueue()` nunca era chamado automaticamente. Adicionado polling de 30s como fallback.

---

## 📁 Ficheiros Alterados

### `static/js/sw.js` ← SUBSTITUÍDO COMPLETAMENTE
- Estratégia `cache-first` para assets estáticos (CSS, JS, imagens)
- Estratégia `network-first + cache fallback` para páginas HTML autenticadas
- `credentials: 'same-origin'` em todos os fetches (fix iOS Safari)
- Limpeza automática de caches antigos ao activar
- Background Sync + notificação para sincronização
- Verificador de updates com prompt ao utilizador

### `static/js/offline-sync.js` ← SUBSTITUÍDO COMPLETAMENTE
- Polling a cada 30s como fallback para iOS (fix evento `online`)
- Limite de 10 tentativas por item na fila
- Cache local via IndexedDB para dados críticos
- Toast de sucesso após sincronização

### `osm/templates/osm/base.html` ← ACTUALIZADO
- SW registado após `window.load` (requisito Safari)
- Dexie actualizado para 3.2.7 (versão estável)
- Meta tags iOS adicionais
- Verificador de updates do SW

### `osm/templates/osm/offline.html` ← REDESENHADO
- Sem Django template tags (funciona como ficheiro estático)
- Redireccionamento automático quando internet volta
- Mostra contagem de itens pendentes de sincronização
- Polling iOS-safe a cada 3s

---

## 🆕 Funcionalidades Novas

### BulkSMS Integrado
**Ficheiro:** `osm/views.py` → função `enviar_sms_bulksms()`
- Envio real via BulkSMS API (sem bibliotecas externas, usa `urllib`)
- Normalização automática de números moçambicanos (+258)
- Log de sucesso/erro por cada SMS
- Fallback para modo simulação se API token não configurado

### Configuração SMS/Email na Interface
**Ficheiro:** `osm/templates/osm/configuracoes.html`
- 4 abas: Conta · Taxas · SMS · Email
- Campo API Token com toggle mostrar/ocultar
- Toggle switches modernos para activar/desactivar funcionalidades
- Guia passo-a-passo para configurar Gmail
- Teste de SMS directamente da interface
- Estatísticas de SMS enviados

### Página de Cobrança Melhorada
**Ficheiro:** `osm/templates/osm/cobranca.html`
- Banner de aviso quando BulkSMS não configurado
- Templates de SMS melhorados (Aviso, Atraso, Urgente, Jurídico)
- Contador de caracteres em tempo real
- Filtro de histórico por nome
- Fix: filtro de status corrigido (`vencido`/`incumprimento` em vez de `atraso`)

### Template PDF de Cobrança
**Ficheiro:** `osm/templates/pdfs/cobranca_aviso.html`
- Design profissional com cabeçalho da empresa
- Strip de alerta vermelho para clientes em atraso
- KPIs financeiros (capital, saldo, mora)
- Dados de pagamento completos (banco + e-Mola)
- Valor total em destaque
- Nota legal e campos de assinatura

### Alertas SMS Automáticos (Cron)
**Ficheiro:** `osm/management/commands/enviar_alertas_sms.py`
```bash
# Testar (sem enviar)
python manage.py enviar_alertas_sms --dry-run

# Executar
python manage.py enviar_alertas_sms

# Configurar no cron (diário às 8h)
0 8 * * * /caminho/venv/bin/python /caminho/manage.py enviar_alertas_sms
```

---

## 🗄️ Base de Dados

### Migration a Aplicar
```bash
python manage.py migrate osm 0002_sms_email_config
```

### Novos campos em `ConfiguracaoBancaria`
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `bulksms_api_token` | CharField | API Token BulkSMS |
| `bulksms_sender` | CharField | Nome remetente (máx 11 car.) |
| `sms_alerta_dias` | PositiveIntegerField | Dias antes do vencimento p/ alerta |
| `sms_cobranca_auto` | BooleanField | Cobrança automática diária |
| `email_smtp_host` | CharField | Servidor SMTP |
| `email_smtp_port` | PositiveIntegerField | Porta SMTP |
| `email_smtp_user` | CharField | Email remetente |
| `email_smtp_pass` | CharField | Senha de aplicação |
| `email_smtp_tls` | BooleanField | Usar TLS |
| `email_ativo` | BooleanField | Activar emails do sistema |

---

## ⚙️ Deploy no Render/Servidor

```bash
# 1. Aplicar migration
python manage.py migrate

# 2. Colectar estáticos
python manage.py collectstatic --noinput

# 3. Configurar variáveis de ambiente (opcional — alternativa ao modelo)
BULKSMS_API_TOKEN=seu-token-aqui
EMAIL_SMTP_USER=seuemail@gmail.com
EMAIL_SMTP_PASS=senha-aplicacao-16-digitos

# 4. Configurar cron para SMS automático (opcional)
0 8 * * * python manage.py enviar_alertas_sms
```

---

## 📱 iOS — Instalar como PWA

1. Abrir o OSM no **Safari** (não Chrome/Firefox)
2. Tocar em **Partilhar** → **Adicionar ao Ecrã Principal**
3. A partir deste momento funciona como app nativa
4. Os dados ficam guardados localmente mesmo sem internet

**Nota:** A funcionalidade offline no iOS requer Safari 13+ e iOS 13+.
