"""
apps/books/migrations/0002_book_pdf_and_upload.py

Adds:
- Book.pdf_file          — stores the uploaded PDF
- Book.cover_image       — uploaded cover image (alternative to URL)
- Book.source            — 'admin' or 'user_upload'
- Book.processing_status — tracks AI chunking progress
- Book.processing_error  — error message if processing failed
- UserUploadedBook       — new model for user-uploaded PDFs
"""

import apps.books.models
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('books', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Add new fields to Book ────────────────────────────────────────────
        migrations.AddField(
            model_name='book',
            name='pdf_file',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.books.models.book_pdf_upload_path,
                help_text='Upload the PDF of this book. Chapters and chunks will be auto-generated.',
            ),
        ),
        migrations.AddField(
            model_name='book',
            name='cover_image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=apps.books.models.book_cover_upload_path,
                help_text='Upload a cover image (optional if cover_image_url is set)',
            ),
        ),
        migrations.AddField(
            model_name='book',
            name='source',
            field=models.CharField(
                choices=[('admin', 'Admin Curated'), ('user_upload', 'User Upload')],
                default='admin',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='book',
            name='processing_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('processing', 'Processing'),
                    ('completed', 'Completed'),
                    ('failed', 'Failed'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='book',
            name='processing_error',
            field=models.TextField(blank=True, help_text='Error message if processing failed'),
        ),

        # ── Create UserUploadedBook model ─────────────────────────────────────
        migrations.CreateModel(
            name='UserUploadedBook',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('author', models.CharField(blank=True, max_length=255)),
                ('pdf_file', models.FileField(upload_to=apps.books.models.user_book_pdf_upload_path)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending Processing'),
                        ('processing', 'Processing'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('error_message', models.TextField(blank=True)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('uploaded_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='uploaded_books',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('book', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='user_upload_source',
                    to='books.book',
                )),
            ],
        ),
    ]