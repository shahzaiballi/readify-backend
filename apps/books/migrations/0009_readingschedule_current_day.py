from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('books', '0008_fix_readingschedule_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='readingschedule',
            name='current_day',
            field=models.PositiveIntegerField(
                default=1,
                help_text='Which reading day the user is currently on (advances after each session)',
            ),
        ),
    ]
