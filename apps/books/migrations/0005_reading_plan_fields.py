"""
Migration: Add reading plan fields to Book, UserUploadedBook, Chunk.
Create ReadingSchedule model.
"""

import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('books', '0004_alter_book_pdf_file_alter_useruploadedbook_pdf_file'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Book: reading_mode ────────────────────────────────────────────────
        migrations.AddField(
            model_name='book',
            name='reading_mode',
            field=models.CharField(
                choices=[('skim', 'Skim'), ('concept', 'Concept'),
                         ('deep', 'Deep'), ('exam', 'Exam')],
                default='deep',
                max_length=10,
            ),
        ),
        # ── Book: daily_minutes ───────────────────────────────────────────────
        migrations.AddField(
            model_name='book',
            name='daily_minutes',
            field=models.PositiveIntegerField(default=30),
        ),
        # ── Book: chapter_source ──────────────────────────────────────────────
        migrations.AddField(
            model_name='book',
            name='chapter_source',
            field=models.CharField(
                choices=[('bookmarks', 'PDF Bookmarks'), ('text_toc', 'Text TOC'),
                         ('ai_generated', 'AI Generated'), ('manual', 'Manual Split')],
                default='manual',
                max_length=20,
            ),
        ),
        # ── UserUploadedBook: reading_mode ────────────────────────────────────
        migrations.AddField(
            model_name='useruploadedbook',
            name='reading_mode',
            field=models.CharField(
                choices=[('skim', 'Skim'), ('concept', 'Concept'),
                         ('deep', 'Deep'), ('exam', 'Exam')],
                default='deep',
                max_length=10,
            ),
        ),
        # ── UserUploadedBook: daily_minutes ───────────────────────────────────
        migrations.AddField(
            model_name='useruploadedbook',
            name='daily_minutes',
            field=models.PositiveIntegerField(default=30),
        ),
        # ── UserUploadedBook: toc_raw ─────────────────────────────────────────
        migrations.AddField(
            model_name='useruploadedbook',
            name='toc_raw',
            field=models.JSONField(blank=True, default=list),
        ),
        # ── UserUploadedBook: total_pages ─────────────────────────────────────
        migrations.AddField(
            model_name='useruploadedbook',
            name='total_pages',
            field=models.PositiveIntegerField(default=0),
        ),
        # ── UserUploadedBook: processing_stage ───────────────────────────────
        migrations.AddField(
            model_name='useruploadedbook',
            name='processing_stage',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        # ── Chunk: day_number ─────────────────────────────────────────────────
        migrations.AddField(
            model_name='chunk',
            name='day_number',
            field=models.PositiveIntegerField(default=1),
        ),
        # ── Chunk: words_count ────────────────────────────────────────────────
        migrations.AddField(
            model_name='chunk',
            name='words_count',
            field=models.PositiveIntegerField(default=0),
        ),
        # ── New model: ReadingSchedule ────────────────────────────────────────
        migrations.CreateModel(
            name='ReadingSchedule',
            fields=[
                ('id', models.UUIDField(
                    primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                )),
                ('schedule_data', models.JSONField(default=list)),
                ('total_days', models.PositiveIntegerField(default=0)),
                ('start_date', models.DateField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reading_schedules',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('book', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reading_schedules',
                    to='books.book',
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('user', 'book')},
            },
        ),
    ]
