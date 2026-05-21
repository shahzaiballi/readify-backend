"""
Management command: fix_stale_covers

Clears cover_image fields that were stored as local filesystem paths by the old
broken code (pattern: books/covers/cover_*.png or covers/cover_*.png).

With Cloudinary configured, these paths generate Cloudinary URLs pointing to
files that were never actually uploaded there — resulting in 404s.

After clearing:
  - Books with cover_image_url set → get_cover_url() falls back to that URL ✅
  - Books with neither → cover_image_url is fetched from Google/Open Library ✅

Usage:
    python manage.py fix_stale_covers
    python manage.py fix_stale_covers --dry-run
"""

import re
from django.core.management.base import BaseCommand
from apps.books.models import Book


STALE_PATTERN = re.compile(r'^(books/)?covers/cover_[0-9a-f\-]+\.png$')


class Command(BaseCommand):
    help = 'Clear stale local cover_image paths left by the old broken extraction code.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making any changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        books = Book.objects.exclude(cover_image='').exclude(cover_image=None)

        fixed = 0
        skipped = 0

        for book in books:
            stored_name = book.cover_image.name or ''
            if not STALE_PATTERN.match(stored_name):
                skipped += 1
                continue

            action = '[DRY RUN] Would clear' if dry_run else 'Clearing'
            fallback = book.cover_image_url or '(none — will need manual cover)'
            self.stdout.write(
                f"{action}: {book.title!r} — cover_image={stored_name!r}  fallback={fallback!r}"
            )

            if not dry_run:
                book.cover_image = None
                book.save(update_fields=['cover_image'])

                if not book.cover_image_url:
                    try:
                        from apps.books.cover_service import fetch_cover_image_url
                        url = fetch_cover_image_url(title=book.title, author=book.author)
                        if url:
                            book.cover_image_url = url
                            book.save(update_fields=['cover_image_url'])
                            self.stdout.write(f"  → Fetched fallback URL: {url}")
                    except Exception as exc:
                        self.stdout.write(self.style.WARNING(f"  → Could not fetch URL: {exc}"))

            fixed += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone — {'would fix' if dry_run else 'fixed'} {fixed} book(s), skipped {skipped} (already clean)."
        ))
