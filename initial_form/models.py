from django.db import models

class UnmatchedSearch(models.Model):
    term = models.CharField(max_length=255, verbose_name="Término de búsqueda")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    has_results = models.BooleanField()

    def __str__(self):
        return self.term

    class Meta:
        verbose_name = "Búsqueda sin coincidencia"
        verbose_name_plural = "Búsquedas sin coincidencia"
