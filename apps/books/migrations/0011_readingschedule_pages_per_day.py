from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('books', '0010_chunk_is_cleaned'),
    ]

    operations = [
        migrations.AddField(
            model_name='readingschedule',
            name='pages_per_day',
            field=models.PositiveIntegerField(
                default=10,
                help_text='Chunks per reading session — stored at creation so both Today and Complete views use the same value',
            ),
        ),
    ]
