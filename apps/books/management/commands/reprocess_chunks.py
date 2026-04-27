"""
apps/books/management/commands/reprocess_chunks.py

Re-splits existing chapter text into proper chunks for books that were
processed with the old (broken) Claude-based chunker.

Usage:
    # Reprocess ALL books that have chapters with only 1 chunk:
    python manage.py reprocess_chunks

    # Reprocess a specific book by ID:
    python manage.py reprocess_chunks --book-id <uuid>

    # Dry run — show what would be reprocessed without changing anything:
    python manage.py reprocess_chunks --dry-run
"""

from django.core.management.base import BaseCommand
from apps.books.models import Book, Chapter, Chunk


class Command(BaseCommand):
    help = 'Reprocess chunks for books where AI failed to split text properly'

    def add_arguments(self, parser):
        parser.add_argument(
            '--book-id',
            type=str,
            help='Reprocess a specific book UUID only',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be reprocessed without making changes',
        )
        parser.add_argument(
            '--words-per-chunk',
            type=int,
            default=275,
            help='Target words per chunk (default: 275 ≈ 1.5 min reading)',
        )

    def handle(self, *args, **options):
        from apps.books.tasks import split_text_into_chunks

        dry_run = options['dry_run']
        words_per_chunk = options['words_per_chunk']
        book_id = options.get('book_id')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be made\n'))

        # Find books to reprocess
        if book_id:
            books = Book.objects.filter(id=book_id)
            if not books.exists():
                self.stdout.write(self.style.ERROR(f'Book {book_id} not found'))
                return
        else:
            # Find all books that have at least one chapter with only 1 chunk
            # These are the "broken" books from the old processor
            books_with_broken_chunks = set()
            for chapter in Chapter.objects.prefetch_related('chunks').all():
                chunk_count = chapter.chunks.count()
                if chunk_count == 1:
                    # Check if the single chunk has a lot of text (indicating it should be split)
                    single_chunk = chapter.chunks.first()
                    if single_chunk and len(single_chunk.text.split()) > 300:
                        books_with_broken_chunks.add(chapter.book_id)

            books = Book.objects.filter(id__in=books_with_broken_chunks)

        if not books.exists():
            self.stdout.write(self.style.SUCCESS('✅ No books need reprocessing!'))
            return

        self.stdout.write(f'Found {books.count()} book(s) to reprocess:\n')

        total_chunks_before = 0
        total_chunks_after = 0

        for book in books:
            self.stdout.write(f'\n📚 "{book.title}" ({book.id})')
            chapters = book.chapters.prefetch_related('chunks').order_by('chapter_number')

            for chapter in chapters:
                chunks = list(chapter.chunks.order_by('chunk_index'))
                current_chunk_count = len(chunks)

                # Reconstruct full chapter text from existing chunks
                full_text = ' '.join(c.text for c in chunks)

                if not full_text.strip():
                    self.stdout.write(
                        self.style.WARNING(
                            f'  Ch.{chapter.chapter_number}: No text found — skipping'
                        )
                    )
                    continue

                # Calculate what the new chunks would be
                new_chunks = split_text_into_chunks(full_text, words_per_chunk=words_per_chunk)
                new_chunk_count = len(new_chunks)

                total_chunks_before += current_chunk_count
                total_chunks_after += new_chunk_count

                status = '✅' if new_chunk_count > current_chunk_count else '⚠️'
                self.stdout.write(
                    f'  {status} Ch.{chapter.chapter_number} "{chapter.title[:40]}": '
                    f'{current_chunk_count} chunk(s) → {new_chunk_count} chunk(s) '
                    f'({len(full_text.split())} words)'
                )

                if not dry_run and new_chunk_count != current_chunk_count:
                    # Delete old chunks and write new ones
                    chapter.chunks.all().delete()
                    for i, chunk_text in enumerate(new_chunks):
                        chunk_text = chunk_text.strip()
                        if not chunk_text:
                            continue
                        word_count = len(chunk_text.split())
                        Chunk.objects.create(
                            chapter=chapter,
                            chunk_index=i,
                            text=chunk_text,
                            estimated_minutes=max(1, round(word_count / 200)),
                        )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'    → Rewrote {new_chunk_count} chunks'
                        )
                    )

        self.stdout.write(f'\n{"=" * 50}')
        self.stdout.write(f'Total chunks before: {total_chunks_before}')
        self.stdout.write(f'Total chunks after:  {total_chunks_after}')
        improvement = total_chunks_after - total_chunks_before
        self.stdout.write(
            self.style.SUCCESS(f'Net improvement: +{improvement} chunks')
            if improvement > 0
            else self.style.WARNING(f'Net change: {improvement} chunks')
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nDRY RUN complete — run without --dry-run to apply changes')
            )
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ Reprocessing complete!'))