# Generated by Django 5.1.1 on 2025-01-30 14:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('initial_form', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='unmatchedsearch',
            name='has_results',
            field=models.BooleanField(default=False),
            preserve_default=False,
        ),
    ]
