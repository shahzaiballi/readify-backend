"""
apps/books/signals.py

Django signals for automatic PDF processing.

WHY SIGNALS instead of doing this in the admin's save_model()?

The admin's save_model() only fires when saving through the Django admin panel.
Signals fire on EVERY save — from admin, from API, from management commands.
This makes the system more robust.

We use post_save (after save) instead of pre_save (before save) because
the file needs to be saved to disk before we can read it in the Celery task.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='books.Book')
def trigger_book_pdf_processing(sender, instance, created, **kwargs):
    """
    Fires after any Book is saved.

    Triggers PDF processing when:
    1. A new Book is created WITH a pdf_file, OR
    2. An existing Book is updated and gets a new pdf_file
       (we detect this by checking processing_status == PENDING)

    We avoid re-triggering if already processing/completed
    to prevent duplicate processing on unrelated saves.
    """
    from .models import Book
    from .tasks import process_admin_book_pdf

    # Only process admin-source books (not user uploads — those have their own flow)
    if instance.source != Book.Source.ADMIN:
        return

    # Only trigger if there's a PDF and status is PENDING
    # The admin sets status to PENDING before saving when a new PDF is uploaded
    if instance.pdf_file and instance.processing_status == Book.ProcessingStatus.PENDING:
        # Use .delay() to run in background via Celery
        # transaction.on_commit() ensures the DB write is committed before Celery reads it
        from django.db import transaction
        import logging
        _log = logging.getLogger(__name__)
        book_id = str(instance.id)

        def _dispatch_task():
            try:
                process_admin_book_pdf.delay(book_id)
                _log.info(f'[Signal] Queued process_admin_book_pdf for book {book_id}')
            except Exception as exc:
                _log.error(
                    f'[Signal] Could not queue Celery task for book {book_id}: {exc}. '
                    f'Check CELERY_BROKER_URL env var and ensure Redis is reachable.',
                    exc_info=True,
                )
                # Mark book as failed so the admin sees an actionable status
                from apps.books.models import Book as _Book
                _Book.objects.filter(id=book_id).update(
                    processing_status=_Book.ProcessingStatus.FAILED,
                    processing_error=f'Celery broker unreachable: {exc}',
                )

        transaction.on_commit(_dispatch_task)