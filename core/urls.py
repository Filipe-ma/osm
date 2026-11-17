"""
OSM Microcrédito — URLs raiz
Localização: core/urls.py
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('',       include('osm.urls')),
    path('sw.js', RedirectView.as_view(url='/static/sw.js', permanent=True)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
