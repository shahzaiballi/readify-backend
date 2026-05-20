from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reading', '0002_add_pages_per_day'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='readingplan',
            name='daily_minutes',
        ),
    ]
