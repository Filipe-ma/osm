"""
Comando de gestão: enviar alertas SMS automáticos
Uso: python manage.py enviar_alertas_sms
Configurar no cron (diário às 8h):
  0 8 * * * /caminho/para/venv/bin/python /caminho/manage.py enviar_alertas_sms
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from osm.models import ConfiguracaoBancaria, Emprestimo, LogSMS
from osm.views import enviar_sms_bulksms


class Command(BaseCommand):
    help = 'Envia alertas SMS automáticos: pré-vencimento e cobrança de atraso'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Simular sem enviar')
        parser.add_argument('--force', action='store_true', help='Forçar mesmo se auto desactivado')

    def handle(self, *args, **options):
        cfg     = ConfiguracaoBancaria.obter()
        dry_run = options['dry_run']
        force   = options['force']
        hoje    = date.today()

        if not cfg.sms_cobranca_auto and not force:
            self.stdout.write(self.style.WARNING(
                'SMS automático desactivado. Use --force para forçar.'
            ))
            return

        if not cfg.bulksms_api_token and not dry_run:
            self.stdout.write(self.style.ERROR('BulkSMS API token não configurado!'))
            return

        enviados = 0
        erros    = 0

        # ── 1. Alertas pré-vencimento ──────────────────────────────
        dias_alerta = cfg.sms_alerta_dias or 3
        data_alerta = hoje + timedelta(days=dias_alerta)
        proximos = Emprestimo.objects.filter(
            status='ativo',
            data_vencimento=data_alerta,
            pago=False,
            telefone__isnull=False,
        ).exclude(telefone='')

        self.stdout.write(f'📅 Alertas pré-vencimento ({dias_alerta}d): {proximos.count()}')

        for emp in proximos:
            msg = (f'OSM Microcredito: {emp.nome}, a sua parcela '
                   f'{emp.numero_contrato} ({emp.valor_fmt}) vence em '
                   f'{dias_alerta} dias ({data_alerta.strftime("%d/%m/%Y")}). '
                   f'Deposite em {cfg.banco} Conta {cfg.conta}.')
            if not dry_run:
                ok, det = enviar_sms_bulksms(emp.telefone, msg, cfg)
                LogSMS.objects.create(
                    nome=emp.nome, telefone=emp.telefone, mensagem=msg,
                    status='alerta' if ok else f'alerta-erro:{det[:40]}',
                    numero_contrato=emp.numero_contrato
                )
                if ok:
                    enviados += 1
                    self.stdout.write(self.style.SUCCESS(f'  ✅ {emp.nome} — {emp.telefone}'))
                else:
                    erros += 1
                    self.stdout.write(self.style.ERROR(f'  ❌ {emp.nome} — {det}'))
            else:
                self.stdout.write(f'  [DRY] {emp.nome} ({emp.telefone}): {msg[:80]}…')

        # ── 2. Cobrança de atraso ─────────────────────────────────
        em_atraso = Emprestimo.objects.filter(
            status__in=['vencido', 'incumprimento'],
            pago=False,
        ).exclude(telefone='')

        self.stdout.write(f'\n⚠ Cobrança em atraso: {em_atraso.count()}')

        for emp in em_atraso:
            msg = (f'OSM Microcredito URGENTE: {emp.nome}, contrato '
                   f'{emp.numero_contrato} em atraso {emp.dias_atraso}d. '
                   f'Regularize ja: {cfg.banco} Conta {cfg.conta} NIB {cfg.nib}. '
                   f'Evite accoes legais.')
            if not dry_run:
                ok, det = enviar_sms_bulksms(emp.telefone, msg, cfg)
                LogSMS.objects.create(
                    nome=emp.nome, telefone=emp.telefone, mensagem=msg,
                    status='auto-cobranca' if ok else f'auto-erro:{det[:40]}',
                    numero_contrato=emp.numero_contrato
                )
                if ok:
                    enviados += 1
                    self.stdout.write(self.style.SUCCESS(f'  ✅ {emp.nome} ({emp.dias_atraso}d)'))
                else:
                    erros += 1
                    self.stdout.write(self.style.ERROR(f'  ❌ {emp.nome} — {det}'))
            else:
                self.stdout.write(f'  [DRY] {emp.nome} ({emp.dias_atraso}d atraso): {msg[:80]}…')

        # ── Resumo ────────────────────────────────────────────────
        self.stdout.write('\n' + '─' * 50)
        if dry_run:
            self.stdout.write(self.style.WARNING('Modo DRY RUN — nenhum SMS enviado.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Concluído: {enviados} SMS enviados, {erros} erros.'
            ))
