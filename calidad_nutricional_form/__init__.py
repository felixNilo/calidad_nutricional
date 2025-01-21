from __future__ import absolute_import, unicode_literals

# Esto asegura que celery se cargue al iniciar Django
from .celery import app as celery_app

__all__ = ("celery_app",)
