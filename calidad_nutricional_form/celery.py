# celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# Establecer el módulo de configuración de Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "calidad_nutricional_form.settings")

app = Celery("calidad_nutricional_form")

# Leer configuración de Celery desde settings.py con el prefijo CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks.py en las aplicaciones instaladas
app.autodiscover_tasks()
