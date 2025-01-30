from django.contrib import admin
from .models import UnmatchedSearch

@admin.register(UnmatchedSearch)
class UnmatchedSearch(admin.ModelAdmin):
    list_display = ['term', 'has_results', 'created_at']