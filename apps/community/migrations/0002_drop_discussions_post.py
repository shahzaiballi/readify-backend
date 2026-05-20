from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('community', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS discussions_post CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
