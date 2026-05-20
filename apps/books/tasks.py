"""
apps/books/tasks.py

NEW 3-STAGE PIPELINE:
  Stage 1 — task_extract_and_detect   : PDF extraction + 3-path chapter detection
  Stage 2 — (user reviews chapters via Flutter — no task)
  Stage 3 — task_build_reading_schedule: confirmed chapters → Chunk records + ReadingSchedule

GOLDEN RULE: Never send >8,000 words to DeepSeek in a single call.
All AI calls are in apps/book_intelligence/. This file is pure code — no AI.
"""

import math
import re
import logging
from datetime import timezone, datetime
from celery import shared_task
from django.db import transaction
from django.utils import timezone as dj_timezone

logger = logging.getLogger(__name__)


# ── Deterministic Text Splitter ────────────────────────────────────────────────

def split_text_into_chunks(text: str, words_per_chunk: int = 250) -> list[str]:
    """
    Reliably split chapter text into bite-sized reading chunks.

    Strategy:
    1. Split into sentences for natural reading breaks
    2. Accumulate sentences until we hit the word limit
    3. Flush to a new chunk — never cut mid-sentence
    4. Guarantees at least 1 chunk even for very short text

    At 250 words/chunk and ~275 words/page:
      - 1 page  →  ~1 chunk
      - 17 pages → ~18 chunks  (the expected number per chapter)
      - 30 pages → ~33 chunks
    """
    if not text or not text.strip():
        return []

    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text.strip())
    text = re.sub(r'[ \t]{2,}', ' ', text)

    # Split on sentence-ending punctuation followed by whitespace
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return [text.strip()]

    chunks: list[str] = []
    current_words: list[str] = []
    current_count = 0

    for sentence in sentences:
        s_words = sentence.split()
        s_count = len(s_words)

        # If adding this sentence would exceed limit AND we already have content, flush
        if current_count + s_count > words_per_chunk and current_words:
            chunks.append(' '.join(current_words))
            current_words = s_words
            current_count = s_count
        else:
            current_words.extend(s_words)
            current_count += s_count

    # Flush any remaining words
    if current_words:
        remaining = ' '.join(current_words).strip()
        if remaining:
            chunks.append(remaining)

    return chunks if chunks else [text.strip()]


# ── PDF Helpers ────────────────────────────────────────────────────────────────

def extract_first_page_as_image(pdf_path: str) -> str:
    """Extract the first page of a PDF as a cover image."""
    try:
        import fitz
        from PIL import Image
        import io
        import uuid
        import os
        from django.conf import settings
    except ImportError as e:
        logger.error(f"Required library not installed: {e}")
        return ""

    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            doc.close()
            return ""

        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))

        img = Image.frombytes(
            "RGB" if pix.n == 3 else "RGBA",
            (pix.width, pix.height),
            pix.samples
        )

        if img.mode == 'RGBA':
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[3] if len(img.split()) == 4 else None)
            img = rgb_img

        doc.close()

        covers_dir = os.path.join(settings.MEDIA_ROOT, 'books', 'covers')
        os.makedirs(covers_dir, exist_ok=True)

        filename = f"cover_{uuid.uuid4()}.png"
        filepath = os.path.join(covers_dir, filename)
        img.save(filepath, 'PNG', quality=95)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            relative_path = f"books/covers/{filename}"
            logger.info(f"[PDF Cover] ✅ Extracted: {relative_path}")
            return relative_path

        return ""

    except Exception as exc:
        logger.warning(f"[PDF Cover] ❌ Failed: {exc}", exc_info=True)
        return ""


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """Extract text page-by-page using PyMuPDF."""
    try:
        import fitz
    except ImportError:
        raise ImportError("PyMuPDF is not installed. Run: pip install PyMuPDF")

    pages = []
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        if text:
            pages.append({'page_number': page_num + 1, 'text': text})
    doc.close()
    logger.info(f"[PDF] Extracted {len(pages)} pages from {pdf_path}")
    return pages


def extract_chapter_text(pages_dict: dict, start_page: int, end_page: int) -> str:
    """Extract and join text from a page range (start_page..end_page inclusive)."""
    texts = []
    for pn in range(start_page, end_page + 1):
        if pn in pages_dict:
            texts.append(pages_dict[pn])
    return '\n\n'.join(texts)


def _merge_small_chunks(chunks: list[str], min_words: int = 100) -> list[str]:
    """
    Merge any chunk shorter than min_words into the previous chunk.
    Ensures minimum readable chunk size.
    """
    if not chunks:
        return chunks

    merged = [chunks[0]]
    for chunk in chunks[1:]:
        if len(chunk.split()) < min_words and merged:
            merged[-1] = merged[-1] + ' ' + chunk
        else:
            merged.append(chunk)
    return merged


# ── Private Helpers ───────────────────────────────────────────────────────────

def _apply_ai_chapter_validation(chapters: list[dict], pages: list[dict], book_title: str) -> list[dict]:
    """
    Fix 4 — AI Chapter Validation Pass.
    After deterministic detection, sends first 100 words of each chapter to AI to:
    1. Confirm the chapter is genuine reading content (not TOC/preface/about-author/index)
    2. Replace generic titles ("Chapter 1") with descriptive ones inferred from the text
    Only runs for non-manual detection (bookmarks / text_toc / ai_generated).
    Falls back to original chapters on any failure — never crashes the pipeline.
    """
    if not chapters or not pages:
        return chapters

    pages_dict = {p['page_number']: p['text'] for p in pages}

    chapter_openings = []
    for ch in chapters:
        text_parts = []
        for pn in range(ch['start_page'], min(ch['start_page'] + 3, ch['end_page'] + 1)):
            if pn in pages_dict:
                text_parts.append(pages_dict[pn])
        raw_text = ' '.join(text_parts)
        opening = ' '.join(raw_text.split()[:100])
        chapter_openings.append({
            'chapter_number': ch['chapter_number'],
            'title': ch['title'],
            'opening_text': opening,
        })

    try:
        from apps.book_intelligence.ai_client import validate_and_rename_chapters
        validation_results = validate_and_rename_chapters(book_title, chapter_openings)
    except Exception as exc:
        logger.warning(f'[ChapterValidation] AI call failed: {exc} — keeping original chapters')
        return chapters

    if not validation_results:
        return chapters

    val_map = {v['chapter_number']: v for v in validation_results}
    refined = []
    for ch in chapters:
        val = val_map.get(ch['chapter_number'])
        if val is None:
            refined.append(ch)
            continue
        if not val.get('is_valid', True):
            logger.info(f'[ChapterValidation] Rejected "{ch["title"]}" as non-content')
            continue
        suggested = (val.get('suggested_title') or '').strip()
        if suggested and len(suggested) > 5:
            is_generic = bool(re.match(r'^(chapter|part|section)\s+\w+$', ch['title'], re.IGNORECASE))
            if is_generic:
                ch = dict(ch)
                logger.info(f'[ChapterValidation] Renamed "{ch["title"]}" → "{suggested}"')
                ch['title'] = suggested
        refined.append(ch)

    # Re-number contiguously after removals
    for i, ch in enumerate(refined):
        ch = dict(ch)
        ch['chapter_number'] = i + 1
        refined[i] = ch

    logger.info(
        f'[ChapterValidation] {len(chapters)} → {len(refined)} chapters after AI validation'
    )

    # Safety: if validation wiped everything out, fall back to original
    if len(refined) < 2:
        logger.warning('[ChapterValidation] Too few chapters after validation — reverting to pre-validation list')
        return chapters

    return refined


def _mark_upload_failed(upload, book, error_message: str, stage: str = 'failed'):
    """Set both upload and book to FAILED status with detailed stage info."""
    try:
        upload.status = upload.Status.FAILED
        upload.error_message = error_message
        upload.processing_stage = stage
        upload.save(update_fields=['status', 'error_message', 'processing_stage'])
    except Exception as e:
        logger.error(f'[_mark_failed] Could not update upload: {e}')

    try:
        book.processing_status = book.ProcessingStatus.FAILED
        book.processing_error = error_message
        book.save(update_fields=['processing_status', 'processing_error'])
    except Exception as e:
        logger.error(f'[_mark_failed] Could not update book: {e}')


# ── STAGE 1: Extract & Detect ─────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60,
             name='books.task_extract_and_detect')
def task_extract_and_detect(self, upload_id: str):
    """
    Stage 1: Extract PDF text, detect chapter structure via 3-path TOC detection.
    Sets upload.status = AWAITING_CONFIRM when done.
    No AI used for Path A (bookmarks) or Path B (text TOC).
    AI only used as Path C last resort using page signals (~1,500 words max).
    """
    from apps.books.models import Book, UserUploadedBook
    from apps.books.toc_detector import (
        detect_from_bookmarks, detect_from_text,
        build_page_signals, validate_chapter_structure, build_manual_chapters,
    )
    from apps.book_intelligence.models import BookIntelligenceProfile, BookIntelligenceChapter

    logger.info(f'[Stage1] Starting — upload_id={upload_id}')

    try:
        upload = UserUploadedBook.objects.select_related('uploaded_by', 'book').get(id=upload_id)
    except UserUploadedBook.DoesNotExist:
        logger.error(f'[Stage1] Upload {upload_id} not found')
        return

    # Ensure Book record exists
    if upload.book is None:
        book = Book.objects.create(
            title=upload.title,
            author=upload.author or 'Unknown Author',
            category='User Upload',
            source=Book.Source.USER_UPLOAD,
            processing_status=Book.ProcessingStatus.PROCESSING,
            reading_mode=upload.reading_mode,
            daily_minutes=upload.daily_minutes,
            is_published=True,
            is_recommended=False,
        )
        upload.book = book
        upload.save(update_fields=['book'])
    else:
        book = upload.book
        book.reading_mode = upload.reading_mode
        book.daily_minutes = upload.daily_minutes
        book.save(update_fields=['reading_mode', 'daily_minutes'])

    # Update status
    upload.status = UserUploadedBook.Status.PROCESSING
    upload.processing_stage = 'extracting'
    upload.save(update_fields=['status', 'processing_stage'])
    book.processing_status = Book.ProcessingStatus.PROCESSING
    book.save(update_fields=['processing_status'])

    # Extract cover if needed
    if not book.cover_image and not book.cover_image_url:
        cover_path = extract_first_page_as_image(upload.pdf_file.path)
        if cover_path:
            book.cover_image = cover_path
            book.save(update_fields=['cover_image'])

    # Extract PDF text (all pages)
    try:
        pages = extract_text_from_pdf(upload.pdf_file.path)
    except Exception as exc:
        logger.error(f'[Stage1] PDF extraction failed: {exc}', exc_info=True)
        _mark_upload_failed(upload, book, str(exc), 'failed:extract')
        raise self.retry(exc=exc)

    if not pages:
        _mark_upload_failed(upload, book, 'PDF has no extractable text.', 'failed:empty')
        return

    total_pages = len(pages)
    upload.total_pages = total_pages
    upload.processing_stage = 'detecting_chapters'
    upload.save(update_fields=['total_pages', 'processing_stage'])

    chapters = []
    chapter_source = 'manual'

    # ── Path A: PDF Bookmarks ─────────────────────────────────────────────────
    upload.processing_stage = 'detecting:bookmarks'
    upload.save(update_fields=['processing_stage'])

    bookmark_chapters = detect_from_bookmarks(upload.pdf_file.path)
    if bookmark_chapters and validate_chapter_structure(bookmark_chapters, total_pages):
        chapters = bookmark_chapters
        chapter_source = 'bookmarks'
        logger.info(f'[Stage1] Path A: {len(chapters)} chapters from bookmarks')

    # ── Path B: Text TOC ──────────────────────────────────────────────────────
    if not chapters:
        upload.processing_stage = 'detecting:text_toc'
        upload.save(update_fields=['processing_stage'])

        text_chapters = detect_from_text(pages, total_pages)
        if text_chapters and validate_chapter_structure(text_chapters, total_pages):
            chapters = text_chapters
            chapter_source = 'text_toc'
            logger.info(f'[Stage1] Path B: {len(chapters)} chapters from text TOC')

    # ── Path C: AI Fallback (page signals only — never full book) ─────────────
    if not chapters:
        upload.processing_stage = 'detecting:ai_fallback'
        upload.save(update_fields=['processing_stage'])

        page_signals = build_page_signals(pages)
        try:
            from apps.book_intelligence.ai_client import detect_chapter_boundaries
            ai_chapters = detect_chapter_boundaries(page_signals, total_pages, upload.title)
            if ai_chapters and validate_chapter_structure(ai_chapters, total_pages):
                chapters = ai_chapters
                chapter_source = 'ai_generated'
                logger.info(f'[Stage1] Path C: {len(chapters)} chapters from AI')
        except Exception as exc:
            logger.warning(f'[Stage1] AI fallback failed: {exc}')

    # ── Final Fallback: deterministic 17-pages-per-chapter ───────────────────
    if not chapters:
        chapters = build_manual_chapters(pages, pages_per_chapter=17)
        chapter_source = 'manual'
        logger.info(f'[Stage1] Manual fallback: {len(chapters)} chapters')

    # ── Fix 4: AI Chapter Validation (non-manual paths only) ─────────────────
    if chapter_source != 'manual':
        upload.processing_stage = 'validating_chapters'
        upload.save(update_fields=['processing_stage'])
        chapters = _apply_ai_chapter_validation(chapters, pages, upload.title)
        # If validation reduced to < 2 chapters, fall back to manual
        if len(chapters) < 2:
            chapters = build_manual_chapters(pages, pages_per_chapter=17)
            chapter_source = 'manual'
            logger.warning('[Stage1] Validation left < 2 chapters — using manual fallback')

    # Persist chapter_source on Book
    book.chapter_source = chapter_source
    book.save(update_fields=['chapter_source'])

    # Store toc_raw on upload for Flutter review
    upload.toc_raw = chapters
    upload.save(update_fields=['toc_raw'])

    # Create / refresh BookIntelligenceProfile + BookIntelligenceChapter records
    profile, _ = BookIntelligenceProfile.objects.get_or_create(
        book=book,
        defaults={'status': BookIntelligenceProfile.Status.PENDING},
    )

    with transaction.atomic():
        profile.ai_chapters.all().delete()
        for ch in chapters:
            BookIntelligenceChapter.objects.create(
                profile=profile,
                chapter_number=ch['chapter_number'],
                title=ch['title'],
                start_page=ch['start_page'],
                end_page=ch['end_page'],
                page_range_display=ch.get(
                    'page_range_display',
                    f"Pages {ch['start_page']}–{ch['end_page']}"
                ),
                user_confirmed=False,
            )

    # Mark as awaiting user confirmation
    upload.status = UserUploadedBook.Status.AWAITING_CONFIRM
    upload.processing_stage = 'awaiting_confirm'
    upload.save(update_fields=['status', 'processing_stage'])

    logger.info(
        f'[Stage1] ✅ Done — {len(chapters)} chapters detected via {chapter_source}. '
        f'Awaiting user confirmation.'
    )


# ── STAGE 3: Build Reading Schedule ──────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60,
             name='books.task_build_reading_schedule')
def task_build_reading_schedule(self, book_id: str, user_id: int):
    """
    Stage 3: Create Chapter + Chunk records from confirmed BookIntelligenceChapter data.
    Uses daily_minutes × 200 wpm formula — no AI.
    Triggers book brief generation on completion.
    """
    from apps.books.models import Book, Chapter, Chunk, UserUploadedBook, ReadingSchedule
    from apps.book_intelligence.models import BookIntelligenceProfile

    logger.info(f'[Stage3] Building reading schedule — book_id={book_id}')

    try:
        book = Book.objects.get(id=book_id)
    except Book.DoesNotExist:
        logger.error(f'[Stage3] Book {book_id} not found')
        return

    try:
        profile = book.intelligence_profile
    except BookIntelligenceProfile.DoesNotExist:
        logger.error(f'[Stage3] No intelligence profile for book {book_id}')
        return

    # Get confirmed chapters (or all if none explicitly confirmed)
    confirmed_chapters = profile.ai_chapters.filter(
        user_confirmed=True
    ).order_by('chapter_number')

    if not confirmed_chapters.exists():
        confirmed_chapters = profile.ai_chapters.all().order_by('chapter_number')

    if not confirmed_chapters.exists():
        logger.error(f'[Stage3] No chapters for book {book_id}')
        return

    # Resolve PDF path
    pdf_path = None
    try:
        upload = book.user_upload_source
        if upload and upload.pdf_file:
            pdf_path = upload.pdf_file.path
            upload.status = UserUploadedBook.Status.SCHEDULING
            upload.processing_stage = 'building_schedule'
            upload.save(update_fields=['status', 'processing_stage'])
    except Exception:
        pass
    if not pdf_path and book.pdf_file:
        pdf_path = book.pdf_file.path

    if not pdf_path:
        logger.error(f'[Stage3] No PDF path for book {book_id}')
        return

    # Extract all pages once and build lookup dict
    pages = extract_text_from_pdf(pdf_path)
    pages_dict = {p['page_number']: p['text'] for p in pages}

    pages_per_day = book.daily_minutes or 30
    words_per_session = pages_per_day * 200  # 200 wpm × daily_minutes

    schedule_data = []
    current_day = 1
    total_chunks_created = 0

    # Wipe existing chapters/chunks for this book (idempotent)
    with transaction.atomic():
        book.chapters.all().delete()

    with transaction.atomic():
        for ai_ch in confirmed_chapters:
            chapter_text = extract_chapter_text(
                pages_dict, ai_ch.start_page, ai_ch.end_page
            )
            if not chapter_text.strip():
                chapter_text = f'{ai_ch.title} — content not extractable.'

            word_count = len(chapter_text.split())
            estimated_chapter_minutes = max(1, round(word_count / 200))

            chapter = Chapter.objects.create(
                book=book,
                chapter_number=ai_ch.chapter_number,
                title=ai_ch.title,
                page_range=ai_ch.page_range_display,
                duration_in_minutes=estimated_chapter_minutes,
                start_page=ai_ch.start_page,
                end_page=ai_ch.end_page,
                is_locked=False,
            )

            # Split into page-sized chunks (~300 words = 1 page ≈ 1.5 min reading).
            # day_number is assigned per-chunk sequentially so that TodayReadingView
            # can slice pages_per_day chunks using positional indexing.
            raw_chunks = split_text_into_chunks(
                chapter_text, words_per_chunk=300
            )
            chunks_text = _merge_small_chunks(raw_chunks, min_words=100)

            if not chunks_text and chapter_text.strip():
                chunks_text = [chapter_text.strip()]

            for i, chunk_text in enumerate(chunks_text):
                chunk_text = chunk_text.strip()
                if not chunk_text:
                    continue

                chunk_word_count = len(chunk_text.split())
                estimated_minutes = max(1, round(chunk_word_count / 200))

                chunk = Chunk.objects.create(
                    chapter=chapter,
                    chunk_index=i,
                    text=chunk_text,
                    estimated_minutes=estimated_minutes,
                    day_number=current_day,
                    words_count=chunk_word_count,
                )

                schedule_data.append({
                    'day': current_day,
                    'chunk_ids': [str(chunk.id)],
                    'estimated_minutes': estimated_minutes,
                    'chapter_number': ai_ch.chapter_number,
                    'chapter_title': ai_ch.title,
                })
                current_day += 1
                total_chunks_created += 1

        # Update book totals
        book.total_chapters = confirmed_chapters.count()
        book.processing_status = Book.ProcessingStatus.COMPLETED
        book.save(update_fields=['total_chapters', 'processing_status'])

    # Persist ReadingSchedule
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        ReadingSchedule.objects.update_or_create(
            user=user,
            book=book,
            defaults={
                'schedule_data': schedule_data,
                'total_days': current_day - 1,
                'start_date': dj_timezone.now().date(),
            },
        )
    except Exception as exc:
        logger.warning(f'[Stage3] Could not save ReadingSchedule: {exc}')

    # Ensure UserBook entry exists
    from apps.library.models import UserBook
    UserBook.objects.get_or_create(
        user_id=user_id,
        book=book,
        defaults={'status': UserBook.Status.NOT_STARTED},
    )

    # Update upload status to PROCESSING (brief + summaries still pending)
    try:
        upload = book.user_upload_source
        upload.status = UserUploadedBook.Status.PROCESSING
        upload.processing_stage = 'generating_brief'
        upload.save(update_fields=['status', 'processing_stage'])
    except Exception:
        pass

    logger.info(
        f'[Stage3] ✅ Schedule built: {current_day - 1} days, '
        f'{total_chunks_created} chunks for "{book.title}"'
    )

    # Trigger Stage 4 FIRST so it isn't blocked behind chunk-cleaning tasks in solo pool
    try:
        from apps.book_intelligence.tasks import generate_book_brief_task
        generate_book_brief_task.delay(str(profile.id), user_id)
    except Exception as exc:
        logger.warning(f'[Stage3] Could not queue book brief task: {exc}')

    # Fix 5: Pre-clean the first day's chunks (queued AFTER brief so brief runs first)
    try:
        from apps.book_intelligence.tasks import task_clean_chunk
        first_chunks = list(
            Chunk.objects.filter(chapter__book=book)
            .order_by('chapter__chapter_number', 'chunk_index')
            [:(pages_per_day or 10)]
        )
        for chunk in first_chunks:
            task_clean_chunk.delay(str(chunk.id))
        logger.info(f'[Stage3] Queued cleaning for {len(first_chunks)} day-1 chunks')
    except Exception as exc:
        logger.warning(f'[Stage3] Could not queue chunk cleaning: {exc}')


# ── Admin Book Processing (auto-confirm chapters) ────────────────────────────

@shared_task(bind=True, max_retries=2, default_retry_delay=30,
             name='books.process_admin_book_pdf')
def process_admin_book_pdf(self, book_id: str):
    """
    Admin-uploaded book processing.
    Auto-confirms detected chapters (no user review needed for admin books).
    """
    from apps.books.models import Book
    from apps.books.cover_service import fetch_cover_image_url
    from apps.books.toc_detector import (
        detect_from_bookmarks, detect_from_text,
        build_page_signals, validate_chapter_structure, build_manual_chapters,
    )
    from apps.book_intelligence.models import BookIntelligenceProfile, BookIntelligenceChapter

    logger.info(f'[AdminPDF] Starting — book_id={book_id}')

    try:
        book = Book.objects.get(id=book_id)
    except Book.DoesNotExist:
        logger.error(f'[AdminPDF] Book {book_id} not found')
        return

    if not book.pdf_file:
        logger.error(f'[AdminPDF] Book {book_id} has no PDF file')
        return

    # Set PROCESSING immediately — must be first save so the post_save signal
    # no longer sees PENDING and won't queue additional duplicate tasks.
    book.processing_status = Book.ProcessingStatus.PROCESSING
    book.save(update_fields=['processing_status'])

    # Cover (safe now: status is PROCESSING, signal won't re-trigger)
    if not book.cover_image and not book.cover_image_url:
        cover_path = extract_first_page_as_image(book.pdf_file.path)
        if cover_path:
            book.cover_image = cover_path
            book.save(update_fields=['cover_image'])
        else:
            cover_url = fetch_cover_image_url(
                title=book.title, author=book.author, pdf_path=book.pdf_file.path
            )
            if cover_url:
                book.cover_image_url = cover_url
                book.save(update_fields=['cover_image_url'])

    try:
        pages = extract_text_from_pdf(book.pdf_file.path)
    except Exception as exc:
        logger.error(f'[AdminPDF] PDF extraction failed: {exc}', exc_info=True)
        book.processing_status = Book.ProcessingStatus.FAILED
        book.processing_error = str(exc)
        book.save(update_fields=['processing_status', 'processing_error'])
        raise self.retry(exc=exc)

    if not pages:
        book.processing_status = Book.ProcessingStatus.FAILED
        book.processing_error = 'PDF has no extractable text.'
        book.save(update_fields=['processing_status', 'processing_error'])
        return

    total_pages = len(pages)

    # 3-path chapter detection
    chapters = []
    chapter_source = 'manual'

    bookmark_chapters = detect_from_bookmarks(book.pdf_file.path)
    if bookmark_chapters and validate_chapter_structure(bookmark_chapters, total_pages):
        chapters, chapter_source = bookmark_chapters, 'bookmarks'
    else:
        text_chapters = detect_from_text(pages, total_pages)
        if text_chapters and validate_chapter_structure(text_chapters, total_pages):
            chapters, chapter_source = text_chapters, 'text_toc'
        else:
            page_signals = build_page_signals(pages)
            try:
                from apps.book_intelligence.ai_client import detect_chapter_boundaries
                ai_chapters = detect_chapter_boundaries(page_signals, total_pages, book.title)
                if ai_chapters and validate_chapter_structure(ai_chapters, total_pages):
                    chapters, chapter_source = ai_chapters, 'ai_generated'
            except Exception as exc:
                logger.warning(f'[AdminPDF] AI fallback failed: {exc}')

    if not chapters:
        chapters = build_manual_chapters(pages, pages_per_chapter=17)
        chapter_source = 'manual'

    # ── Fix 4: AI Chapter Validation (non-manual paths only) ─────────────────
    if chapter_source != 'manual':
        chapters = _apply_ai_chapter_validation(chapters, pages, book.title)
        if len(chapters) < 2:
            chapters = build_manual_chapters(pages, pages_per_chapter=17)
            chapter_source = 'manual'
            logger.warning('[AdminPDF] Validation left < 2 chapters — using manual fallback')

    book.chapter_source = chapter_source
    book.save(update_fields=['chapter_source'])

    # Create intelligence profile + auto-confirmed chapters
    profile, _ = BookIntelligenceProfile.objects.get_or_create(
        book=book,
        defaults={'status': BookIntelligenceProfile.Status.PENDING},
    )

    with transaction.atomic():
        profile.ai_chapters.all().delete()
        for ch in chapters:
            BookIntelligenceChapter.objects.create(
                profile=profile,
                chapter_number=ch['chapter_number'],
                title=ch['title'],
                start_page=ch['start_page'],
                end_page=ch['end_page'],
                page_range_display=ch.get(
                    'page_range_display',
                    f"Pages {ch['start_page']}–{ch['end_page']}"
                ),
                user_confirmed=True,  # Auto-confirm for admin books
            )

    # Build schedule immediately (admin books use default reading prefs)
    pages_dict = {p['page_number']: p['text'] for p in pages}
    from apps.books.models import Chapter, Chunk
    with transaction.atomic():
        book.chapters.all().delete()
        current_chunk_number = 0
        total_chunks = 0

        for ai_ch in profile.ai_chapters.all().order_by('chapter_number'):
            chapter_text = extract_chapter_text(
                pages_dict, ai_ch.start_page, ai_ch.end_page
            )
            if not chapter_text.strip():
                chapter_text = ai_ch.title

            word_count = len(chapter_text.split())
            chapter = Chapter.objects.create(
                book=book,
                chapter_number=ai_ch.chapter_number,
                title=ai_ch.title,
                page_range=ai_ch.page_range_display,
                duration_in_minutes=max(1, round(word_count / 200)),
                start_page=ai_ch.start_page,
                end_page=ai_ch.end_page,
                is_locked=False,
            )

            # Split into page-sized chunks (~300 words each ≈ 1 book page).
            # day_number uses the global chunk position so TodayReadingView can
            # slice pages_per_day chunks positionally (day_number doubles as
            # a global sequence number here for ordering/reference).
            raw_chunks = split_text_into_chunks(chapter_text, words_per_chunk=300)
            chunks_text = _merge_small_chunks(raw_chunks, min_words=100)
            if not chunks_text and chapter_text.strip():
                chunks_text = [chapter_text.strip()]

            for i, chunk_text in enumerate(chunks_text):
                chunk_text = chunk_text.strip()
                if not chunk_text:
                    continue
                chunk_wc = len(chunk_text.split())
                current_chunk_number += 1
                Chunk.objects.create(
                    chapter=chapter,
                    chunk_index=i,
                    text=chunk_text,
                    estimated_minutes=max(1, round(chunk_wc / 200)),
                    day_number=current_chunk_number,
                    words_count=chunk_wc,
                )
                total_chunks += 1

        book.total_chapters = len(chapters)
        book.processing_status = Book.ProcessingStatus.COMPLETED
        book.processing_error = ''
        book.save(update_fields=['total_chapters', 'processing_status', 'processing_error'])

    logger.info(
        f'[AdminPDF] ✅ Done — "{book.title}": '
        f'{len(chapters)} chapters, {total_chunks} chunks via {chapter_source}'
    )

    # Trigger book brief generation
    try:
        from apps.book_intelligence.tasks import generate_book_brief_task
        generate_book_brief_task.delay(str(profile.id), None)
    except Exception as exc:
        logger.warning(f'[AdminPDF] Could not queue book brief: {exc}')


# ── Legacy alias for admin signal compatibility ───────────────────────────────

@shared_task(bind=True, max_retries=2, name='books.process_user_uploaded_book')
def process_user_uploaded_book(self, upload_id: str):
    """
    Alias kept for backwards compatibility with any existing queued tasks.
    Delegates to task_extract_and_detect.
    """
    task_extract_and_detect.apply_async(args=[upload_id])


# ── Lazy Chapter Metadata (legacy endpoint support) ───────────────────────────

@shared_task(bind=True, max_retries=2, name='books.generate_chapter_metadata')
def generate_chapter_metadata_task(self, chapter_id: str):
    """
    Generates chapter summary + flashcards lazily when user opens a chapter.
    Uses the BookIntelligence pipeline — checks ChapterIntelligence first.
    """
    from apps.books.models import Chapter
    try:
        chapter = Chapter.objects.select_related('book').get(id=chapter_id)
        if hasattr(chapter, 'summary') and chapter.summary:
            return

        # Delegate to book_intelligence pipeline for the user's reading mode
        from apps.book_intelligence.models import (
            BookIntelligenceChapter, ChapterIntelligence
        )
        reading_mode = chapter.book.reading_mode or 'deep'

        ai_chapter = BookIntelligenceChapter.objects.filter(
            profile__book=chapter.book,
            chapter_number=chapter.chapter_number,
        ).first()

        if ai_chapter and not ChapterIntelligence.objects.filter(
            ai_chapter=ai_chapter, mode=reading_mode
        ).exists():
            from apps.book_intelligence.tasks import generate_chapter_intelligence_task
            generate_chapter_intelligence_task.delay(str(ai_chapter.id), reading_mode)

    except Exception as exc:
        logger.error(f'[ChapterMeta] Failed: {exc}')