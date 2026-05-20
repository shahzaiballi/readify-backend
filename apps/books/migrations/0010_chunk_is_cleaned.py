from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('books', '0009_readingschedule_current_day'),
    ]

    operations = [
        migrations.AddField(
            model_name='chunk',
            name='is_cleaned',
            field=models.BooleanField(
                default=False,
                help_text='True once AI has removed OCR artifacts and PDF extraction noise from this chunk',
            ),
        ),
    ]
