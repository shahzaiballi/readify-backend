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
    from apps.book_intelligence.ai_client import classify_book

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

    # Step 1b: Sync AI chapters from existing Chapter records if not already populated
    # (Stage 1 task_extract_and_detect already creates BookIntelligenceChapter records;
    #  this is a fallback for books processed via the legacy /analyze/ endpoint)
    if not profile.ai_chapters.exists():
        existing_chapters = list(chapters.values(
            'chapter_number', 'title', 'page_range'
        ))
        with transaction.atomic():
            for ch in existing_chapters:
                BookIntelligenceChapter.objects.get_or_create(
                    profile=profile,
                    chapter_number=ch['chapter_number'],
                    defaults={
                        'title': ch['title'],
                        'start_page': 1,
                        'end_page': 17,
                        'page_range_display': ch.get('page_range', ''),
                        'user_confirmed': True,
                    },
                )
        logger.info(
            f'[Intelligence] Synced {chapters.count()} chapters from Book '
            f'records for "{book.title}"'
        )
    else:
        logger.info(
            f'[Intelligence] AI chapters already exist for "{book.title}" '
            f'— skipping sync'
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
def generate_book_brief_task(self, profile_id: str, user_id=None):
    """
    Stage 4: Generate Book Brief using chapter titles + first 150 words per chapter.
    Input size: ~800 words max — well within 8k limit.
    Triggers initial summary generation for chapters 1-3 on completion.
    """
    from apps.book_intelligence.models import BookIntelligenceProfile
    from apps.books.models import Chunk
    from apps.book_intelligence.ai_client import generate_book_brief

    logger.info(f'[Intelligence] 📚 Generating Book Brief — profile={profile_id}')

    try:
        profile = BookIntelligenceProfile.objects.select_related('book').get(id=profile_id)
    except BookIntelligenceProfile.DoesNotExist:
        logger.error(f'[Intelligence] Profile {profile_id} not found')
        return

    if profile.book_brief:
        logger.info(f'[Intelligence] Brief already exists — skipping')
        # Still trigger initial summaries if user_id provided
        if user_id:
            generate_initial_summaries_task.delay(profile_id, user_id)
        return

    # Build chapter_openings: title + first 150 words of each chapter
    chapter_openings = []
    for ai_ch in profile.ai_chapters.all().order_by('chapter_number')[:12]:
        from apps.books.models import Chapter
        try:
            ch = Chapter.objects.get(
                book=profile.book, chapter_number=ai_ch.chapter_number
            )
            first_chunks = Chunk.objects.filter(chapter=ch).order_by('chunk_index')[:1]
            opening_text = ' '.join(c.text for c in first_chunks)
            # Truncate to first 150 words
            opening_words = opening_text.split()[:150]
            opening = ' '.join(opening_words)
        except Chapter.DoesNotExist:
            opening = ai_ch.chapter_hook or ''

        chapter_openings.append({'title': ai_ch.title, 'opening': opening})

    if not chapter_openings:
        logger.warning(f'[Intelligence] No chapters for brief — profile={profile_id}')
        return

    try:
        brief = generate_book_brief(
            book_title=profile.book.title,
            book_author=profile.book.author,
            chapter_openings=chapter_openings,
        )
        profile.book_brief = brief
        profile.brief_generated_at = datetime.now(tz=timezone.utc)
        profile.save(update_fields=['book_brief', 'brief_generated_at'])
        logger.info(f'[Intelligence] ✅ Book Brief generated for "{profile.book.title}"')

        # Mark upload as completed
        try:
            from apps.books.models import UserUploadedBook
            upload = profile.book.user_upload_source
            if upload:
                upload.status = UserUploadedBook.Status.COMPLETED
                upload.processing_stage = 'completed'
                from datetime import timezone as tz
                upload.processed_at = datetime.now(tz=tz.utc)
                upload.save(update_fields=['status', 'processing_stage', 'processed_at'])
        except Exception:
            pass

        # Trigger initial summaries for chapters 1-3
        if user_id:
            generate_initial_summaries_task.delay(profile_id, user_id)

    except Exception as exc:
        logger.error(f'[Intelligence] Book Brief generation failed: {exc}', exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True, max_retries=2, name='book_intelligence.generate_chapter_intelligence')
def generate_chapter_intelligence_task(self, ai_chapter_id: str, mode: str):
    """
    Stage 5 (lazy): Generate chapter intelligence for a specific reading mode.
    GOLDEN RULE: If chapter > 8,000 words, splits into 6,000-word sections,
    summarises each, then synthesises into one final response.
    Triggered when user opens a chapter.
    """
    from apps.book_intelligence.models import BookIntelligenceChapter, ChapterIntelligence
    from apps.books.models import Chunk, Chapter
    from apps.book_intelligence.ai_client import (
        generate_chapter_summary_for_mode, synthesise_section_summaries
    )

    logger.info(f'[Intelligence] 📖 Generating {mode} mode — chapter={ai_chapter_id}')

    try:
        ai_chapter = BookIntelligenceChapter.objects.select_related(
            'profile__book'
        ).get(id=ai_chapter_id)
    except BookIntelligenceChapter.DoesNotExist:
        logger.error(f'[Intelligence] AI Chapter {ai_chapter_id} not found')
        return

    if ChapterIntelligence.objects.filter(ai_chapter=ai_chapter, mode=mode).exists():
        logger.info(f'[Intelligence] {mode} already cached — skipping')
        return

    # Get chapter text from Chunk records
    try:
        existing_chapter = Chapter.objects.get(
            book_id=ai_chapter.profile.book_id,
            chapter_number=ai_chapter.chapter_number,
        )
        chunks = Chunk.objects.filter(chapter=existing_chapter).order_by('chunk_index')
        chapter_text = ' '.join(c.text for c in chunks)
    except Chapter.DoesNotExist:
        chapter_text = ai_chapter.chapter_hook or f'Chapter {ai_chapter.chapter_number}'

    book_title = ai_chapter.profile.book.title
    chapter_title = ai_chapter.title
    word_count = len(chapter_text.split())

    # Pull book type + complexity from the intelligence profile
    book_type = ai_chapter.profile.book_type or 'other'
    complexity_level = ai_chapter.profile.complexity_level or 'intermediate'

    try:
        if word_count <= 8000:
            # Short chapter: single AI call
            content = generate_chapter_summary_for_mode(
                chapter_title=chapter_title,
                chapter_text=chapter_text,
                mode=mode,
                book_title=book_title,
                book_type=book_type,
                complexity_level=complexity_level,
            )
        else:
            # Long chapter: split into 6,000-word sections, summarise each, synthesise
            logger.info(
                f'[Intelligence] Chapter "{chapter_title}" is {word_count} words — '
                f'splitting into sections'
            )
            words = chapter_text.split()
            section_size = 6000
            sections = [
                ' '.join(words[i:i + section_size])
                for i in range(0, len(words), section_size)
            ]
            section_summaries = []
            for sec_text in sections:
                sec_result = generate_chapter_summary_for_mode(
                    chapter_title=chapter_title,
                    chapter_text=sec_text,
                    mode=mode,
                    book_title=book_title,
                    book_type=book_type,
                    complexity_level=complexity_level,
                )
                # Convert dict summary to string for synthesis input
                import json as _json
                section_summaries.append(_json.dumps(sec_result))

            content = synthesise_section_summaries(
                section_summaries=section_summaries,
                mode=mode,
                chapter_title=chapter_title,
                book_title=book_title,
            )
            if not content:
                # Fallback: use first section result if synthesis fails
                content = generate_chapter_summary_for_mode(
                    chapter_title=chapter_title,
                    chapter_text=' '.join(words[:6000]),
                    mode=mode,
                    book_title=book_title,
                    book_type=book_type,
                    complexity_level=complexity_level,
                )

        ChapterIntelligence.objects.create(
            ai_chapter=ai_chapter,
            mode=mode,
            content=content,
        )
        logger.info(f'[Intelligence] ✅ {mode} mode generated for "{chapter_title}"')
    except Exception as exc:
        logger.error(f'[Intelligence] Chapter intelligence failed: {exc}', exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True, max_retries=2, name='book_intelligence.generate_initial_summaries')
def generate_initial_summaries_task(self, profile_id: str, user_id: int):
    """
    Stage 5 (pre-gen): Generate summaries for chapters 1-3 in the user's chosen mode.
    Called after book brief is generated. All other chapters are lazy.
    """
    from apps.book_intelligence.models import BookIntelligenceProfile, ChapterIntelligence

    logger.info(f'[Intelligence] ⚡ Pre-generating summaries 1-3 — profile={profile_id}')

    try:
        profile = BookIntelligenceProfile.objects.select_related('book').get(id=profile_id)
    except BookIntelligenceProfile.DoesNotExist:
        logger.error(f'[Intelligence] Profile {profile_id} not found')
        return

    reading_mode = profile.book.reading_mode or 'deep'
    first_three = list(profile.ai_chapters.order_by('chapter_number')[:3])

    for ai_ch in first_three:
        # Pre-generate the user's chosen reading mode
        if not ChapterIntelligence.objects.filter(
            ai_chapter=ai_ch, mode=reading_mode
        ).exists():
            generate_chapter_intelligence_task.delay(str(ai_ch.id), reading_mode)
            logger.info(
                f'[Intelligence] Queued {reading_mode} for Ch.{ai_ch.chapter_number} '
                f'"{ai_ch.title}"'
            )

        # Always pre-generate exam mode (Q&A) regardless of reading_mode
        if reading_mode != 'exam' and not ChapterIntelligence.objects.filter(
            ai_chapter=ai_ch, mode='exam'
        ).exists():
            generate_chapter_intelligence_task.delay(str(ai_ch.id), 'exam')
            logger.info(
                f'[Intelligence] Queued exam/Q&A for Ch.{ai_ch.chapter_number} '
                f'"{ai_ch.title}"'
            )

        # Always pre-generate flashcard mode (front/back cards) for chapters 1-3
        if not ChapterIntelligence.objects.filter(
            ai_chapter=ai_ch, mode='flashcard'
        ).exists():
            generate_chapter_intelligence_task.delay(str(ai_ch.id), 'flashcard')
            logger.info(
                f'[Intelligence] Queued flashcards for Ch.{ai_ch.chapter_number} '
                f'"{ai_ch.title}"'
            )

    logger.info(f'[Intelligence] ✅ Initial summary generation queued for {profile.book.title}')


@shared_task(bind=True, max_retries=3, default_retry_delay=30, name='book_intelligence.task_clean_chunk')
def task_clean_chunk(self, chunk_id: str):
    """
    Fix 5 — Chunk Text Cleaning.
    Removes OCR artifacts (header/footer noise, broken hyphenation, stray page numbers)
    from a single reading chunk. Runs once per chunk — idempotent via is_cleaned flag.
    """
    from apps.books.models import Chunk
    from apps.book_intelligence.ai_client import clean_chunk_text

    try:
        chunk = Chunk.objects.get(id=chunk_id)
    except Chunk.DoesNotExist:
        logger.warning(f'[CleanChunk] Chunk {chunk_id} not found')
        return

    if chunk.is_cleaned:
        logger.info(f'[CleanChunk] Chunk {chunk_id} already cleaned — skipping')
        return

    logger.info(f'[CleanChunk] Cleaning chunk {chunk_id} ({chunk.words_count} words)')

    try:
        cleaned = clean_chunk_text(chunk.text)
        if cleaned and cleaned.strip() and cleaned != chunk.text:
            chunk.text = cleaned
        chunk.is_cleaned = True
        chunk.save(update_fields=['text', 'is_cleaned'])
        logger.info(f'[CleanChunk] ✅ Chunk {chunk_id} cleaned')
    except Exception as exc:
        logger.error(f'[CleanChunk] Failed for chunk {chunk_id}: {exc}', exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, name='book_intelligence.generate_daily_notifications')
def generate_daily_notifications_task(self, profile_id: str, user_id: int, target_date: str = None):  # noqa: E501
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

    # Determine which chunk the user should be reading tomorrow
    from apps.books.models import ReadingSchedule

    ai_chapter = None
    chapter_text = ''

    try:
        schedule = ReadingSchedule.objects.get(
            user_id=user_id, book=profile.book
        )
        # Find tomorrow's day entry
        tomorrow_day = (notification_date - schedule.start_date).days + 2  # +2 for tomorrow
        tomorrow_entries = [
            e for e in schedule.schedule_data
            if e.get('day') == tomorrow_day
        ]
        if tomorrow_entries:
            entry = tomorrow_entries[0]
            ai_chapter = profile.ai_chapters.filter(
                chapter_number=entry.get('chapter_number', 1)
            ).first()
            # Get chunk text for tomorrow's reading
            chunk_ids = entry.get('chunk_ids', [])
            if chunk_ids:
                first_chunk = Chunk.objects.filter(id=chunk_ids[0]).first()
                if first_chunk:
                    chapter_text = first_chunk.text
    except ReadingSchedule.DoesNotExist:
        pass

    # Fallback: use current reading progress
    if not ai_chapter:
        total_chapters = profile.ai_chapters.count()
        if total_chapters == 0:
            logger.warning(f'[Intelligence] No AI chapters for profile {profile_id}')
            return
        from apps.library.models import UserBook
        try:
            user_book = UserBook.objects.get(user_id=user_id, book=profile.book)
            day_chapter_num = min(
                getattr(user_book, 'current_chapter', 1) or 1, total_chapters
            )
        except Exception:
            day_chapter_num = 1
        ai_chapter = profile.ai_chapters.filter(
            chapter_number=day_chapter_num
        ).first() or profile.ai_chapters.first()

    if not chapter_text:
        try:
            existing_chapter = Chapter.objects.get(
                book=profile.book, chapter_number=ai_chapter.chapter_number
            )
            chunks = Chunk.objects.filter(chapter=existing_chapter).order_by('chunk_index')[:4]
            # Respect 8k limit: take first 3,000 words only
            raw = ' '.join(c.text for c in chunks)
            chapter_text = ' '.join(raw.split()[:3000])
        except Chapter.DoesNotExist:
            chapter_text = ai_chapter.chapter_hook or ''

    try:
        pieces = generate_daily_notifications(
            book_title=profile.book.title,
            chapter_title=ai_chapter.title,
            chapter_text_sample=' '.join(chapter_text.split()[:3000]),
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


@shared_task(name='book_intelligence.dispatch_nightly_notifications')
def dispatch_nightly_notifications():
    """
    Celery Beat nightly task (11PM) — fan out one notification job per active user/book.
    Runs via `readify_nightly_notifications` beat schedule in config/celery.py.
    Only dispatches for books that have an intelligence profile + reading schedule.
    """
    from apps.book_intelligence.models import BookIntelligenceProfile
    from apps.books.models import ReadingSchedule

    today_str = date.today().isoformat()
    dispatched = 0

    schedules = ReadingSchedule.objects.select_related(
        'user', 'book', 'book__intelligence_profile'
    ).all()

    for schedule in schedules:
        try:
            profile = schedule.book.intelligence_profile
            generate_daily_notifications_task.delay(
                str(profile.id),
                schedule.user.id,
                today_str,
            )
            dispatched += 1
        except Exception as exc:
            logger.warning(
                f'[Nightly] Could not queue notifications for '
                f'user={schedule.user_id} book={schedule.book_id}: {exc}'
            )

    logger.info(f'[Nightly] Dispatched {dispatched} notification jobs for {today_str}')
