"""
apps/book_intelligence/tasks.py

Celery tasks for the Book Intelligence Agent.
All tasks are triggered by user actions (lazy) — nothing runs speculatively.

Tasks:
  classify_and_structure_book   — classification + chapter structure detection
  generate_book_brief_task      — book brief (on first open)
  generate_chapter_intelligence_task — per-chapter mode summaries
  generate_daily_notifications_task  — 4 daily notification pieces
  build_rag_embeddings_task     — build RAG index for Ask Your Book
"""

import logging
from datetime import date, datetime, timezone
from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, name='book_intelligence.classify_and_structure')
def classify_and_structure_book(self, book_id: str):
    """
    Step 1: Classify book type + detect semantic chapter structure.
    Triggered after book PDF is fully processed (processing_status=COMPLETED).
    """
    from apps.books.models import Book, Chapter
    from apps.book_intelligence.models import (
        BookIntelligenceProfile, BookIntelligenceChapter
    )
    from apps.book_intelligence.ai_client import classify_book, detect_chapter_structure

    logger.info(f'[Intelligence] 🚀 classify_and_structure_book — book_id={book_id}')

    try:
        book = Book.objects.get(id=book_id)
    except Book.DoesNotExist:
        logger.error(f'[Intelligence] Book {book_id} not found')
        return

    # Create or get intelligence profile
    profile, created = BookIntelligenceProfile.objects.get_or_create(
        book=book,
        defaults={'status': BookIntelligenceProfile.Status.CLASSIFYING},
    )

    if not created and profile.status == BookIntelligenceProfile.Status.READY:
        logger.info(f'[Intelligence] Profile already READY for "{book.title}" — skipping')
        return

    profile.status = BookIntelligenceProfile.Status.CLASSIFYING
    profile.save(update_fields=['status'])

    # Get existing chapters from apps.books
    chapters = Chapter.objects.filter(book=book).order_by('chapter_number')
    if not chapters.exists():
        logger.warning(f'[Intelligence] No chapters found for book {book_id} — waiting')
        profile.status = BookIntelligenceProfile.Status.FAILED
        profile.error_message = 'No chapters found. Ensure PDF processing completed first.'
        profile.save(update_fields=['status', 'error_message'])
        return

    # Build text sample from first chapter
    from apps.books.models import Chunk
    first_chapter_chunks = Chunk.objects.filter(
        chapter__book=book
    ).order_by('chapter__chapter_number', 'chunk_index')[:10]

    text_sample = ' '.join(c.text for c in first_chapter_chunks)[:3000]

    # Step 1a: Classify book
    try:
        classification = classify_book(book.title, text_sample)
        profile.book_type = classification.get('book_type', 'other')
        profile.detected_language = classification.get('language', 'English')
        profile.complexity_level = classification.get('complexity', 'intermediate')
        profile.classification_raw = classification
        profile.status = BookIntelligenceProfile.Status.STRUCTURING
        profile.save(update_fields=[
            'book_type', 'detected_language', 'complexity_level',
            'classification_raw', 'status'
        ])
        logger.info(f'[Intelligence] Classified "{book.title}": {classification.get("book_type")}')
    except Exception as exc:
        logger.warning(f'[Intelligence] Classification failed: {exc} — using defaults')

    # Step 1b: Detect chapter structure
    existing_chapters = list(chapters.values(
        'chapter_number', 'title', 'page_range'
    ))

    try:
        structured = detect_chapter_structure(book.title, text_sample, existing_chapters)
    except Exception as exc:
        logger.warning(f'[Intelligence] Structure detection failed: {exc} — using existing')
        structured = [
            {
                'chapter_number': ch['chapter_number'],
                'title': ch['title'],
                'start_page': 1,
                'end_page': 17,
                'hook': f"Explore chapter {ch['chapter_number']} of {book.title}",
            }
            for ch in existing_chapters
        ]

    # Save AI chapters
    with transaction.atomic():
        profile.ai_chapters.all().delete()
        for ch_data in structured:
            ch_num = ch_data.get('chapter_number', 1)
            # Find the matching existing chapter for page range display
            existing = next(
                (c for c in existing_chapters if c['chapter_number'] == ch_num),
                {}
            )
            BookIntelligenceChapter.objects.create(
                profile=profile,
                chapter_number=ch_num,
                title=ch_data.get('title', f'Chapter {ch_num}'),
                start_page=ch_data.get('start_page', 1),
                end_page=ch_data.get('end_page', 17),
                page_range_display=existing.get('page_range', ''),
                chapter_hook=ch_data.get('hook', ''),
            )

    logger.info(
        f'[Intelligence] ✅ Structured "{book.title}": '
        f'{len(structured)} AI chapters saved'
    )

    # Step 1c: Queue embedding build
    profile.status = BookIntelligenceProfile.Status.EMBEDDING
    profile.save(update_fields=['status'])

    build_rag_embeddings_task.delay(str(profile.id), str(book_id))


@shared_task(bind=True, max_retries=2, name='book_intelligence.build_rag_embeddings')
def build_rag_embeddings_task(self, profile_id: str, book_id: str):
    """Build RAG embeddings for all book chunks."""
    from apps.book_intelligence.models import BookIntelligenceProfile
    from apps.book_intelligence.rag_engine import build_embeddings_for_book

    logger.info(f'[Intelligence] 🔍 Building RAG embeddings — profile={profile_id}')

    try:
        build_embeddings_for_book(profile_id, book_id)

        profile = BookIntelligenceProfile.objects.get(id=profile_id)
        profile.status = BookIntelligenceProfile.Status.READY
        profile.save(update_fields=['status'])

        logger.info(f'[Intelligence] ✅ Book Intelligence READY — profile={profile_id}')

    except Exception as exc:
        logger.error(f'[Intelligence] RAG build failed: {exc}', exc_info=True)
        try:
            profile = BookIntelligenceProfile.objects.get(id=profile_id)
            # Still mark READY even if embeddings fail — other features still work
            profile.status = BookIntelligenceProfile.Status.READY
            profile.error_message = f'RAG embeddings failed: {exc}'
            profile.save(update_fields=['status', 'error_message'])
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=2, name='book_intelligence.generate_book_brief')
def generate_book_brief_task(self, profile_id: str):
    """
    Generate Book Brief on first open. Cached permanently.
    Triggered by GET /intelligence/books/<book_id>/brief/ on cache miss.
    """
    from apps.book_intelligence.models import BookIntelligenceProfile
    from apps.books.models import Summary
    from apps.book_intelligence.ai_client import generate_book_brief

    logger.info(f'[Intelligence] 📚 Generating Book Brief — profile={profile_id}')

    try:
        profile = BookIntelligenceProfile.objects.select_related('book').get(id=profile_id)
    except BookIntelligenceProfile.DoesNotExist:
        logger.error(f'[Intelligence] Profile {profile_id} not found')
        return

    if profile.book_brief:
        logger.info(f'[Intelligence] Brief already exists — skipping')
        return

    # Collect chapter summaries from existing apps.books summaries
    summaries = Summary.objects.filter(
        chapter__book=profile.book
    ).order_by('chapter__chapter_number').values_list('summary_content', flat=True)

    chapter_summaries = list(summaries[:12])

    if not chapter_summaries:
        # Fall back to AI chapter hooks
        hooks = profile.ai_chapters.values_list('chapter_hook', flat=True)
        chapter_summaries = list(hooks[:12])

    try:
        brief = generate_book_brief(
            book_title=profile.book.title,
            book_author=profile.book.author,
            chapter_summaries=chapter_summaries,
        )
        profile.book_brief = brief
        profile.brief_generated_at = datetime.now(tz=timezone.utc)
        profile.save(update_fields=['book_brief', 'brief_generated_at'])
        logger.info(f'[Intelligence] ✅ Book Brief generated for "{profile.book.title}"')
    except Exception as exc:
        logger.error(f'[Intelligence] Book Brief generation failed: {exc}', exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True, max_retries=2, name='book_intelligence.generate_chapter_intelligence')
def generate_chapter_intelligence_task(self, ai_chapter_id: str, mode: str):
    """
    Generate chapter intelligence for a specific reading mode.
    Triggered when user opens a chapter in that mode.
    """
    from apps.book_intelligence.models import BookIntelligenceChapter, ChapterIntelligence
    from apps.books.models import Chunk
    from apps.book_intelligence.ai_client import generate_chapter_summary_for_mode

    logger.info(f'[Intelligence] 📖 Generating {mode} mode — chapter={ai_chapter_id}')

    try:
        ai_chapter = BookIntelligenceChapter.objects.select_related(
            'profile__book'
        ).get(id=ai_chapter_id)
    except BookIntelligenceChapter.DoesNotExist:
        logger.error(f'[Intelligence] AI Chapter {ai_chapter_id} not found')
        return

    # Check if already generated
    if ChapterIntelligence.objects.filter(ai_chapter=ai_chapter, mode=mode).exists():
        logger.info(f'[Intelligence] {mode} already cached — skipping')
        return

    # Get chapter text from existing chunks
    book_id = ai_chapter.profile.book_id
    # Match chapter by number
    from apps.books.models import Chapter
    try:
        existing_chapter = Chapter.objects.get(
            book_id=book_id,
            chapter_number=ai_chapter.chapter_number,
        )
        chunks = Chunk.objects.filter(chapter=existing_chapter).order_by('chunk_index')
        chapter_text = ' '.join(c.text for c in chunks)
    except Chapter.DoesNotExist:
        chapter_text = ai_chapter.chapter_hook or f'Chapter {ai_chapter.chapter_number}'

    try:
        content = generate_chapter_summary_for_mode(
            chapter_title=ai_chapter.title,
            chapter_text=chapter_text,
            mode=mode,
            book_title=ai_chapter.profile.book.title,
        )
        ChapterIntelligence.objects.create(
            ai_chapter=ai_chapter,
            mode=mode,
            content=content,
        )
        logger.info(f'[Intelligence] ✅ {mode} mode generated for "{ai_chapter.title}"')
    except Exception as exc:
        logger.error(f'[Intelligence] Chapter intelligence failed: {exc}', exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True, max_retries=2, name='book_intelligence.generate_daily_notifications')
def generate_daily_notifications_task(self, profile_id: str, user_id: int, target_date: str = None):
    """
    Generate 4 daily notification pieces for a user/book/day.
    target_date: ISO format date string, defaults to today.
    """
    from apps.book_intelligence.models import (
        BookIntelligenceProfile, NotificationContent, BookIntelligenceChapter
    )
    from apps.books.models import Chunk, Chapter
    from apps.book_intelligence.ai_client import generate_daily_notifications

    logger.info(f'[Intelligence] 🔔 Generating notifications — profile={profile_id}, user={user_id}')

    notification_date = (
        date.fromisoformat(target_date) if target_date else date.today()
    )

    try:
        profile = BookIntelligenceProfile.objects.select_related('book').get(id=profile_id)
    except BookIntelligenceProfile.DoesNotExist:
        logger.error(f'[Intelligence] Profile {profile_id} not found')
        return

    # Check if already generated today
    if NotificationContent.objects.filter(
        profile=profile, user_id=user_id, date=notification_date
    ).exists():
        logger.info(f'[Intelligence] Notifications already exist for {notification_date}')
        return

    # Determine which chapter to use (cycle through chapters)
    total_chapters = profile.ai_chapters.count()
    if total_chapters == 0:
        logger.warning(f'[Intelligence] No AI chapters for profile {profile_id}')
        return

    from apps.library.models import UserBook
    from apps.reading.models import ReadingProgress

    # Try to get current chapter from reading progress
    try:
        user_book = UserBook.objects.get(user_id=user_id, book=profile.book)
        day_chapter_num = min(
            getattr(user_book, 'current_chapter', 1) or 1,
            total_chapters
        )
    except Exception:
        day_chapter_num = 1

    # Get AI chapter for this day
    ai_chapter = profile.ai_chapters.filter(
        chapter_number=day_chapter_num
    ).first() or profile.ai_chapters.first()

    # Get chapter text
    try:
        existing_chapter = Chapter.objects.get(
            book=profile.book, chapter_number=ai_chapter.chapter_number
        )
        chunks = Chunk.objects.filter(chapter=existing_chapter).order_by('chunk_index')[:8]
        chapter_text = ' '.join(c.text for c in chunks)
    except Chapter.DoesNotExist:
        chapter_text = ai_chapter.chapter_hook

    try:
        pieces = generate_daily_notifications(
            book_title=profile.book.title,
            chapter_title=ai_chapter.title,
            chapter_text_sample=chapter_text,
            day_number=(notification_date - profile.created_at.date()).days + 1,
        )

        NotificationContent.objects.create(
            user_id=user_id,
            profile=profile,
            date=notification_date,
            morning_hook=pieces.get('morning_hook', ''),
            midday_concept=pieces.get('midday_concept', ''),
            afternoon_story=pieces.get('afternoon_story', ''),
            evening_recap=pieces.get('evening_recap', ''),
            chapter_number=ai_chapter.chapter_number,
        )
        logger.info(f'[Intelligence] ✅ Notifications generated for {notification_date}')
    except Exception as exc:
        logger.error(f'[Intelligence] Notification generation failed: {exc}', exc_info=True)
        raise self.retry(exc=exc, countdown=30)
