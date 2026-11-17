# osm/signals.py
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth import get_user_model
import os

User = get_user_model()


@receiver(post_migrate)
def create_default_superuser(sender, **kwargs):
    if sender.name != 'osm':
        return
    username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
    email    = os.environ.get('DJANGO_SUPERUSER_EMAIL',    'admin@osm.co.mz')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '123mudar')

    if not User.objects.filter(username=username).exists():
        user = User.objects.create_superuser(username, email, password)
        user.perfil            = 'superadmin'
        user.deve_trocar_senha = False
        user.activo            = True
        user.first_name        = 'Super'
        user.last_name         = 'Admin'
        user.save()
        print(f"✓ Superusuário '{username}' criado — perfil=superadmin.")
    else:
        user = User.objects.filter(username=username).first()
        changed = False
        if user and user.perfil != 'superadmin':
            user.perfil = 'superadmin'
            changed = True
        if user and not user.activo:
            user.activo = True
            changed = True
        if changed:
            user.save()
            print(f"✓ Superusuário '{username}' corrigido — perfil=superadmin.")

    try:
        from osm.models import LicencaSistema
        if not LicencaSistema.objects.exists():
            lic = LicencaSistema.criar_nova()
            print(f"✓ Licença do sistema criada — código {lic.codigo} · válida até {lic.data_expiracao:%d/%m/%Y}")
    except Exception:
        pass