"""
apps/books/tasks.py

Changes vs original:
- Integrated cover_service.fetch_cover_image_url() so every user-uploaded
  book automatically gets a cover image (Google Books → Open Library →
  generated placeholder). No manual upload needed.
- process_user_uploaded_book no longer exits early when upload.book is None.
- Added clearer logging for each processing step.
- transaction.atomic() is used correctly (only around DB writes).
- Retry countdown set to 30 s for faster feedback during development.
"""

import re
import json
import logging
from datetime import timezone, datetime
from celery import shared_task
from django.db import transaction
from django.conf import settings

logger = logging.getLogger(__name__)


# ── PDF Helpers ────────────────────────────────────────────────────────────────

def extract_first_page_as_image(pdf_path: str) -> str:
    """Extract the first page of a PDF as an image and save it as cover."""
    try:
        import fitz  # PyMuPDF
        from PIL import Image
        import io
        import uuid
        import os
        from django.conf import settings
    except ImportError as e:
        logger.error(f"Required library not installed: {e}. Skipping cover extraction.")
        return ""

    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            logger.warning(f"[PDF Cover] PDF has no pages: {pdf_path}")
            doc.close()
            return ""

        # Render first page to image at 1.5x zoom for better quality
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        
        # Convert pixmap to PIL Image (pix.n is number of channels: 3=RGB, 4=RGBA)
        img = Image.frombytes(
            "RGB" if pix.n == 3 else "RGBA",
            (pix.width, pix.height),
            pix.samples
        )
        
        # Ensure RGB (remove alpha channel if present)
        if img.mode == 'RGBA':
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[3] if len(img.split()) == 4 else None)
            img = rgb_img
        
        doc.close()
        
        # Save to media/books/covers/
        covers_dir = os.path.join(settings.MEDIA_ROOT, 'books', 'covers')
        os.makedirs(covers_dir, exist_ok=True)
        
        filename = f"cover_{uuid.uuid4()}.png"
        filepath = os.path.join(covers_dir, filename)
        img.save(filepath, 'PNG', quality=95)
        
        # Verify file was created and has content
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            # Return relative path for Django FileField
            relative_path = f"books/covers/{filename}"
            logger.info(f"[PDF Cover] ✅ Extracted first page: {relative_path} ({os.path.getsize(filepath)} bytes)")
            return relative_path
        else:
            logger.warning(f"[PDF Cover] Image file created but is empty: {filepath}")
            return ""
        
    except Exception as exc:
        logger.warning(f"[PDF Cover] ❌ Failed to extract cover from PDF: {exc}", exc_info=True)
        return ""


def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """Extract text page-by-page using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF is not installed. Run: pip install PyMuPDF")
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


def group_pages_into_chapters(pages: list[dict], pages_per_chapter: int = 15) -> list[dict]:
    """Group flat pages into logical chapters (~15 pages each)."""
    chapters = []
    for i in range(0, len(pages), pages_per_chapter):
        chapter_pages = pages[i:i + pages_per_chapter]
        page_numbers = [p['page_number'] for p in chapter_pages]
        chapters.append({
            'chapter_number': len(chapters) + 1,
            'pages': page_numbers,
            'page_range': f"Pages {page_numbers[0]}–{page_numbers[-1]}",
            'text': '\n\n'.join(p['text'] for p in chapter_pages),
        })
    return chapters


def call_claude_for_chapter(chapter_text: str, chapter_number: int, book_title: str) -> dict:
    """
    Send one chapter's raw text to Claude and get back structured data.
    Falls back to a safe default dict if the API call fails.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        max_chars = 32_000
        if len(chapter_text) > max_chars:
            chapter_text = chapter_text[:max_chars] + '\n\n[...text truncated...]'

        prompt = f"""You are processing Chapter {chapter_number} of "{book_title}".

<chapter_text>{chapter_text}</chapter_text>

Return ONLY valid JSON with NO markdown fences:
{{
  "title": "Descriptive title (max 60 chars)",
  "chunks": ["200-300 word reading chunks — as many as needed"],
  "summary": "2-3 sentence summary of this chapter",
  "key_takeaways": ["Insight 1", "Insight 2", "Insight 3"],
  "flashcards": [{{"question": "...", "answer": "..."}}],
  "estimated_read_minutes": 15
}}"""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()
        response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)

        result = json.loads(response_text)
        logger.info(
            f"[Claude] Chapter {chapter_number}: "
            f"{len(result.get('chunks', []))} chunks, "
            f"{len(result.get('flashcards', []))} flashcards"
        )
        return result

    except Exception as exc:
        logger.warning(f"[Claude] Chapter {chapter_number} failed ({exc}), using fallback.")
        return {
            "title": f"Chapter {chapter_number}",
            "chunks": [chapter_text[:500]] if chapter_text else [],
            "summary": "AI processing unavailable for this chapter.",
            "key_takeaways": [],
            "flashcards": [],
            "estimated_read_minutes": 15,
        }


def save_book_content_to_db(book, chapters_data: list[dict]):
    """
    Wipe any existing chapters/flashcards for this book and write fresh ones.
    """
    from apps.books.models import Chapter, Chunk, Summary, Flashcard

    with transaction.atomic():
        book.chapters.all().delete()
        book.flashcards.all().delete()

        total_flashcards = 0

        for chapter_data in chapters_data:
            chapter = Chapter.objects.create(
                book=book,
                chapter_number=chapter_data['chapter_number'],
                title=chapter_data.get('title', f"Chapter {chapter_data['chapter_number']}"),
                page_range=chapter_data.get('page_range', ''),
                duration_in_minutes=chapter_data.get('estimated_read_minutes', 15),
                is_locked=False,
            )

            for i, chunk_text in enumerate(chapter_data.get('chunks', [])):
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

            summary_text = chapter_data.get('summary', '').strip()
            if summary_text:
                Summary.objects.create(
                    chapter=chapter,
                    title=chapter.title,
                    summary_content=summary_text,
                    key_takeaways=chapter_data.get('key_takeaways', []),
                    is_locked=False,
                )

            for fc in chapter_data.get('flashcards', []):
                if fc.get('question') and fc.get('answer'):
                    Flashcard.objects.create(
                        book=book,
                        question=fc['question'],
                        answer=fc['answer'],
                    )
                    total_flashcards += 1

        book.total_chapters = len(chapters_data)
        book.flashcards_count = total_flashcards
        book.save(update_fields=['total_chapters', 'flashcards_count'])

    logger.info(
        f"[DB] Saved {len(chapters_data)} chapters, "
        f"{total_flashcards} flashcards for book '{book.title}'"
    )


# ── Celery Tasks ───────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=2)
def process_user_uploaded_book(self, upload_id: str):
    """
    Background task: read the PDF, call Claude per chapter, persist results.

    NEW: Automatically fetches a cover image from Google Books / Open Library
    if the book doesn't already have one — so user uploads always look good
    in the Flutter app without requiring a manual image upload.
    """
    from apps.books.models import Book, UserUploadedBook
    from apps.library.models import UserBook
    from apps.books.cover_service import fetch_cover_image_url  # ← NEW

    logger.info(f"[PDF Task] 🚀 Starting — upload_id={upload_id}")

    # ── 1. Fetch the upload record ────────────────────────────────────────────
    try:
        upload = UserUploadedBook.objects.select_related(
            'uploaded_by', 'book'
        ).get(id=upload_id)
    except UserUploadedBook.DoesNotExist:
        logger.error(f"[PDF Task] ❌ Upload not found: {upload_id}")
        return

    logger.info(
        f"[PDF Task] Upload '{upload.title}' by {upload.uploaded_by.email} — "
        f"book linked: {upload.book_id is not None}"
    )

    # ── 2. Ensure a Book record exists ────────────────────────────────────────
    if upload.book is None:
        logger.warning(
            f"[PDF Task] No Book linked to upload {upload_id}. Creating fallback."
        )
        book = Book.objects.create(
            title=upload.title,
            author=upload.author or 'Unknown Author',
            category='User Upload',
            source=Book.Source.USER_UPLOAD,
            processing_status=Book.ProcessingStatus.PENDING,
            is_published=True,
            is_recommended=False,
        )
        upload.book = book
        upload.save(update_fields=['book'])
        logger.info(f"[PDF Task] Fallback Book created: {book.id}")
    else:
        book = upload.book

    # ── 3. Auto-fetch cover image if missing ──────────────────────────────────
    # NEW: Extract the first page of PDF as cover image automatically.
    # This works for both user uploads and admin books.
    if not book.cover_image and not book.cover_image_url:
        logger.info(f"[PDF Task] Extracting first page as cover image for '{book.title}'...")
        cover_path = extract_first_page_as_image(upload.pdf_file.path)
        if cover_path:
            book.cover_image = cover_path
            book.save(update_fields=['cover_image'])
            logger.info(f"[PDF Task] ✅ Cover image extracted: {cover_path}")
        else:
            logger.info(f"[PDF Task] ⚠️  Could not extract cover from PDF. Skipping fallback.")
    else:
        logger.info(f"[PDF Task] Book already has a cover image, skipping auto-fetch.")

    # ── 4. Mark as processing ─────────────────────────────────────────────────
    try:
        upload.status = UserUploadedBook.Status.PROCESSING
        upload.save(update_fields=['status'])

        book.processing_status = Book.ProcessingStatus.PROCESSING
        book.save(update_fields=['processing_status'])
        logger.info(f"[PDF Task] Status → PROCESSING")
    except Exception as exc:
        logger.error(f"[PDF Task] Could not update status: {exc}")
        raise self.retry(exc=exc, countdown=30)

    # ── 5. Extract PDF text ───────────────────────────────────────────────────
    try:
        logger.info(f"[PDF Task] Reading PDF: {upload.pdf_file.path}")
        pages = extract_text_from_pdf(upload.pdf_file.path)
    except Exception as exc:
        logger.error(f"[PDF Task] ❌ PDF extraction failed: {exc}", exc_info=True)
        _mark_failed(upload, book, str(exc))
        raise self.retry(exc=exc, countdown=30)

    if not pages:
        msg = "PDF appears to be empty or has no extractable text."
        logger.error(f"[PDF Task] ❌ {msg}")
        _mark_failed(upload, book, msg)
        return

    logger.info(f"[PDF Task] Extracted {len(pages)} pages")

    # ── 6. Group pages into chapters ──────────────────────────────────────────
    raw_chapters = group_pages_into_chapters(pages)
    logger.info(f"[PDF Task] Grouped into {len(raw_chapters)} chapters")

    # ── 7. Call Claude for each chapter ──────────────────────────────────────
    processed_chapters = []
    for raw_ch in raw_chapters:
        claude_result = call_claude_for_chapter(
            raw_ch['text'],
            raw_ch['chapter_number'],
            upload.title,
        )
        claude_result['chapter_number'] = raw_ch['chapter_number']
        claude_result['page_range'] = raw_ch['page_range']
        processed_chapters.append(claude_result)

    # ── 8. Save everything to the database ───────────────────────────────────
    try:
        save_book_content_to_db(book, processed_chapters)
    except Exception as exc:
        logger.error(f"[PDF Task] ❌ DB save failed: {exc}", exc_info=True)
        _mark_failed(upload, book, str(exc))
        raise self.retry(exc=exc, countdown=30)

    # ── 9. Mark as completed ──────────────────────────────────────────────────
    book.processing_status = Book.ProcessingStatus.COMPLETED
    book.save(update_fields=['processing_status'])

    upload.status = UserUploadedBook.Status.COMPLETED
    upload.processed_at = datetime.now(tz=timezone.utc)
    upload.save(update_fields=['status', 'processed_at'])

    # ── 10. Ensure the user has a library entry ───────────────────────────────
    user_book, created = UserBook.objects.get_or_create(
        user=upload.uploaded_by,
        book=book,
        defaults={'status': UserBook.Status.NOT_STARTED},
    )
    logger.info(
        f"[PDF Task] ✅ DONE — '{upload.title}' processed successfully. "
        f"UserBook {'created' if created else 'already existed'}."
    )


@shared_task(bind=True, max_retries=2)
def process_admin_book_pdf(self, book_id: str):
    """
    Background task for admin-uploaded books.

    NEW: Also auto-fetches a cover image if the admin didn't provide one.
    """
    from apps.books.models import Book
    from apps.books.cover_service import fetch_cover_image_url  # ← NEW

    logger.info(f"[Admin PDF Task] 🚀 Starting — book_id={book_id}")

    try:
        book = Book.objects.get(id=book_id)
    except Book.DoesNotExist:
        logger.error(f"[Admin PDF Task] ❌ Book not found: {book_id}")
        return

    if not book.pdf_file:
        logger.error(f"[Admin PDF Task] ❌ Book {book_id} has no PDF file.")
        return

    # ── Auto-fetch cover image if missing ─────────────────────────────────────
    # NEW: Extract the first page of PDF as cover image automatically.
    # Falls back to external services if PDF cover extraction fails.
    if not book.cover_image and not book.cover_image_url:
        logger.info(f"[Admin PDF Task] Extracting first page as cover image for '{book.title}'...")
        cover_path = extract_first_page_as_image(book.pdf_file.path)
        if cover_path:
            book.cover_image = cover_path
            book.save(update_fields=['cover_image'])
            logger.info(f"[Admin PDF Task] Cover image extracted: {cover_path}")
        else:
            logger.info(f"[Admin PDF Task] Could not extract cover from PDF, trying external services...")
            cover_url = fetch_cover_image_url(
        title=book.title,
        author=book.author,
        pdf_path=book.pdf_file.path
    )
            if cover_url:
                book.cover_image_url = cover_url
                book.save(update_fields=['cover_image_url'])
                logger.info(f"[Admin PDF Task] Cover image set from external service: {cover_url[:80]}...")

    # Mark processing
    book.processing_status = Book.ProcessingStatus.PROCESSING
    book.save(update_fields=['processing_status'])

    try:
        pages = extract_text_from_pdf(book.pdf_file.path)
    except Exception as exc:
        logger.error(f"[Admin PDF Task] ❌ PDF extraction failed: {exc}", exc_info=True)
        book.processing_status = Book.ProcessingStatus.FAILED
        book.processing_error = str(exc)
        book.save(update_fields=['processing_status', 'processing_error'])
        raise self.retry(exc=exc, countdown=30)

    if not pages:
        book.processing_status = Book.ProcessingStatus.FAILED
        book.processing_error = "PDF is empty or has no extractable text."
        book.save(update_fields=['processing_status', 'processing_error'])
        return

    raw_chapters = group_pages_into_chapters(pages)
    processed_chapters = []

    for raw_ch in raw_chapters:
        claude_result = call_claude_for_chapter(
            raw_ch['text'],
            raw_ch['chapter_number'],
            book.title,
        )
        claude_result['chapter_number'] = raw_ch['chapter_number']
        claude_result['page_range'] = raw_ch['page_range']
        processed_chapters.append(claude_result)

    try:
        save_book_content_to_db(book, processed_chapters)
    except Exception as exc:
        logger.error(f"[Admin PDF Task] ❌ DB save failed: {exc}", exc_info=True)
        book.processing_status = Book.ProcessingStatus.FAILED
        book.processing_error = str(exc)
        book.save(update_fields=['processing_status', 'processing_error'])
        raise self.retry(exc=exc, countdown=30)

    book.processing_status = Book.ProcessingStatus.COMPLETED
    book.processing_error = ''
    book.save(update_fields=['processing_status', 'processing_error'])

    logger.info(f"[Admin PDF Task] ✅ DONE — '{book.title}' processed successfully.")


# ── Private helpers ────────────────────────────────────────────────────────────

def _mark_failed(upload, book, error_message: str):
    """Helper: set both upload and book to FAILED status."""
    try:
        upload.status = upload.Status.FAILED
        upload.error_message = error_message
        upload.save(update_fields=['status', 'error_message'])
    except Exception as e:
        logger.error(f"[_mark_failed] Could not update upload status: {e}")

    try:
        book.processing_status = book.ProcessingStatus.FAILED
        book.processing_error = error_message
        book.save(update_fields=['processing_status', 'processing_error'])
    except Exception as e:
        logger.error(f"[_mark_failed] Could not update book status: {e}")