// static/js/cobranca-sms.js

const banco_nome   = "{{ banco.banco|escapejs }}";
const banco_conta  = "{{ banco.conta|escapejs }}";
const banco_nib    = "{{ banco.nib|escapejs }}";
const telefone_osm = "{{ banco.telefone_contacto|default:'258872031215'|escapejs }}";

const TPLS = {
  aviso:      `{nome}, a sua parcela do contrato {contrato} (MT {valor}) vence em 3 dias ({data}). Efectue o pagamento: ${banco_nome} | Conta ${banco_conta} | NIB ${banco_nib}. OSM Microcrédito.`,
  atraso:     `Prezado(a) {nome}, a parcela do contrato {contrato} (MT {valor}) está em atraso. Deposite: ${banco_nome} | Conta ${banco_conta} | NIB ${banco_nib}. Prazo: {data}. Tel: ${telefone_osm}`,
  urgente:    `URGENTE — {nome}: contrato {contrato} com parcela(s) em falta (MT {valor}). Regularize até {data}. Banco: ${banco_nome} | Conta ${banco_conta}. Tel: ${telefone_osm}`,
  lembrete:   `{nome}, lembre-se que a parcela do contrato {contrato} (MT {valor}) vence em {data}. Efectue o pagamento: ${banco_nome} | Conta ${banco_conta} | NIB ${banco_nib}.`,
  dia_venc:   `{nome}, HOJE é o dia de pagamento da parcela do contrato {contrato} (MT {valor}). Deposite: ${banco_nome} | Conta ${banco_conta} | NIB ${banco_nib}. OSM Microcrédito.`,
  atraso1d:   `{nome}, a parcela do contrato {contrato} (MT {valor}) está em atraso. Regularize urgentemente: ${banco_nome} | Conta ${banco_conta} | NIB ${banco_nib}. Juros de mora de 2%/dia aplicados. Tel: ${telefone_osm}`,
  atraso7d:   `AVISO — {nome}: contrato {contrato} com 7 dias de atraso. Mora acumulada: MT {mora}. Total a pagar: MT {totalMora}. Regularize: ${banco_nome} | Conta ${banco_conta}. Tel: ${telefone_osm}`,
  atraso15d:  `URGENTE — {nome}: contrato {contrato} com 15 dias de atraso. Mora acumulada: MT {mora}. Total a pagar: MT {totalMora}. Contacte-nos imediatamente: ${telefone_osm}. OSM Microcrédito.`,
  aviso_legal:`AVISO LEGAL — {nome}: contrato {contrato} com 30 dias de atraso. Mora: MT {mora}. Total: MT {totalMora}. Sem regularização, serão tomadas medidas judiciais. Tel: ${telefone_osm}`,
  agradecimento:`Obrigado(a) {nome}! Pagamento do contrato {contrato} recebido com sucesso. OSM Microcrédito agradece a sua pontualidade.`,
};

let activeChip = null;

function setTpl(key, button) {
  const textarea = document.getElementById('sms-msg');
  if (TPLS[key]) {
    textarea.value = TPLS[key];
    updateCharCount();

    // Remove active de todos os chips
    document.querySelectorAll('.template-chip').forEach(chip => chip.classList.remove('active'));
    button.classList.add('active');
    activeChip = key;
  }
}

function updateCharCount() {
  const msg = document.getElementById('sms-msg').value || '';
  const len = msg.length;
  const smsCnt = Math.ceil(len / 160) || 1;
  const el = document.getElementById('char-counter');
  el.textContent = `${len} / 160 caracteres · ${smsCnt} SMS`;
  el.className = 'sms-char-counter' + (len > 320 ? ' over' : len > 160 ? ' warn' : '');
}

function updateSelCount() {
  const checked = document.querySelectorAll('input[name="dest"]:checked').length;
  document.getElementById('sel-count').textContent = checked + ' sel.';
}

function toggleItem(label) {
  if (event.target.type === 'checkbox') return;
  const cb = label.querySelector('input[type=checkbox]');
  cb.checked = !cb.checked;
  label.classList.toggle('selected', cb.checked);
  updateSelCount();
}

function selAll(val) {
  document.querySelectorAll('input[name="dest"]').forEach(cb => {
    cb.checked = val;
    const item = cb.closest('.cliente-item');
    if (item) item.classList.toggle('selected', val);
  });
  updateSelCount();
}

function confirmSend() {
  const cnt = document.querySelectorAll('input[name="dest"]:checked').length;
  const msg = document.getElementById('sms-msg').value.trim();
  if (!msg)  { alert('Escreva uma mensagem primeiro.'); return false; }
  if (cnt === 0) { alert('Seleccione pelo menos um destinatário.'); return false; }
  return confirm(`Enviar SMS a ${cnt} cliente(s)?`);
}

function filterHistory() {
  const q = document.getElementById('hist-search').value.toLowerCase();
  document.querySelectorAll('.hist-row').forEach(r => {
    r.style.display = r.dataset.nome?.includes(q) ? '' : 'none';
  });
}

function toggleBankEdit() {
  const edit = document.getElementById('bank-edit');
  const show = edit.style.display === 'none';
  edit.style.display = show ? 'block' : 'none';
}

// Limpar campo após envio bem-sucedido
function setupFormClear() {
  const form = document.getElementById('sms-form');
  if (form) {
    form.addEventListener('submit', function() {
      setTimeout(() => {
        document.getElementById('sms-msg').value = '';
        updateCharCount();
        document.querySelectorAll('.template-chip').forEach(chip => chip.classList.remove('active'));
        activeChip = null;
      }, 100);
    });
  }
}

// Inicialização
document.addEventListener('DOMContentLoaded', function() {
  // Configurar templates rápidos
  document.querySelectorAll('#template-buttons .template-chip').forEach(button => {
    const key = button.getAttribute('data-key');
    button.addEventListener('click', function() {
      setTpl(key, this);
    });
  });

  updateSelCount();
  updateCharCount();

  // Marcar clientes já selecionados
  document.querySelectorAll('input[name="dest"]:checked').forEach(cb => {
    cb.closest('.cliente-item')?.classList.add('selected');
  });

  setupFormClear();
});