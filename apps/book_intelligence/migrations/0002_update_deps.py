"""
Migration: ensure book_intelligence depends on books/0005 (reading plan fields).
This is a no-op data migration — just establishes the correct dependency chain.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('book_intelligence', '0001_initial'),
        ('books', '0005_reading_plan_fields'),
    ]

    operations = []
