# apps/community/migrations/0001_initial.py

import uuid
import secrets
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('books', '0004_alter_book_pdf_file_alter_useruploadedbook_pdf_file'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Community',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('description', models.TextField(blank=True)),
                ('community_type', models.CharField(
                    choices=[('general', 'General'), ('book', 'Book Group')],
                    default='general',
                    max_length=10,
                )),
                ('privacy', models.CharField(
                    choices=[('public', 'Public'), ('private', 'Private')],
                    default='public',
                    max_length=10,
                )),
                ('cover_image', models.ImageField(blank=True, null=True, upload_to='communities/covers/')),
                ('cover_emoji', models.CharField(blank=True, default='📚', max_length=10)),
                ('invite_token', models.CharField(blank=True, max_length=32, unique=True)),
                ('member_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='created_communities',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('book', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='communities',
                    to='books.book',
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name_plural': 'Communities',
            },
        ),
        migrations.CreateModel(
            name='CommunityMember',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('role', models.CharField(
                    choices=[('admin', 'Admin'), ('member', 'Member')],
                    default='member',
                    max_length=10,
                )),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('community', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='members',
                    to='community.community',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='community_memberships',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['joined_at'],
                'unique_together': {('community', 'user')},
            },
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('content', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('edited_at', models.DateTimeField(blank=True, null=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('community', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='messages',
                    to='community.community',
                )),
                ('sender', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='community_messages',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('reply_to', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='replies',
                    to='community.message',
                )),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='MessageReaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('emoji', models.CharField(max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('message', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reactions',
                    to='community.message',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='message_reactions',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'unique_together': {('message', 'user', 'emoji')},
            },
        ),
    ]