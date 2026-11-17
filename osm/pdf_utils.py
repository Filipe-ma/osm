"""
OSM Microcrédito — Gerador de PDFs Profissional
Usa ReportLab para gerar contratos, fichas, recibos, faturas e declarações.
v3.7: Padrão visual unificado: cabeçalho escuro, Times New Roman, dourado.
      Declaração em página única, tamanho 12, sem duplicação.
"""
import os
from io import BytesIO
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from reportlab.lib.pagesizes import A4, A6
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable, KeepTogether, Image)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

# ══════════════════════════════════════════════════════════════
# FONTE TIMES NEW ROMAN (built‑in no ReportLab)
# ══════════════════════════════════════════════════════════════
def _get_font():
    return 'Times-Roman'

FONTE = _get_font()
FONTE_BOLD = 'Times-Bold'

# ══════════════════════════════════════════════════════════════
# CORES
# ══════════════════════════════════════════════════════════════
HEADER_BG    = colors.white
OURO         = colors.white
TITULO_BG    = colors.white
PRETO        = colors.black
CINZA_ESCURO = colors.HexColor('#333333')
CINZA_MED    = colors.HexColor('#888888')
CINZA_CLARO  = colors.HexColor('#f4f4f4')
VERMELHO     = colors.HexColor('#cc0000')
BRANCO       = colors.black

# ══════════════════════════════════════════════════════════════
# DATAS EM PORTUGUÊS
# ══════════════════════════════════════════════════════════════
MESES_PT = {
    1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril',
    5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
    9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
}

def _format_date_pt(data):
    return f"{data.day} de {MESES_PT[data.month]} de {data.year}"

# ══════════════════════════════════════════════════════════════
# CAMINHO DA LOGO
# ══════════════════════════════════════════════════════════════
def _logo_path():
    candidatos = []
    base = getattr(settings, 'BASE_DIR', None)
    if base:
        candidatos.append(os.path.join(str(base), 'static', 'images', 'logo', 'logo.png'))
    for d in getattr(settings, 'STATICFILES_DIRS', []):
        candidatos.append(os.path.join(str(d), 'images', 'logo', 'logo.png'))
    sr = getattr(settings, 'STATIC_ROOT', None)
    if sr:
        candidatos.append(os.path.join(str(sr), 'images', 'logo', 'logo.png'))
    for p in candidatos:
        if os.path.isfile(p):
            return p
    return None

# ══════════════════════════════════════════════════════════════
# CANVAS COM RODAPÉ SIMPLES
# ══════════════════════════════════════════════════════════════
class SimpleCanvas(rl_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        rl_canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
    def save(self):
        n = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._rodape(n)
            rl_canvas.Canvas.showPage(self)
        rl_canvas.Canvas.save(self)
    def _rodape(self, total):
        w, _ = A4
        self.saveState()
        self.setStrokeColor(CINZA_MED)
        self.setLineWidth(0.4)
        self.line(20 * mm, 14 * mm, w - 20 * mm, 14 * mm)
        self.setFillColor(CINZA_MED)
        self.setFont('Times-Roman', 7)
        self.drawString(20 * mm, 9 * mm,
                        'OSM Microcrédito — Documento Confidencial')
        self.drawRightString(w - 20 * mm, 9 * mm,
                             f'Pág. {self._pageNumber} / {total}')
        self.drawCentredString(w / 2, 9 * mm,
                               f'Gerado em {timezone.localdate().strftime("%d/%m/%Y")}')
        self.restoreState()

# ══════════════════════════════════════════════════════════════
# ESTILOS
# ══════════════════════════════════════════════════════════════
def _estilos():
    return {
        'corpo': ParagraphStyle(
            'corpo', fontName=FONTE, fontSize=12, leading=18,
            spaceAfter=8, alignment=TA_JUSTIFY),
        'subtitulo': ParagraphStyle(
            'subtitulo', fontName=FONTE_BOLD, fontSize=12,
            textColor=CINZA_ESCURO, spaceAfter=4, spaceBefore=10, leading=14),
        'clausula_titulo': ParagraphStyle(
            'cl', fontName=FONTE_BOLD, fontSize=12,
            textColor=PRETO, spaceAfter=3, spaceBefore=8),
        'aviso': ParagraphStyle(
            'aviso', fontName=FONTE, fontSize=11,
            textColor=CINZA_MED, spaceAfter=4, alignment=TA_CENTER),
        'aviso_vermelho': ParagraphStyle(
            'aviso_v', fontName=FONTE, fontSize=10,
            textColor=VERMELHO, spaceAfter=4, alignment=TA_CENTER, leading=12),
        'centro': ParagraphStyle(
            'centro', fontName=FONTE, fontSize=12,
            alignment=TA_CENTER, spaceAfter=4),
    }

# ══════════════════════════════════════════════════════════════
# CABEÇALHO OSM ESCURO (com logo e linha dourada)
# ══════════════════════════════════════════════════════════════
def _header(story, titulo_doc, subtitulo=''):
    logo_p = _logo_path()
    if logo_p:
        logo_cell = Image(logo_p, width=22 * mm, height=22 * mm)
    else:
        logo_cell = Paragraph(
            '<b>OSM</b>',
            ParagraphStyle('lg', fontName=FONTE_BOLD, fontSize=20,
                           textColor=BRANCO, alignment=TA_CENTER))
    empresa_cell = Paragraph(
        f'<b>Office Semente Microcrédito, E.I.</b><br/>'
        f'<font size="8">NUIT: {getattr(settings, "OSM_NUIT", "150493129")}</font><br/>'
        f'<font size="8">{getattr(settings, "OSM_MORADA", "EN6 Bairro Centro Hípico, Chimoio, Moçambique")}</font>',
        ParagraphStyle('emp', fontName=FONTE, fontSize=9,
                       textColor=BRANCO, leading=13))
    contactos_cell = Paragraph(
        f'<font size="8">{getattr(settings, "OSM_TEL", "")}</font><br/>'
        f'<font size="8">{getattr(settings, "OSM_EMAIL", "")}</font>',
        ParagraphStyle('cont', fontName=FONTE, fontSize=8,
                       textColor=BRANCO, leading=12, alignment=TA_RIGHT))
    t_topo = Table(
        [[logo_cell, empresa_cell, contactos_cell]],
        colWidths=[28 * mm, 102 * mm, 50 * mm]
    )
    t_topo.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), HEADER_BG),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (0, -1),  6 * mm),
        ('LEFTPADDING',   (1, 0), (1, -1),  4 * mm),
        ('TOPPADDING',    (0, 0), (-1, -1), 5 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5 * mm),
        ('RIGHTPADDING',  (-1, 0), (-1, -1), 5 * mm),
        ('LINEBELOW',     (0, 0), (-1, -1), 2, OURO),
    ]))
    story.append(t_topo)
    t_titulo = Table(
        [[Paragraph(
            titulo_doc.upper(),
            ParagraphStyle('td', fontName=FONTE_BOLD, fontSize=13,
                           textColor=BRANCO, alignment=TA_CENTER)
        )]],
        colWidths=[180 * mm]
    )
    t_titulo.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), TITULO_BG),
        ('TOPPADDING',    (0, 0), (-1, -1), 4 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4 * mm),
        ('LINEBELOW',     (0, 0), (-1, -1), 1.5, OURO),
    ]))
    story.append(t_titulo)
    if subtitulo:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            subtitulo,
            ParagraphStyle('sub2', fontName=FONTE, fontSize=9,
                           textColor=CINZA_MED, alignment=TA_CENTER)))
    story.append(Spacer(1, 6 * mm))

# ══════════════════════════════════════════════════════════════
# TABELA DE DADOS (2 colunas)
# ══════════════════════════════════════════════════════════════
def _tabela_dados(dados):
    rows = [[
        Paragraph(str(lb),
                  ParagraphStyle('tl', fontName=FONTE_BOLD, fontSize=12,
                                 textColor=PRETO)),
        Paragraph(str(vl),
                  ParagraphStyle('tv', fontName=FONTE, fontSize=12,
                                 textColor=PRETO)),
    ] for lb, vl in dados]
    t = Table(rows, colWidths=[60 * mm, 100 * mm])
    t.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [CINZA_CLARO, BRANCO]),
        ('LINEBELOW',      (0, 0), (-1, -2), 0.3, colors.HexColor('#dddddd')),
        ('LEFTPADDING',    (0, 0), (-1, -1), 4 * mm),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 4 * mm),
        ('TOPPADDING',     (0, 0), (-1, -1), 2.5 * mm),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 2.5 * mm),
        ('VALIGN',         (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t

# ══════════════════════════════════════════════════════════════
# ASSINATURAS
# ══════════════════════════════════════════════════════════════
def _assinaturas(story, partes):
    story.append(Spacer(1, 16 * mm))
    story.append(HRFlowable(width='100%', thickness=0.4,
                             color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 2 * mm))
    cols = [Paragraph(
        f'{"_" * 38}<br/><b>{nome}</b><br/>'
        f'<font size="10" color="#888888">{titulo}</font>',
        ParagraphStyle('ass', fontName=FONTE, fontSize=11,
                       alignment=TA_CENTER, leading=14, spaceBefore=10)
    ) for nome, titulo in partes]
    col_w = 160 * mm / len(partes)
    t = Table([cols], colWidths=[col_w] * len(partes))
    t.setStyle(TableStyle([
        ('VALIGN',     (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 8 * mm),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(t)

# ══════════════════════════════════════════════════════════════
# VALOR POR EXTENSO
# ══════════════════════════════════════════════════════════════
def _valor_por_extenso(valor):
    unidades = ['', 'um', 'dois', 'três', 'quatro', 'cinco',
                'seis', 'sete', 'oito', 'nove']
    dezenas  = ['', 'dez', 'vinte', 'trinta', 'quarenta', 'cinquenta',
                'sessenta', 'setenta', 'oitenta', 'noventa']
    centenas = ['', 'cem', 'duzentos', 'trezentos', 'quatrocentos',
                'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']
    esp = {10:'dez', 11:'onze', 12:'doze', 13:'treze', 14:'catorze',
           15:'quinze', 16:'dezasseis', 17:'dezassete', 18:'dezoito', 19:'dezanove'}

    def _lt100(n):
        if n in esp:
            return esp[n]
        if n < 10:
            return unidades[n]
        d, u = divmod(n, 10)
        if u == 0:
            return dezenas[d]
        else:
            return dezenas[d] + ' e ' + unidades[u]

    def _lt1000(n):
        if n == 0:
            return ''
        if n == 100:
            return 'cem'
        c, r = divmod(n, 100)
        return centenas[c] + ((' e ' + _lt100(r)) if r else '')

    n = int(valor)
    if n == 0:
        return 'zero meticais'
    mil, resto = divmod(n, 1000)
    partes = []
    if mil:
        partes.append('mil' if mil == 1
                      else (_lt100(mil) if mil < 100 else _lt1000(mil)) + ' mil')
    if resto:
        partes.append(_lt1000(resto) if resto >= 100 else _lt100(resto))
    return ' e '.join(partes) + ' meticais'

# =============================================================================
# PDF — CONTRATO DE EMPRÉSTIMO
# =============================================================================
def gerar_contrato(emp):
    buffer = BytesIO()
    doc    = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=15 * mm, bottomMargin=22 * mm)
    E     = _estilos()
    story = []
    _header(story,
            'Contrato de Empréstimo de Dinheiro',
            f'N.º {getattr(emp, "numero_contrato", "")}')
    v_num  = float(emp.valor)
    V      = (f'<b><font color="red">'
              f'{v_num:,.2f} MZN ({_valor_por_extenso(v_num)})'
              f'</font></b>')
    data_venc = _format_date_pt(emp.data_vencimento) if emp.data_vencimento else "—"
    D_VENC = f'<b><font color="red">{data_venc}</font></b>'
    D_SIGN = _format_date_pt(timezone.localdate())
    EMP  = '<b>Office Semente Microcrédito, E.I.</b>'
    GER  = '<b>Office Bernardo Ofece Semente</b>'
    MUT  = '<b>MUTUANTE</b>'
    MUR  = '<b>MUTUÁRIO</b>'
    NOME = f'<b>{emp.nome}</b>'
    nac    = getattr(emp, 'nacionalidade', 'Moçambicana')
    cidade = getattr(emp, 'cidade', 'Chimoio')
    tj     = float(getattr(emp, 'taxa_juros', 30))
    tm     = float(getattr(emp, 'taxa_multa', 2))
    tj_ext = 'trinta' if tj == 30 else str(int(tj))
    gar    = getattr(emp, 'garantia',
                     'Penhora de viatura da Marca Toyota Ractis, '
                     'avaliada acima de 50% do valor a pagar.')
    paragrafos = [
        (f'Entre {EMP}, com sede na EN6 Bairro Centro Hípico, Cidade de Chimoio, '
         f'registada na Conservatória do Registo das Entidades Legais de Chimoio com '
         f'número <b>1105038077</b> e com o NUIT <b>150493129</b>, representada neste '
         f'acto por {GER}, na qualidade de <b>Gerente</b>, com poderes bastantes para '
         f'este acto, doravante designada por {MUT},'),
        'E:',
        (f'Nome: {NOME}, Estado civil: <b>{emp.estado_civil or "—"}</b>, '
         f'de nacionalidade <b>{nac}</b>, Funcionário na '
         f'<b>{emp.empregador or "—"}</b>, portador(a) de BI N.º <b>{emp.bi or "—"}</b>, '
         f'NUIT n.º <b>{emp.nuit or "—"}</b>, residente na cidade de '
         f'<b>{cidade}</b>, Bairro <b>{emp.bairro or "—"}</b>, '
         f'doravante denominado(a) {MUR}.'),
        ('As partes acima identificadas têm, entre si, justo e acertado, o presente '
         'contrato de empréstimo de dinheiro, ficando desde já aceito nas cláusulas e '
         'condições abaixo descritas.'),
        (f'<b>CLÁUSULA 1.ª – OBJECTO</b><br/>'
         f'Por meio deste contrato, o {MUT} empresta ao {MUR}, directa e pessoalmente, '
         f'a quantia de {V}, mediante as condições definidas neste contrato.<br/><br/>'
         f'<i>Parágrafo único.</i> A quantia será entregue ao {MUR} por transferência '
         f'bancária ou cheque, no acto de assinatura deste contrato.'),
        (f'<b>CLÁUSULA 2.ª – DO JURO</b><br/>'
         f'Sobre a quantia acima serão aplicados juros compostos de '
         f'<b>{tj:.0f}% ({tj_ext} por cento) mensais</b>.<br/><br/>'
         f'O {MUR} poderá amortizar ou liquidar a dívida antes do vencimento, '
         f'com abatimento proporcional dos juros.'),
        (f'<b>CLÁUSULA 3.ª – DO PAGAMENTO</b><br/>'
         f'O {MUR} obriga-se a restituir o valor tomado em empréstimo com o respectivo '
         f'juro na seguinte forma:<br/><br/>'
         f'O pagamento deve ser efectuado no dia {D_VENC}.<br/><br/>'
         f'<b>1.º</b> O pagamento deve ser feito na conta bancária da {EMP}, '
         f'com domicílio no banco <b>FNB</b>:<br/>'
         f'Número de conta: <b>4551596810001</b><br/>'
         f'NIB: <b>0014 0000 45515968101 86</b><br/><br/>'
         f'<b>2.º</b> O não pagamento do crédito na data acordada será acrescido de '
         f'juros de mora de <b><font color="red">{tm:.0f}% diários</font></b> sobre o '
         f'valor total do crédito.<br/><br/>'
         f'<b>3.º</b> O não pagamento facultará ao {MUT} tomar todas as medidas, sejam '
         f'judiciais ou extrajudiciais, para satisfazer o crédito, sendo todas as despesas '
         f'de cobrança, incluindo <b>honorários advocatícios (fixados em 20% do valor '
         f'total da dívida)</b>, deslocamento e imposto do tribunal, da responsabilidade '
         f'do {MUR}.<br/><br/>'
         f'<b>4.º</b> O {MUR} autoriza o {MUT}, em caso de inadimplemento, a postergar, '
         f'se assim desejar, o prazo deste contrato para liquidação do saldo devedor '
         f'remanescente.'),
        (f'<b>CLÁUSULA 4.ª – DA GARANTIA</b><br/>'
         f'O {MUR} coloca como garantia o seguinte bem:<br/>'
         f'<b>{gar}</b>'),
        (f'<b>CLÁUSULA 5.ª – DAS OBRIGAÇÕES DO {MUR}</b><br/>'
         f'Sem prejuízo de outras disposições, constituem obrigações do {MUR}:<br/>'
         f'I. Restituir, no prazo convencionado, o pagamento devido, conforme as datas '
         f'e meios deste contrato;<br/>'
         f'II. Informar o {MUT} sobre insolvência, falência ou qualquer acção ou '
         f'execução declarada contra si.'),
        (f'<b>CLÁUSULA 6.ª – DAS OBRIGAÇÕES DO {MUT}</b><br/>'
         f'Sem prejuízo de outras disposições, constituem obrigações do {MUT}:<br/>'
         f'I. Receber o pagamento do empréstimo nos termos definidos neste contrato;<br/>'
         f'II. Não solicitar a restituição do valor antes do prazo convencionado ou '
         f'de forma diferente dos meios definidos neste contrato.'),
        (f'<b>CLÁUSULA 7.ª – DA TOLERÂNCIA</b><br/>'
         f'Qualquer condescendência do {MUT} para com o {MUR}, quanto ao cumprimento de '
         f'qualquer cláusula, constituirá mera tolerância e não importará em alteração '
         f'ou modificação das cláusulas contratuais.'),
        ('<b>CLÁUSULA 8.ª – DA EXTINÇÃO DO CONTRATO</b><br/>'
         'O presente contrato poderá ser extinto nas seguintes hipóteses:<br/>'
         'I. Pela inadimplência de qualquer uma das partes;<br/>'
         'II. Por distrato solicitado por qualquer uma das partes;<br/>'
         'III. Pelo descumprimento das obrigações previstas neste contrato.'),
        (f'<b>CLÁUSULA 9.ª – DO DESCUMPRIMENTO</b><br/>'
         f'O descumprimento de qualquer cláusula deste contrato, por qualquer das '
         f'partes, acarretará rescisão imediata do mesmo.'),
        (f'<b>CLÁUSULA 10.ª – DO VENCIMENTO ANTECIPADO DA DÍVIDA</b><br/>'
         f'Haverá antecipação da dívida do {MUR} que poderá ser exigida integralmente '
         f'nas seguintes hipóteses:<br/>'
         f'I. Se o {MUR} tiver os seus títulos protestados, entrar em estado de '
         f'insolvência ou concordata, ou sofrer medidas que afectem os direitos '
         f'creditórios do {MUT}.'),
        ('<b>CLÁUSULA 11.ª – DO FORO</b><br/>'
         'Fica desde já eleito o foro da comarca da cidade de Chimoio, Moçambique, '
         'para serem resolvidas eventuais pendências decorrentes deste contrato.'),
        (f'Por estarem assim certos e ajustados, firmam os signatários este instrumento '
         f'em <b>02 (duas) vias</b> de igual teor e forma, e para único fim de direito, '
         f'diante de uma (01) testemunha abaixo, que também o subscrevem.<br/><br/>'
         f'Cidade de Chimoio, Moçambique, {D_SIGN}.'),
    ]
    for p_html in paragrafos:
        story.append(Paragraph(p_html, E['corpo']))
    _assinaturas(story, [
        ('Office Bernardo Ofece Semente', 'MUTUANTE — Office Semente Microcrédito E.I.'),
        (emp.nome, f'MUTUÁRIO: {emp.nome or "—"}'),
    ])
    doc.build(story, canvasmaker=SimpleCanvas)
    buffer.seek(0)
    return buffer

# =============================================================================
# PDF — FICHA DO GESTOR
# =============================================================================
def gerar_ficha_gestor(utilizador, senha_inicial=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=15*mm, bottomMargin=22*mm)
    E = _estilos()
    story = []
    _header(story,
            'Ficha de Utilizador — Gestor de Crédito',
            f'Emitida em {timezone.localdate().strftime("%d/%m/%Y")}')
    story.append(Paragraph('Dados Pessoais', E['subtitulo']))
    story.append(_tabela_dados([
        ('Nome Completo',    utilizador.nome_completo),
        ('NUIT',             utilizador.nuit or '—'),
        ('BI',               utilizador.bi or '—'),
        ('Telefone',         utilizador.telefone or '—'),
        ('Email',            utilizador.email or '—'),
        ('Cargo',            utilizador.cargo or 'Gestor de Crédito'),
        ('Perfil',           utilizador.label_perfil),
        ('Data de Registo',  utilizador.data_registo.strftime('%d/%m/%Y %H:%M')),
    ]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph('Permissões Atribuídas', E['subtitulo']))
    story.append(_tabela_dados([
        ('Aprovar Empréstimos',    '✓' if utilizador.perm_aprovar      else '✗'),
        ('Eliminar Registos',      '✓' if utilizador.perm_eliminar     else '✗'),
        ('Enviar SMS',             '✓' if utilizador.perm_sms          else '✗'),
        ('Ver Relatórios',         '✓' if utilizador.perm_relatorios   else '✗'),
        ('Exportar Dados',         '✓' if utilizador.perm_exportar     else '✗'),
        ('Gestão de Comerciantes', '✓' if utilizador.perm_comerciantes else '✗'),
        ('Limite de Empréstimo',   f'MT {utilizador.limite_emprestimo:,.2f}'
                                   if utilizador.limite_emprestimo else 'Sem limite'),
    ]))
    if senha_inicial:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph('Credenciais de Acesso ao Sistema OSM', E['clausula_titulo']))
        story.append(Paragraph(
            f'<b>{getattr(settings, "OSM_URL", "Contacte o administrador")}</b><br/>'
            f'<b>Username:</b> {utilizador.username}<br/>'
            f'<b>Password:</b> {senha_inicial}', E['corpo']))
        story.append(Paragraph(
            'A OSM nunca pede a sua password por telefone ou email. '
            'Guarde estas credenciais num local seguro e não as partilhe.',
            E['aviso_vermelho']))
    _assinaturas(story, [
        (utilizador.nome_completo, 'Gestor de Crédito'),
        ('Office Bernardo Ofece Semente', 'Directora — Office Semente Microcrédito E.I.'),
    ])
    doc.build(story, canvasmaker=SimpleCanvas)
    buffer.seek(0)
    return buffer

# =============================================================================
# PDF — FICHA DO CLIENTE
# =============================================================================
def gerar_ficha_cliente(utilizador, senha_inicial=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=15*mm, bottomMargin=22*mm)
    E = _estilos()
    story = []
    _header(story,
            'Ficha de Cliente',
            f'Emitida em {timezone.localdate().strftime("%d/%m/%Y")}')
    story.append(Paragraph('Dados de Identificação', E['subtitulo']))
    story.append(_tabela_dados([
        ('Nome Completo',   utilizador.nome_completo),
        ('Username',        utilizador.username),
        ('NUIT',            utilizador.nuit or '—'),
        ('BI',              utilizador.bi or '—'),
        ('Telefone',        utilizador.telefone or '—'),
        ('Email',           utilizador.email or '—'),
        ('Data de Registo', utilizador.data_registo.strftime('%d/%m/%Y %H:%M')),
    ]))
    if senha_inicial:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph('Credenciais de Acesso ao Portal do Cliente', E['clausula_titulo']))
        story.append(Paragraph(
            f'<b>{getattr(settings, "OSM_URL", "Contacte o administrador")}</b><br/>'
            f'<b>Username:</b> {utilizador.username}<br/>'
            f'<b>Password:</b> {senha_inicial}', E['corpo']))
        story.append(Paragraph(
            'A OSM nunca pede a sua password por telefone ou email. '
            'Guarde estas credenciais num local seguro e não as partilhe.',
            E['aviso_vermelho']))
    _assinaturas(story, [
        (utilizador.nome_completo, 'Cliente'),
        ('Office Bernardo Ofece Semente', 'Directora — Office Semente Microcrédito E.I.'),
    ])
    doc.build(story, canvasmaker=SimpleCanvas)
    buffer.seek(0)
    return buffer

# =============================================================================
# PDF — DECLARAÇÃO DE ASSUNÇÃO DE DÍVIDA (PÁGINA ÚNICA, TAMANHO 12, SEM DUPLICAÇÃO)
# =============================================================================
def gerar_declaracao(emp):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=15 * mm, bottomMargin=22 * mm)
    
    # Estilos específicos da declaração (tamanho 12)
    class EstilosDeclaracao:
        corpo = ParagraphStyle(
            'corpo_decl', fontName=FONTE, fontSize=12, leading=16,
            spaceAfter=8, alignment=TA_JUSTIFY)
        local_data = ParagraphStyle(
            'local_decl', fontName=FONTE, fontSize=12,
            alignment=TA_RIGHT, textColor=PRETO, spaceAfter=12)
        assinatura = ParagraphStyle(
            'ass_decl', fontName=FONTE, fontSize=11,
            alignment=TA_CENTER, leading=14, spaceBefore=8)
    E = EstilosDeclaracao

    valor_num = float(emp.valor)
    valor_html = (f'<b><font color="red">'
                  f'{valor_num:,.2f} MZN ({_valor_por_extenso(valor_num)})'
                  f'</font></b>')
    data_venc = _format_date_pt(emp.data_vencimento) if emp.data_vencimento else "—"
    data_venc_html = f'<b><font color="red">{data_venc}</font></b>'
    data_decl = _format_date_pt(timezone.localdate())

    nome          = getattr(emp, 'nome', '—')
    nacionalidade = getattr(emp, 'nacionalidade', 'Moçambicana')
    nome_pai      = getattr(emp, 'nome_pai', '—')
    nome_mae      = getattr(emp, 'nome_mae', '—')
    distrito      = getattr(emp, 'distrito', '—')
    provincia     = getattr(emp, 'provincia', '—')
    bairro        = getattr(emp, 'bairro', '—')
    bi            = getattr(emp, 'bi', '—')
    local_emissao = getattr(emp, 'local_emissao_bi', '—')
    data_emissao  = (emp.data_emissao_bi.strftime("%d/%m/%Y")
                     if getattr(emp, 'data_emissao_bi', None) else "___/___/_____")
    nuit          = getattr(emp, 'nuit', '—')
    telefone      = getattr(emp, 'telefone', '—')
    garantia      = getattr(emp, 'garantia',
                             'Minha viatura da marca Toyota Modelo Ractis 2008, '
                             'com placa de matrícula ALB 605 MC')
    tj = float(getattr(emp, 'taxa_juros', 30))
    tm = float(getattr(emp, 'taxa_multa', 2))

    story = []
    _header(story, 'Declaração de Assunção de Dívida')

    texto = (
        f'<b>{nome}</b>, de nacionalidade <b>{nacionalidade}</b>, '
        f'filho(a) de <b>{nome_pai}</b> e de <b>{nome_mae}</b>, '
        f'do distrito de <b>{distrito}</b>, província de <b>{provincia}</b>, '
        f'residente no bairro <b>{bairro}</b>, '
        f'portador(a) do B.I. n.º <b>{bi}</b>, emitido pelo Arquivo de Identificação '
        f'Civil de <b>{local_emissao}</b> em <b>{data_emissao}</b>, '
        f'NUIT <b>{nuit}</b>, contactável através do n.º <b>{telefone}</b>, '
        f'declaro ser devedor(a) de {valor_html}, '
        f'a favor da <b>Office Semente Microcrédito, E.I.</b>, com sede na EN6 Bairro '
        f'Centro Hípico, Cidade de Chimoio, registada na Conservatória dos Registos das '
        f'Entidades Legais de Chimoio sob o n.º <b>1105038077</b>, NUIT <b>150493129</b>, '
        f'representada por <b>Office Bernardo Ofece Semente</b>, na qualidade de '
        f'<b>Gerente</b>, cuja taxa de juros mensais é de '
        f'<b>{tj:.0f}%</b> e multa diária de '
        f'<b><font color="red">{tm:.0f}%</font></b> por cada dia de atraso.<br/><br/>'
        f'Pagarei a dívida até ao dia {data_venc_html}. '
        f'Em caso de incumprimento, coloco como garantia: <b>{garantia}</b>.'
    )
    story.append(Paragraph(texto, E.corpo))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(f'Chimoio, {data_decl}', E.local_data))
    story.append(Spacer(1, 12 * mm))
    story.append(HRFlowable(width='100%', thickness=0.4, color=colors.HexColor('#cccccc')))
    story.append(Spacer(1, 2 * mm))

    # Assinaturas (duas colunas)
    ass_cols = [
        Paragraph(
            f'{"_" * 38}<br/><b>{nome}</b><br/>'
            f'<font size="9" color="#888888">Declarante (Mutuário)</font>',
            E.assinatura),
        Paragraph(
            f'{"_" * 38}<br/><b>Office Bernardo Ofece Semente</b><br/>'
            f'<font size="9" color="#888888">Gerente — OSM Microcrédito</font>',
            E.assinatura),
    ]
    t_ass = Table([ass_cols], colWidths=[85*mm, 85*mm])
    t_ass.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 4 * mm),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(t_ass)

    doc.build(story, canvasmaker=SimpleCanvas)
    buffer.seek(0)
    return buffer

# =============================================================================
# PDF — RECIBO DE PAGAMENTO (para o cliente)
# =============================================================================
def gerar_recibo(lancamento):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=22*mm)
    E = _estilos()
    story = []
    emp = lancamento.emprestimo
    data_str = lancamento.data_pagamento.strftime('%d/%m/%Y')
    hora_str = lancamento.data_validacao.strftime('%H:%M') if lancamento.data_validacao else ''
    num_recibo = f'REC-{emp.numero_contrato}-{lancamento.pk:04d}'
    _header(story, 'Recibo de Pagamento', f'N.º {num_recibo}')
    t_valor = Table(
        [[Paragraph(
            f'<b><font color="white" size="22">MT {float(lancamento.valor_pago):,.2f}</font></b><br/>'
            f'<font color="white" size="10">VALOR RECEBIDO</font>',
            ParagraphStyle('vr', fontName=FONTE_BOLD, fontSize=22,
                           textColor=colors.white, alignment=TA_CENTER)
        )]],
        colWidths=[170*mm]
    )
    t_valor.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor('#1565c0')),
        ('TOPPADDING',    (0,0), (-1,-1), 10*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10*mm),
        ('ROUNDEDCORNERS', [8]),
    ]))
    story.append(t_valor)
    story.append(Spacer(1, 6*mm))
    tipo_label = 'Pagamento Total' if lancamento.tipo_pagamento == 'total' else 'Pagamento Parcial'
    metodo_label = dict(lancamento.METODO_CHOICES).get(lancamento.metodo, lancamento.metodo)
    story.append(Paragraph('Dados do Pagamento', E['subtitulo']))
    story.append(_tabela_dados([
        ('N.º Recibo',          num_recibo),
        ('Data do Pagamento',   f'{data_str}{" às " + hora_str if hora_str else ""}'),
        ('Contrato',            emp.numero_contrato),
        ('Cliente',             emp.nome),
        ('Telefone',            emp.telefone or '—'),
        ('Método de Pagamento', metodo_label),
        ('Tipo de Pagamento',   tipo_label),
        ('Referência',          lancamento.referencia or '—'),
    ]))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph('Resumo Financeiro', E['subtitulo']))
    capital = emp.valor
    juros   = emp.juros_valor
    multa   = emp.mora_composta if lancamento.tipo_pagamento == 'total' else Decimal('0')
    total_pago = lancamento.valor_pago
    if lancamento.tipo_pagamento == 'parcial':
        saldo_antes = (emp.saldo_restante or emp.total_com_multa) + lancamento.valor_pago
        saldo_apos  = emp.saldo_restante or Decimal('0')
        story.append(_tabela_dados([
            ('Capital Emprestado', f'MT {float(capital):,.2f}'),
            ('Juros ({:.0f}%)'.format(float(emp.taxa_juros)), f'MT {float(juros):,.2f}'),
            ('Total do Contrato',  f'MT {float(emp.total_a_pagar):,.2f}'),
            ('Saldo antes',        f'MT {float(saldo_antes):,.2f}'),
            ('Valor Pago',         f'<b>MT {float(total_pago):,.2f}</b>'),
            ('Saldo Restante',     f'MT {float(saldo_apos):,.2f}'),
        ]))
    else:
        story.append(_tabela_dados([
            ('Capital Emprestado', f'MT {float(capital):,.2f}'),
            ('Juros ({:.0f}%)'.format(float(emp.taxa_juros)), f'MT {float(juros):,.2f}'),
            ('Multa / Mora',       f'MT {float(multa):,.2f}'),
            ('TOTAL PAGO',         f'<b>MT {float(total_pago):,.2f}</b>'),
            ('Estado',             'QUITADO' if emp.pago else 'Parcialmente pago'),
        ]))
    if lancamento.notas:
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph(f'Obs.: {lancamento.notas}', E['aviso']))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph(
        f'Validado por: <b>{lancamento.validado_por.nome_completo if lancamento.validado_por else "—"}</b>',
        ParagraphStyle('vld', fontName=FONTE, fontSize=10, textColor=CINZA_MED, alignment=TA_RIGHT)
    ))
    _assinaturas(story, [
        (emp.nome, 'Cliente / Mutuário'),
        ('Office Semente Microcrédito', 'Recebi o pagamento acima'),
    ])
    doc.build(story, canvasmaker=SimpleCanvas)
    buffer.seek(0)
    return buffer

# =============================================================================
# PDF — FATURA DE RECEBIMENTO (para a empresa) — FUNDO CLARO
# =============================================================================
def gerar_fatura(lancamento):
    """
    Gera uma Nota de Recebimento / Fatura interna para a empresa.
    Layout profissional com fundo claro na caixa de valor.
    """
    from decimal import Decimal
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=22*mm)
    E = _estilos()
    story = []
    emp = lancamento.emprestimo
    data_str   = lancamento.data_pagamento.strftime('%d/%m/%Y')
    data_valid = lancamento.data_validacao.strftime('%d/%m/%Y %H:%M') if lancamento.data_validacao else data_str
    num_fatura = f'FAT-{emp.numero_contrato}-{lancamento.pk:04d}'
    metodo_label = dict(lancamento.METODO_CHOICES).get(lancamento.metodo, lancamento.metodo)
    tipo_label   = 'Pagamento Total' if lancamento.tipo_pagamento == 'total' else 'Pagamento Parcial'

    # Cabeçalho padrão OSM (escuro)
    _header(story, 'NOTA DE RECEBIMENTO', f'Documento Interno · N.º {num_fatura}')

    # ── CAIXA DE VALOR EM DESTAQUE (fundo claro) ───────────────────────────
    # Estilo para o fundo claro
    valor_style = ParagraphStyle(
        'vr_claro',
        fontName=FONTE_BOLD,
        fontSize=22,
        textColor=colors.HexColor("#ffffff"),  # Azul OSM para o valor
        alignment=TA_CENTER
    )
    rotulo_style = ParagraphStyle(
        'vr_rotulo',
        fontName=FONTE,
        fontSize=10,
        textColor=colors.HexColor("#ffffff"),
        alignment=TA_CENTER
    )
    valor_cell = Paragraph(
        f'<b>MT {float(lancamento.valor_pago):,.2f}</b>',
        valor_style
    )
    rotulo_cell = Paragraph('VALOR RECEBIDO', rotulo_style)

    # Tabela com fundo claro e borda suave
    valor_tabela = Table([[valor_cell], [rotulo_cell]], colWidths=[170*mm])
    valor_tabela.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8faff')),  # fundo muito claro
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#ffffff")),       # borda azul
        ('TOPPADDING', (0,0), (-1,0), 8*mm),
        ('BOTTOMPADDING', (0,0), (-1,0), 4*mm),
        ('TOPPADDING', (0,1), (-1,1), 2*mm),
        ('BOTTOMPADDING', (0,1), (-1,1), 8*mm),
        ('ROUNDEDCORNERS', [8]),
    ]))
    story.append(valor_tabela)
    story.append(Spacer(1, 6*mm))

    # ── IDENTIFICAÇÃO DA OPERAÇÃO (2 colunas) ──────────────────────────────
    story.append(Paragraph('Identificação da Operação', E['subtitulo']))
    dados_operacao = [
        ('N.º Fatura',          num_fatura),
        ('Contrato',            emp.numero_contrato),
        ('Data do Recebimento', data_str),
        ('Data de Validação',   data_valid),
        ('Método',              metodo_label),
        ('Tipo',                tipo_label),
        ('Referência',          lancamento.referencia or '—'),
        ('Validado por',        lancamento.validado_por.nome_completo if lancamento.validado_por else '—'),
        ('Registado por',       lancamento.submetido_por.nome_completo if lancamento.submetido_por else '—'),
    ]
    # Dividir em duas colunas
    metade = len(dados_operacao) // 2 + (len(dados_operacao) % 2)
    col1 = dados_operacao[:metade]
    col2 = dados_operacao[metade:]
    tabela_duas_cols = Table([
        [_tabela_dados(col1), _tabela_dados(col2)]
    ], colWidths=[85*mm, 85*mm])
    tabela_duas_cols.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (0,-1), 0),
        ('RIGHTPADDING', (1,0), (1,-1), 0),
    ]))
    story.append(tabela_duas_cols)
    story.append(Spacer(1, 5*mm))

    # ── DADOS DO CLIENTE ────────────────────────────────────────────────────
    story.append(Paragraph('Dados do Cliente / Mutuário', E['subtitulo']))
    story.append(_tabela_dados([
        ('Nome',          emp.nome),
        ('BI',            emp.bi or '—'),
        ('NUIT',          emp.nuit or '—'),
        ('Telefone',      emp.telefone or '—'),
        ('Sector',        emp.sector),
        ('Score',         emp.score),
        ('Bairro',        emp.bairro or '—'),
    ]))
    story.append(Spacer(1, 5*mm))

    # ── DECOMPOSIÇÃO DO RECEBIMENTO (tabela mais elegante) ─────────────────
    story.append(Paragraph('Decomposição do Recebimento', E['subtitulo']))
    capital = emp.valor
    juros   = emp.juros_valor
    multa   = emp.mora_composta

    if lancamento.tipo_pagamento == 'parcial':
        saldo_antes = (emp.saldo_restante or emp.total_com_multa) + lancamento.valor_pago
        saldo_apos  = emp.saldo_restante or Decimal('0')
        dados_fin = [
            ('Capital Emprestado',       f'MT {float(capital):,.2f}'),
            (f'Juros ({float(emp.taxa_juros):.0f}%)', f'MT {float(juros):,.2f}'),
            ('Total do Contrato',        f'MT {float(emp.total_a_pagar):,.2f}'),
            ('Saldo antes do pagamento', f'MT {float(saldo_antes):,.2f}'),
            ('VALOR RECEBIDO (hoje)',    f'<b>MT {float(lancamento.valor_pago):,.2f}</b>'),
            ('Saldo remanescente',       f'MT {float(saldo_apos):,.2f}'),
            ('Total pago até hoje',      f'MT {float(emp.total_pago_parcial):,.2f}'),
        ]
    else:
        dados_fin = [
            ('Capital Emprestado',       f'MT {float(capital):,.2f}'),
            (f'Juros ({float(emp.taxa_juros):.0f}%)', f'MT {float(juros):,.2f}'),
            ('Mora / Multa',             f'MT {float(multa):,.2f}'),
            ('TOTAL RECEBIDO',           f'<b>MT {float(lancamento.valor_pago):,.2f}</b>'),
            ('Estado do Contrato',       'QUITADO ✓' if emp.pago else 'Em aberto'),
        ]

    tabela_fin = _tabela_dados(dados_fin)
    # Destacar a linha do valor recebido com fundo claro
    linha_destaque = len(dados_fin) - 2 if lancamento.tipo_pagamento == 'parcial' else len(dados_fin) - 2
    tabela_fin.setStyle(TableStyle([
        ('BACKGROUND', (0, linha_destaque), (-1, linha_destaque), colors.HexColor('#e8f0fd')),
    ]))
    story.append(tabela_fin)

    # Aviso de atraso
    if emp.dias_atraso > 0:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(
            f'⚠ Pagamento efectuado com {emp.dias_atraso} dia(s) de atraso. '
            f'Multa aplicada: MT {float(multa):,.2f}',
            ParagraphStyle('al', fontName=FONTE, fontSize=10,
                           textColor=VERMELHO, alignment=TA_CENTER)))

    # Notas adicionais
    if lancamento.notas:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(f'Observações: {lancamento.notas}', E['aviso']))

    story.append(Spacer(1, 8*mm))

    # ── ASSINATURAS (para controlo interno) ─────────────────────────────────
    _assinaturas(story, [
        (lancamento.validado_por.nome_completo if lancamento.validado_por else '______________', 'Responsável pela Validação'),
        ('Office Semente Microcrédito', 'Direcção Financeira'),
    ])

    # ── RODAPÉ COM METADADOS ───────────────────────────────────────────────
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        f'Documento gerado automaticamente em {timezone.now().strftime("%d/%m/%Y %H:%M:%S")} · '
        f'Válido como comprovativo de quitação parcial/total.',
        ParagraphStyle('gen', fontName=FONTE, fontSize=8,
                       textColor=CINZA_MED, alignment=TA_CENTER)))

    doc.build(story, canvasmaker=SimpleCanvas)
    buffer.seek(0)
    return buffer

# =============================================================================
# PDF — FATURA DUPLA COM LINHA DE CORTE (cliente + empresa numa folha A4)
# =============================================================================
def gerar_fatura_dupla(lancamento):
    """
    Gera um PDF A4 com dois recibos idênticos:
      — Parte superior (½ da folha): CÓPIA DO CLIENTE
      — Linha de corte tracejada no meio
      — Parte inferior (½ da folha): CÓPIA DA EMPRESA
    """
    from decimal import Decimal
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors

    emp        = lancamento.emprestimo
    W, H       = A4
    MEIO       = H / 2
    MARGEM_H   = 18 * mm
    MARGEM_V   = 10 * mm
    COL_W      = W - 2 * MARGEM_H

    data_str   = lancamento.data_pagamento.strftime('%d/%m/%Y')
    hora_str   = lancamento.data_validacao.strftime('%H:%M') if lancamento.data_validacao else ''
    num_rec    = f'REC-{emp.numero_contrato}-{lancamento.pk:04d}'
    metodo_lbl = dict(lancamento.METODO_CHOICES).get(lancamento.metodo, lancamento.metodo)
    tipo_lbl   = 'Pagamento Total' if lancamento.tipo_pagamento == 'total' else 'Pagamento Parcial'
    validado_nm= lancamento.validado_por.nome_completo if lancamento.validado_por else '—'

    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=A4)

    def desenhar_recibo(top_y, titulo_copia):
        y = top_y - MARGEM_V
        # Cabeçalho azul
        c.setFillColor(colors.HexColor('#1565c0'))
        c.roundRect(MARGEM_H, y - 22*mm, COL_W, 22*mm, 6, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont('Times-Bold', 13)
        c.drawString(MARGEM_H + 8*mm, y - 9*mm, 'OSM Microcrédito')
        c.setFont('Times-Roman', 9)
        c.drawString(MARGEM_H + 8*mm, y - 15*mm, f'Recibo de Pagamento  ·  N.º {num_rec}')
        c.setFillColor(colors.HexColor('#ffc107'))
        c.roundRect(W - MARGEM_H - 36*mm, y - 17*mm, 34*mm, 12*mm, 4, fill=1, stroke=0)
        c.setFillColor(colors.HexColor('#1a2332'))
        c.setFont('Times-Bold', 8)
        c.drawCentredString(W - MARGEM_H - 19*mm, y - 10*mm, titulo_copia)
        y -= 26*mm
        # Valor destacado
        c.setFillColor(colors.HexColor('#e3f0ff'))
        c.roundRect(MARGEM_H, y - 14*mm, COL_W, 14*mm, 4, fill=1, stroke=0)
        c.setFillColor(colors.HexColor('#1565c0'))
        c.setFont('Times-Bold', 15)
        c.drawCentredString(W / 2, y - 9*mm, f'MT {float(lancamento.valor_pago):,.2f}')
        c.setFont('Times-Roman', 7)
        c.drawCentredString(W / 2, y - 13*mm, tipo_lbl.upper())
        y -= 18*mm
        # Tabela
        col2 = MARGEM_H + COL_W / 2 + 4*mm
        linha_h = 6*mm
        dados_esq = [
            ('Cliente',    emp.nome),
            ('Contrato',   emp.numero_contrato),
            ('Data',       f'{data_str}{" " + hora_str if hora_str else ""}'),
            ('Método',     metodo_lbl),
        ]
        dados_dir = [
            ('BI',         emp.bi or '—'),
            ('Telefone',   emp.telefone or '—'),
            ('Validado',   validado_nm[:22]),
            ('Estado',     'QUITADO' if emp.pago else 'Parcial'),
        ]
        c.setFont('Times-Roman', 7.5)
        for i, (k, v) in enumerate(dados_esq):
            yy = y - i * linha_h
            c.setFillColor(colors.HexColor('#f0f4fa'))
            c.rect(MARGEM_H, yy - linha_h + 1, COL_W / 2 - 2*mm, linha_h - 1, fill=1, stroke=0)
            c.setFillColor(colors.HexColor('#5a6478'))
            c.drawString(MARGEM_H + 2*mm, yy - linha_h + 2.5*mm, k)
            c.setFillColor(colors.HexColor('#1a2332'))
            c.setFont('Times-Bold', 7.5)
            c.drawRightString(MARGEM_H + COL_W/2 - 3*mm, yy - linha_h + 2.5*mm, v[:28])
            c.setFont('Times-Roman', 7.5)
        for i, (k, v) in enumerate(dados_dir):
            yy = y - i * linha_h
            c.setFillColor(colors.HexColor('#f0f4fa'))
            c.rect(col2, yy - linha_h + 1, COL_W / 2 - 2*mm, linha_h - 1, fill=1, stroke=0)
            c.setFillColor(colors.HexColor('#5a6478'))
            c.drawString(col2 + 2*mm, yy - linha_h + 2.5*mm, k)
            c.setFillColor(colors.HexColor('#1a2332'))
            c.setFont('Times-Bold', 7.5)
            c.drawRightString(col2 + COL_W/2 - 3*mm, yy - linha_h + 2.5*mm, v[:28])
            c.setFont('Times-Roman', 7.5)
        y -= (len(dados_esq) + 1) * linha_h
        # Assinatura
        c.setStrokeColor(colors.HexColor('#c0cce0'))
        c.setLineWidth(0.5)
        sig_w = (COL_W - 10*mm) / 2
        c.line(MARGEM_H,                sig_w / 2 + MARGEM_H,
               MARGEM_H + sig_w,       sig_w / 2 + MARGEM_H)
        c.line(MARGEM_H + sig_w + 10*mm, sig_w / 2 + MARGEM_H,
               MARGEM_H + 2*sig_w + 10*mm, sig_w / 2 + MARGEM_H)
        c.setFont('Times-Roman', 7)
        c.setFillColor(colors.HexColor('#888'))
        c.drawCentredString(MARGEM_H + sig_w / 2, sig_w / 2 + MARGEM_H - 3*mm, emp.nome[:30])
        c.drawCentredString(MARGEM_H + sig_w + 10*mm + sig_w / 2,
                            sig_w / 2 + MARGEM_H - 3*mm, 'OSM Microcrédito')

    desenhar_recibo(H - 2*mm,  'CÓPIA DO CLIENTE')
    desenhar_recibo(MEIO - 2*mm, 'CÓPIA DA EMPRESA')

    # Linha de corte
    c.saveState()
    c.setDash([4, 3], 0)
    c.setStrokeColor(colors.HexColor('#aaaaaa'))
    c.setLineWidth(0.8)
    c.line(10*mm, MEIO, W - 10*mm, MEIO)
    c.setDash([], 0)
    c.restoreState()
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# =============================================================================
# PDF — RECIBO SIMPLES PARA PAGAMENTOS DE COMERCIANTE (A4)
# =============================================================================
def gerar_recibo_comerciante(comerciante, today=None, registado_por=None):
    if today is None:
        today = timezone.localdate()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=22*mm)
    E = _estilos()
    story = []
    num_rec = f'RCOM-{comerciante.numero_contrato}-{today.strftime("%Y%m%d")}'
    _header(story, 'Recibo de Pagamento — Comerciante', f'N.º {num_rec}')
    t_valor = Table(
        [[Paragraph(
            f'<b><font color="white" size="22">MT {float(comerciante.parcela_atual):,.2f}</font></b><br/>'
            f'<font color="white" size="10">PARCELA RECEBIDA</font>',
            ParagraphStyle('vr', fontName=FONTE_BOLD, fontSize=22,
                           textColor=colors.white, alignment=TA_CENTER)
        )]],
        colWidths=[170*mm]
    )
    t_valor.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#1565c0')),
        ('TOPPADDING', (0,0), (-1,-1), 10*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10*mm),
    ]))
    story.append(t_valor)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph('Dados do Pagamento', E['subtitulo']))
    story.append(_tabela_dados([
        ('N.º Recibo',      num_rec),
        ('Data',            today.strftime('%d/%m/%Y')),
        ('Contrato',        comerciante.numero_contrato),
        ('Comerciante',     comerciante.nome),
        ('Telefone',        comerciante.telefone or '—'),
        ('Modalidade',      comerciante.modalidade_pagamento.capitalize()),
        ('Período',         f'{comerciante.periodos_pagos}/{comerciante.total_periodos}'),
        ('Registado por',   registado_por.nome_completo if registado_por else '—'),
    ]))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph('Resumo Financeiro', E['subtitulo']))
    story.append(_tabela_dados([
        ('Capital',              f'MT {float(comerciante.capital):,.2f}'),
        ('Juros ({:.0f}%)'.format(float(comerciante.taxa_juros)),
                                 f'MT {float(comerciante.juros_valor):,.2f}'),
        ('Custo SMS (serviço)',  'MT 1.20'),
        ('Total a Pagar',        f'MT {float(comerciante.total_a_pagar):,.2f}'),
        ('Parcela',              f'MT {float(comerciante.parcela_atual):,.2f}'),
        ('Total Pago',           f'MT {float(comerciante.total_pago):,.2f}'),
        ('Restante',             f'MT {float(comerciante.total_restante_sem_multa):,.2f}'),
        ('Estado',               comerciante.status.upper()),
    ]))
    if comerciante.periodos_em_atraso > 0:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(
            f'⚠ {comerciante.periodos_em_atraso} período(s) em atraso · '
            f'Multa: MT {float(comerciante.multa_parcela_em_atraso):,.2f}',
            ParagraphStyle('al', fontName=FONTE, fontSize=10,
                           textColor=VERMELHO, alignment=TA_CENTER)))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        'Obrigado pelo seu pagamento!',
        ParagraphStyle('obg', fontName=FONTE_BOLD, fontSize=11,
                       textColor=colors.HexColor('#1565c0'), alignment=TA_CENTER)))
    _assinaturas(story, [
        (comerciante.nome, 'Comerciante / Mutuário'),
        ('Office Semente Microcrédito', 'Recebi o pagamento acima'),
    ])
    doc.build(story, canvasmaker=SimpleCanvas)
    buffer.seek(0)
    return buffer

# =============================================================================
# PDF — RECIBO POS (80mm) PARA COMERCIANTE
# =============================================================================
def gerar_recibo_pos_comerciante(pagamento):
    """Gera recibo no formato POS (80mm térmico) para pagamento de comerciante."""
    com = pagamento.comerciante
    buffer = BytesIO()
    W = 80 * mm
    H = 210 * mm
    MARG = 3 * mm
    c = rl_canvas.Canvas(buffer, pagesize=(W, H))
    y = H - MARG

    # Cabeçalho OSM (simplificado para POS)
    c.setFillColor(colors.HexColor('#0a1628'))
    c.rect(0, y - 15*mm, W, 15*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont('Times-Bold', 10)
    c.drawCentredString(W/2, y - 6*mm, 'OSM Microcrédito')
    c.setFont('Times-Roman', 7)
    c.drawCentredString(W/2, y - 11*mm, 'EN6 Bairro Centro Hípico, Chimoio')
    y -= 18*mm

    c.setStrokeColor(colors.HexColor('#c9a84c'))
    c.setLineWidth(0.8)
    c.line(MARG, y, W - MARG, y)
    y -= 4*mm

    c.setFillColor(colors.black)
    c.setFont('Times-Bold', 9)
    c.drawCentredString(W/2, y, 'RECIBO DE PAGAMENTO (POS)')
    y -= 5*mm
    c.setFont('Times-Roman', 7)
    c.drawCentredString(W/2, y, f'N.º {pagamento.id}')
    y -= 6*mm

    def linha(label, valor, bold=False):
        nonlocal y
        c.setFont('Times-Bold' if bold else 'Times-Roman', 7)
        c.setFillColor(colors.black)
        c.drawString(MARG, y, f'{label}:')
        c.drawRightString(W - MARG, y, str(valor)[:32])
        y -= 4.5*mm

    linha('Comerciante', com.nome[:28])
    linha('Contrato', com.numero_contrato)
    linha('Data', pagamento.data.strftime('%d/%m/%Y'))
    linha('Valor', f'MT {pagamento.valor_pago:,.2f}', bold=True)
    linha('Custo SMS', f'MT {pagamento.custo_sms:,.2f}')
    linha('Total pago', f'MT {com.total_pago:,.2f}')
    linha('Período', f'{com.periodos_pagos}/{com.total_periodos}')

    y -= 4*mm
    c.setStrokeColor(colors.HexColor('#c9a84c'))
    c.line(MARG, y, W - MARG, y)
    y -= 6*mm
    c.setFont('Times-Roman', 6)
    c.setFillColor(colors.HexColor('#555'))
    c.drawCentredString(W/2, y, 'Obrigado pela confiança!')
    y -= 4*mm
    c.drawCentredString(W/2, y, f'Emissão: {timezone.now().strftime("%d/%m/%Y %H:%M")}')
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# =============================================================================
# PDF — FATURA ESTILO TURBOHOST (A4, profissional, com PAID stamp)
# =============================================================================
def gerar_fatura_turbohost(lancamento):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=22*mm)
    story = []
    emp = lancamento.emprestimo
    data_str = lancamento.data_pagamento.strftime('%d/%m/%Y')
    data_valid = lancamento.data_validacao.strftime('%d/%m/%Y %H:%M') if lancamento.data_validacao else data_str
    num_fat = f'FAT-{emp.numero_contrato}-{lancamento.pk:04d}'
    metodo_lbl = dict(lancamento.METODO_CHOICES).get(lancamento.metodo, lancamento.metodo)
    tipo_lbl = 'Pagamento Total' if lancamento.tipo_pagamento == 'total' else 'Pagamento Parcial'

    logo_p = _logo_path()
    if logo_p:
        logo_cell = Image(logo_p, width=28*mm, height=28*mm)
    else:
        logo_cell = Paragraph('<b>OSM</b>', ParagraphStyle('lg', fontName=FONTE_BOLD,
                              fontSize=22, textColor=colors.HexColor('#1565c0'), alignment=TA_CENTER))

    empresa_left = Paragraph(
        f'<b>Office Semente Microcrédito, E.I.</b><br/>'
        f'<font size="9" color="#555">EN6 Bairro Centro Hípico<br/>'
        f'Chimoio, Manica, Moçambique<br/>'
        f'NUIT: 150493129<br/>'
        f'Tel: {getattr(settings, "OSM_TEL", "+258 84 203 1215")}</font>',
        ParagraphStyle('el', fontName=FONTE, fontSize=10, leading=14, alignment=TA_CENTER))

    fatura_right = Paragraph(
        f'<b><font size="20" color="#1565c0">FATURA</font></b><br/>'
        f'<font size="9" color="#555">N.º {num_fat}<br/>'
        f'Data: {data_str}<br/>'
        f'Válido: {data_valid}</font>',
        ParagraphStyle('fr', fontName=FONTE, fontSize=10, leading=14, alignment=TA_RIGHT))

    t_head = Table([[logo_cell, empresa_left, fatura_right]],
                   colWidths=[35*mm, 80*mm, 65*mm])
    t_head.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4*mm),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, colors.HexColor('#1565c0')),
    ]))
    story.append(t_head)
    story.append(Spacer(1, 6*mm))

    # Cliente
    t_partes = Table([
        [Paragraph('<b>Emitido por:</b>', ParagraphStyle('ep', fontName=FONTE_BOLD, fontSize=9)),
         Paragraph('<b>Cliente / Mutuário:</b>', ParagraphStyle('cp', fontName=FONTE_BOLD, fontSize=9))],
        [Paragraph(
            f'Office Semente Microcrédito, E.I.<br/>'
            f'<font size="9" color="#555">NUIT: 150493129<br/>'
            f'FNB Conta: 4551596810001</font>',
            ParagraphStyle('ep2', fontName=FONTE, fontSize=9, leading=13)),
         Paragraph(
            f'{emp.nome}<br/>'
            f'<font size="9" color="#555">BI: {emp.bi or "—"} · NUIT: {emp.nuit or "—"}<br/>'
            f'Tel: {emp.telefone or "—"}<br/>'
            f'Bairro: {emp.bairro or "—"}, Chimoio</font>',
            ParagraphStyle('cp2', fontName=FONTE, fontSize=9, leading=13))],
    ], colWidths=[90*mm, 90*mm])
    t_partes.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f4fa')),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#fafbfc')),
        ('TOPPADDING', (0, 0), (-1, -1), 3*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3*mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 4*mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4*mm),
        ('LINEBELOW', (0, 1), (-1, 1), 0.5, colors.HexColor('#ddd')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#ddd')),
    ]))
    story.append(t_partes)
    story.append(Spacer(1, 6*mm))

    # Tabela de itens
    cab = [
        Paragraph('<b>Descrição</b>', ParagraphStyle('tc', fontName=FONTE_BOLD, fontSize=10, alignment=TA_CENTER)),
        Paragraph('<b>Qtd.</b>', ParagraphStyle('tq', fontName=FONTE_BOLD, fontSize=10, alignment=TA_CENTER)),
        Paragraph('<b>Subtotal</b>', ParagraphStyle('ts', fontName=FONTE_BOLD, fontSize=10, alignment=TA_CENTER)),
    ]
    PS_ITEM = ParagraphStyle('ti', fontName=FONTE, fontSize=10)
    PS_VAL = ParagraphStyle('tv', fontName=FONTE, fontSize=10, alignment=TA_RIGHT)
    PS_QTD = ParagraphStyle('tq2', fontName=FONTE, fontSize=10, alignment=TA_CENTER)
    linhas = [cab]
    if lancamento.tipo_pagamento == 'parcial':
        saldo_antes = (emp.saldo_restante or emp.total_com_multa)
        if emp.saldo_restante is not None:
            saldo_antes = emp.saldo_restante + lancamento.valor_pago
        linhas.append([
            Paragraph(f'Contrato {emp.numero_contrato} — Pagamento Parcial', PS_ITEM),
            Paragraph('1', PS_QTD),
            Paragraph(f'MT {float(lancamento.valor_pago):,.2f}', PS_VAL),
        ])
        linhas.append([
            Paragraph(f'  <i>(Saldo antes: MT {float(saldo_antes):,.2f})</i>', PS_ITEM),
            Paragraph('', PS_QTD),
            Paragraph('', PS_VAL),
        ])
    else:
        linhas.append([
            Paragraph(f'Capital Emprestado — Contrato {emp.numero_contrato}', PS_ITEM),
            Paragraph('1', PS_QTD),
            Paragraph(f'MT {float(emp.valor):,.2f}', PS_VAL),
        ])
        linhas.append([
            Paragraph(f'Juros ({float(emp.taxa_juros):.0f}% — 1 mês)', PS_ITEM),
            Paragraph('1', PS_QTD),
            Paragraph(f'MT {float(emp.juros_valor):,.2f}', PS_VAL),
        ])
        if emp.mora_composta > 0:
            linhas.append([
                Paragraph(f'Mora / Multa ({emp.dias_atraso} dias de atraso)', PS_ITEM),
                Paragraph('1', PS_QTD),
                Paragraph(f'MT {float(emp.mora_composta):,.2f}', PS_VAL),
            ])
        linhas.append([
            Paragraph('Custo de SMS (notificação ao cliente)', PS_ITEM),
            Paragraph('1', PS_QTD),
            Paragraph('MT 1.20', PS_VAL),
        ])

    t_itens = Table(linhas, colWidths=[115*mm, 20*mm, 45*mm])
    ts_itens = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565c0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('TOPPADDING', (0, 0), (-1, -1), 3*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3*mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 3*mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3*mm),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#e0e0e0')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#ccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8faff')]),
    ]
    t_itens.setStyle(TableStyle(ts_itens))
    story.append(t_itens)
    story.append(Spacer(1, 4*mm))

    # Total
    t_total = Table([
        [Paragraph('Subtotal', ParagraphStyle('st', fontName=FONTE, fontSize=10)),
         Paragraph(f'MT {float(lancamento.valor_pago):,.2f}',
                   ParagraphStyle('stv', fontName=FONTE, fontSize=10, alignment=TA_RIGHT))],
        [Paragraph('<b>TOTAL A PAGAR</b>', ParagraphStyle('tp', fontName=FONTE_BOLD, fontSize=12)),
         Paragraph(f'<b>MT {float(lancamento.valor_pago):,.2f}</b>',
                   ParagraphStyle('tpv', fontName=FONTE_BOLD, fontSize=12, alignment=TA_RIGHT))],
    ], colWidths=[120*mm, 60*mm])
    t_total.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 2.5*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5*mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 4*mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4*mm),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#e8f0fd')),
        ('LINEABOVE', (0, 1), (-1, 1), 1.5, colors.HexColor('#1565c0')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#ccc')),
    ]))
    story.append(t_total)
    story.append(Spacer(1, 8*mm))

    # Stamp PAGO
    if emp.pago:
        stamp = Table([[Paragraph(
            '<b><font color="#2e7d32" size="36">PAGO</font></b><br/>'
            f'<font size="9" color="#555">{metodo_lbl} · {data_str}</font>',
            ParagraphStyle('paid', fontName=FONTE_BOLD, fontSize=36,
                           textColor=colors.HexColor('#2e7d32'), alignment=TA_CENTER)
        )]], colWidths=[180*mm])
        stamp.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 3, colors.HexColor('#2e7d32')),
            ('TOPPADDING', (0, 0), (-1, -1), 5*mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5*mm),
        ]))
        story.append(stamp)
        story.append(Spacer(1, 6*mm))

    # Notas
    notas_items = []
    if lancamento.referencia:
        notas_items.append(f'Referência de pagamento: <b>{lancamento.referencia}</b>')
    notas_items.append(f'Validado por: <b>{lancamento.validado_por.nome_completo if lancamento.validado_por else "—"}</b>')
    notas_items.append(f'Gerado automaticamente em {timezone.now().strftime("%d/%m/%Y %H:%M")}')
    if lancamento.notas:
        notas_items.append(f'Notas: {lancamento.notas}')

    for nota in notas_items:
        story.append(Paragraph(nota, ParagraphStyle('nota', fontName=FONTE, fontSize=9,
                                                     textColor=colors.HexColor('#666'), spaceAfter=3)))
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(
        '<b>Obrigado pelo seu pagamento!</b>',
        ParagraphStyle('obg', fontName=FONTE_BOLD, fontSize=11,
                       textColor=colors.HexColor('#1565c0'), alignment=TA_CENTER)))

    doc.build(story, canvasmaker=SimpleCanvas)
    buffer.seek(0)
    return buffer


# =============================================================================
# PDF — RECIBO POS (80mm) PARA EMPRÉSTIMO (gerar_recibo_pos)
# =============================================================================
def gerar_recibo_pos(lancamento):
    """
    Gera recibo estilo impressora POS/thermal (80mm) para pagamento de empréstimo.
    Retorna BytesIO.
    """
    from decimal import Decimal
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.lib import colors

    emp = lancamento.emprestimo
    data_str = lancamento.data_pagamento.strftime('%d/%m/%Y')
    hora_str = lancamento.data_validacao.strftime('%H:%M') if lancamento.data_validacao else ''
    num_rec = f'REC-{emp.numero_contrato}-{lancamento.pk:04d}'
    metodo_lbl = dict(lancamento.METODO_CHOICES).get(lancamento.metodo, lancamento.metodo)
    tipo_lbl = 'Pagamento Total' if lancamento.tipo_pagamento == 'total' else 'Parcial'
    validado_nm = lancamento.validado_por.nome_completo if lancamento.validado_por else '—'

    W = 80 * mm
    H = 210 * mm
    MARG = 3 * mm

    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(W, H))
    y = H - MARG

    # Cabeçalho OSM escuro
    c.setFillColor(colors.HexColor('#0a1628'))
    c.rect(0, y - 15*mm, W, 15*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont('Times-Bold', 10)
    c.drawCentredString(W/2, y - 6*mm, 'OSM Microcrédito')
    c.setFont('Times-Roman', 7)
    c.drawCentredString(W/2, y - 11*mm, 'EN6 Bairro Centro Hípico, Chimoio')
    y -= 18*mm

    c.setStrokeColor(colors.HexColor('#c9a84c'))
    c.setLineWidth(0.8)
    c.line(MARG, y, W - MARG, y)
    y -= 4*mm

    c.setFillColor(colors.black)
    c.setFont('Times-Bold', 9)
    c.drawCentredString(W/2, y, 'RECIBO DE PAGAMENTO (POS)')
    y -= 5*mm
    c.setFont('Times-Roman', 7)
    c.drawCentredString(W/2, y, f'N.º {num_rec}')
    y -= 6*mm

    def linha(label, valor, bold=False):
        nonlocal y
        c.setFont('Times-Bold' if bold else 'Times-Roman', 7)
        c.setFillColor(colors.black)
        c.drawString(MARG, y, f'{label}:')
        c.drawRightString(W - MARG, y, str(valor)[:32])
        y -= 4.5*mm

    linha('Cliente', emp.nome[:28])
    linha('Contrato', emp.numero_contrato)
    linha('Data', f'{data_str}{" " + hora_str if hora_str else ""}')
    linha('Método', metodo_lbl)
    linha('Tipo', tipo_lbl)
    if lancamento.referencia:
        linha('Ref.', lancamento.referencia[:28])

    # Itens (resumo)
    y -= 2*mm
    c.setStrokeColor(colors.HexColor('#ccc'))
    c.line(MARG, y, W - MARG, y)
    y -= 4*mm
    c.setFont('Times-Bold', 7)
    c.drawString(MARG, y, 'Descrição')
    c.drawRightString(W - MARG, y, 'Valor')
    y -= 4.5*mm

    def item(desc, valor):
        nonlocal y
        c.setFont('Times-Roman', 7)
        c.drawString(MARG, y, desc)
        c.drawRightString(W - MARG, y, f'MT {float(valor):,.2f}')
        y -= 4.5*mm

    if lancamento.tipo_pagamento == 'parcial':
        saldo_antes = (emp.saldo_restante or emp.total_com_multa)
        if emp.saldo_restante is not None:
            saldo_antes = emp.saldo_restante + lancamento.valor_pago
        item('Saldo antes', saldo_antes)
        item('Valor pago', lancamento.valor_pago)
        saldo_apos = max(Decimal('0'), saldo_antes - lancamento.valor_pago)
        item('Saldo restante', saldo_apos)
    else:
        item('Capital', emp.valor)
        item(f'Juros ({float(emp.taxa_juros):.0f}%)', emp.juros_valor)
        if emp.mora_composta > 0:
            item('Mora', emp.mora_composta)
        item('SMS', Decimal('1.20'))

    y -= 1*mm
    c.setStrokeColor(colors.HexColor('#333'))
    c.line(MARG, y, W - MARG, y)
    y -= 5*mm

    c.setFillColor(colors.HexColor('#1565c0'))
    c.rect(MARG, y - 6*mm, W - 2*MARG, 7*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont('Times-Bold', 11)
    c.drawString(MARG + 2*mm, y - 4*mm, 'TOTAL PAGO')
    c.drawRightString(W - MARG - 2*mm, y - 4*mm, f'MT {float(lancamento.valor_pago):,.2f}')
    y -= 9*mm

    estado_cor = colors.HexColor('#2e7d32') if emp.pago else colors.HexColor('#e65100')
    estado_txt = 'QUITADO ✓' if emp.pago else 'PARCIALMENTE PAGO'
    c.setFillColor(estado_cor)
    c.setFont('Times-Bold', 8)
    c.drawCentredString(W/2, y, estado_txt)
    y -= 6*mm

    c.setStrokeColor(colors.HexColor('#ccc'))
    c.line(MARG, y, W - MARG, y)
    y -= 4*mm
    c.setFont('Times-Roman', 6)
    c.setFillColor(colors.HexColor('#555'))
    c.drawCentredString(W/2, y, f'Validado: {validado_nm[:30]}')
    y -= 3.5*mm
    c.drawCentredString(W/2, y, f'Gerado: {timezone.now().strftime("%d/%m/%Y %H:%M")}')
    y -= 3.5*mm
    c.setFont('Times-Bold', 7)
    c.drawCentredString(W/2, y, 'Obrigado pelo seu pagamento!')

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer