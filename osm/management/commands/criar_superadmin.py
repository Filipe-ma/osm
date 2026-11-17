"""
Comando inicial OSM v2
Uso: python manage.py criar_superadmin
"""
from django.core.management.base import BaseCommand
from osm.models import Utilizador, ConfiguracaoBancaria


class Command(BaseCommand):
    help = 'Cria a configuração bancária inicial. O superadmin deve ser criado com createsuperuser.'

    def handle(self, *args, **options):
        # Configuração bancária
        b, created = ConfiguracaoBancaria.objects.get_or_create(pk=1)
        if created:
            b.banco   = 'FNB — First National Bank'
            b.titular = 'Office Semente Microcrédito EI.'
            b.conta   = '4551596810001'
            b.nib     = '0014 0000 45515968101 86'
            b.save()
            self.stdout.write(self.style.SUCCESS('✓ Configuração bancária criada.'))
        else:
            self.stdout.write(self.style.WARNING('Config bancária já existe.'))

        self.stdout.write(self.style.SUCCESS(
            '\n✅ OSM Microcrédito v2 inicializado!\n\n'
            '   Próximo passo:\n'
            '   python manage.py createsuperuser\n\n'
            '   Depois aceda: http://127.0.0.1:8000/\n'
        ))
