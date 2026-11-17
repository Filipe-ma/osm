from django.apps import AppConfig


class OsmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'osm'
    verbose_name = 'OSM Microcrédito'

    def ready(self):
        import osm.signals  # noq