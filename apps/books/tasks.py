"""
apps/books/tasks.py

KEY FIX: Chunk generation is now deterministic and never relies on Claude
to split text correctly. Claude is only used for title, summary, key takeaways,
and flashcards — all of which are short and reliable. The actual reading chunks
(pages) are always produced by our own sentence-aware word splitter, guaranteeing
that a 17-page chapter always becomes ~17+ readable pages in the app.

PREVIOUS BUG: Claude was asked to produce the chunks array directly.
When the chapter text was long (or Claude was being conservative), it often
returned the entire chapter as a single string in the chunks array, giving
the user 1 page per chapter instead of 15-20.
"""

import re
import json
import logging
from datetime import timezone, datetime
from celery import shared_task
from django.db import transaction
from django.conf import settings

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


def group_pages_into_chapters(pages: list[dict], pages_per_chapter: int = 17) -> list[dict]:
    """
    Group flat PDF pages into logical chapters.

    FIX: Default changed from 15 to 17 pages per chapter to match
    the page ranges already shown in the Flutter UI (Pages 1-17, 18-34 etc.)
    
    If the PDF has fewer pages than pages_per_chapter, they all become chapter 1.
    """
    if not pages:
        return []

    chapters = []
    for i in range(0, len(pages), pages_per_chapter):
        chapter_pages = pages[i:i + pages_per_chapter]
        page_numbers = [p['page_number'] for p in chapter_pages]
        full_text = '\n\n'.join(p['text'] for p in chapter_pages)
        chapters.append({
            'chapter_number': len(chapters) + 1,
            'pages': page_numbers,
            'page_range': f"Pages {page_numbers[0]}–{page_numbers[-1]}",
            'text': full_text,
            'page_count': len(chapter_pages),
        })

    logger.info(f"[PDF] Grouped {len(pages)} pages into {len(chapters)} chapters "
                f"({pages_per_chapter} pages/chapter)")
    return chapters


# ── Claude Integration (title/summary/flashcards only) ────────────────────────

def call_claude_for_metadata(chapter_text: str, chapter_number: int, book_title: str) -> dict:
    """
    Ask Claude ONLY for metadata: title, summary, key takeaways, flashcards.

    IMPORTANT: We do NOT ask Claude to split the text into chunks anymore.
    Chunk splitting is handled deterministically by split_text_into_chunks()
    above, which guarantees the right number of pages every time.

    Claude's job here is purely semantic: understand the chapter and generate
    the study aids. This is a much simpler, more reliable task.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Limit input to avoid token limits — use first 8000 chars for metadata
        preview_text = chapter_text[:8000]
        if len(chapter_text) > 8000:
            preview_text += '\n\n[...chapter continues...]'

        prompt = f"""You are processing Chapter {chapter_number} of "{book_title}".

<chapter_text>
{preview_text}
</chapter_text>

Return ONLY valid JSON with NO markdown fences, NO extra text:
{{
  "title": "Descriptive chapter title (max 60 chars)",
  "summary": "2-3 sentence summary of the main ideas in this chapter",
  "key_takeaways": [
    "Key insight 1 (1 sentence)",
    "Key insight 2 (1 sentence)",
    "Key insight 3 (1 sentence)"
  ],
  "flashcards": [
    {{"question": "A question testing understanding of this chapter", "answer": "A clear concise answer"}},
    {{"question": "Another question", "answer": "Another answer"}},
    {{"question": "Third question", "answer": "Third answer"}}
  ],
  "estimated_read_minutes": {max(5, (len(chapter_text.split()) // 200))}
}}"""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text.strip()
        # Strip any accidental markdown fences
        response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)

        result = json.loads(response_text)
        logger.info(
            f"[Claude] Ch.{chapter_number} metadata: "
            f"title='{result.get('title', '')[:40]}', "
            f"{len(result.get('flashcards', []))} flashcards"
        )
        return result

    except Exception as exc:
        logger.warning(f"[Claude] Ch.{chapter_number} metadata failed ({exc}), using fallback.")
        # Safe fallback — processing continues without AI metadata
        word_count = len(chapter_text.split())
        return {
            "title": f"Chapter {chapter_number}",
            "summary": f"Chapter {chapter_number} content.",
            "key_takeaways": [],
            "flashcards": [],
            "estimated_read_minutes": max(5, word_count // 200),
        }


def process_chapter(raw_chapter: dict, book_title: str) -> dict:
    """
    Process one chapter end-to-end:
    1. Get metadata (title/summary/flashcards) from Claude
    2. Split raw text into chunks deterministically (NEVER rely on Claude for this)
    3. Return a complete chapter dict ready for save_book_content_to_db()

    This function is the core fix. Separating concerns means:
    - Claude handles semantics (what does this chapter mean?)
    - Our code handles structure (how many pages should this chapter have?)
    """
    chapter_text = raw_chapter['text']
    chapter_number = raw_chapter['chapter_number']
    page_count = raw_chapter.get('page_count', 17)

    # Step 1: Get Claude metadata (title, summary, flashcards)
    metadata = call_claude_for_metadata(chapter_text, chapter_number, book_title)

    # Step 2: Deterministic chunk splitting
    # Target: ~3 chunks per page (each chunk ~2 min at 250 words)
    # A 17-page chapter → ~17 chunks minimum, ideally 17-20
    # We use 275 words/chunk so a 17-page chapter (17*275=4675 words) → ~17 chunks
    words_per_chunk = 275
    chunks = split_text_into_chunks(chapter_text, words_per_chunk=words_per_chunk)

    # Safety: if text was very short (e.g. mostly images/scanned PDF),
    # still produce at least 1 chunk with whatever text we have
    if not chunks and chapter_text.strip():
        chunks = [chapter_text.strip()]

    logger.info(
        f"[Process] Ch.{chapter_number} '{metadata.get('title', '')}': "
        f"{len(chapter_text.split())} words → {len(chunks)} chunks "
        f"({page_count} PDF pages)"
    )

    return {
        'chapter_number': chapter_number,
        'page_range': raw_chapter.get('page_range', ''),
        'title': metadata.get('title', f'Chapter {chapter_number}'),
        'summary': metadata.get('summary', ''),
        'key_takeaways': metadata.get('key_takeaways', []),
        'flashcards': metadata.get('flashcards', []),
        'estimated_read_minutes': metadata.get('estimated_read_minutes', len(chunks) * 2),
        # CHUNKS come from our deterministic splitter, NOT from Claude
        'chunks': chunks,
    }


# ── Database Writer ────────────────────────────────────────────────────────────

def save_book_content_to_db(book, chapters_data: list[dict]):
    """
    Wipe existing chapters/flashcards for this book and write fresh ones.
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

            chunks = chapter_data.get('chunks', [])
            if not chunks:
                logger.warning(
                    f"[DB] Ch.{chapter_data['chapter_number']} has no chunks — "
                    "skipping chunk creation"
                )

            for i, chunk_text in enumerate(chunks):
                chunk_text = chunk_text.strip()
                if not chunk_text:
                    continue
                word_count = len(chunk_text.split())
                # Estimate reading time: average reader does ~200 words/min
                estimated_minutes = max(1, round(word_count / 200))
                Chunk.objects.create(
                    chapter=chapter,
                    chunk_index=i,
                    text=chunk_text,
                    estimated_minutes=estimated_minutes,
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
                q = (fc.get('question') or '').strip()
                a = (fc.get('answer') or '').strip()
                if q and a:
                    Flashcard.objects.create(book=book, question=q, answer=a)
                    total_flashcards += 1

        book.total_chapters = len(chapters_data)
        book.flashcards_count = total_flashcards
        book.save(update_fields=['total_chapters', 'flashcards_count'])

    total_chunks = sum(len(c.get('chunks', [])) for c in chapters_data)
    logger.info(
        f"[DB] Saved {len(chapters_data)} chapters, "
        f"{total_chunks} total chunks, "
        f"{total_flashcards} flashcards for '{book.title}'"
    )


# ── Celery Tasks ───────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=2)
def process_user_uploaded_book(self, upload_id: str):
    """
    Background task: read the PDF, process each chapter, persist results.
    """
    from apps.books.models import Book, UserUploadedBook
    from apps.library.models import UserBook
    from apps.books.cover_service import fetch_cover_image_url

    logger.info(f"[PDF Task] 🚀 Starting — upload_id={upload_id}")

    # ── 1. Fetch upload record ─────────────────────────────────────────────────
    try:
        upload = UserUploadedBook.objects.select_related(
            'uploaded_by', 'book'
        ).get(id=upload_id)
    except UserUploadedBook.DoesNotExist:
        logger.error(f"[PDF Task] ❌ Upload not found: {upload_id}")
        return

    # ── 2. Ensure a Book record exists ─────────────────────────────────────────
    if upload.book is None:
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
    else:
        book = upload.book

    # ── 3. Auto-fetch cover image ──────────────────────────────────────────────
    if not book.cover_image and not book.cover_image_url:
        cover_path = extract_first_page_as_image(upload.pdf_file.path)
        if cover_path:
            book.cover_image = cover_path
            book.save(update_fields=['cover_image'])
            logger.info(f"[PDF Task] ✅ Cover extracted: {cover_path}")

    # ── 4. Mark as processing ──────────────────────────────────────────────────
    try:
        upload.status = UserUploadedBook.Status.PROCESSING
        upload.save(update_fields=['status'])
        book.processing_status = Book.ProcessingStatus.PROCESSING
        book.save(update_fields=['processing_status'])
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)

    # ── 5. Extract PDF text ────────────────────────────────────────────────────
    try:
        pages = extract_text_from_pdf(upload.pdf_file.path)
    except Exception as exc:
        logger.error(f"[PDF Task] ❌ PDF extraction failed: {exc}", exc_info=True)
        _mark_failed(upload, book, str(exc))
        raise self.retry(exc=exc, countdown=30)

    if not pages:
        _mark_failed(upload, book, "PDF is empty or has no extractable text.")
        return

    logger.info(f"[PDF Task] Extracted {len(pages)} pages")

    # ── 6. Group pages into chapters ───────────────────────────────────────────
    raw_chapters = group_pages_into_chapters(pages, pages_per_chapter=17)

    # ── 7. Process each chapter (Claude metadata + deterministic chunks) ────────
    processed_chapters = []
    for raw_ch in raw_chapters:
        chapter_result = process_chapter(raw_ch, upload.title)
        processed_chapters.append(chapter_result)

    # ── 8. Save to database ────────────────────────────────────────────────────
    try:
        save_book_content_to_db(book, processed_chapters)
    except Exception as exc:
        logger.error(f"[PDF Task] ❌ DB save failed: {exc}", exc_info=True)
        _mark_failed(upload, book, str(exc))
        raise self.retry(exc=exc, countdown=30)

    # ── 9. Mark as completed ───────────────────────────────────────────────────
    book.processing_status = Book.ProcessingStatus.COMPLETED
    book.save(update_fields=['processing_status'])

    upload.status = UserUploadedBook.Status.COMPLETED
    upload.processed_at = datetime.now(tz=timezone.utc)
    upload.save(update_fields=['status', 'processed_at'])

    # ── 10. Ensure library entry exists ───────────────────────────────────────
    user_book, created = UserBook.objects.get_or_create(
        user=upload.uploaded_by,
        book=book,
        defaults={'status': UserBook.Status.NOT_STARTED},
    )

    total_chunks = sum(len(c.get('chunks', [])) for c in processed_chapters)
    logger.info(
        f"[PDF Task] ✅ DONE — '{upload.title}': "
        f"{len(processed_chapters)} chapters, {total_chunks} chunks. "
        f"UserBook {'created' if created else 'already existed'}."
    )


@shared_task(bind=True, max_retries=2)
def process_admin_book_pdf(self, book_id: str):
    """
    Background task for admin-uploaded books.
    Uses the same process_chapter() function for consistent chunk generation.
    """
    from apps.books.models import Book
    from apps.books.cover_service import fetch_cover_image_url

    logger.info(f"[Admin PDF Task] 🚀 Starting — book_id={book_id}")

    try:
        book = Book.objects.get(id=book_id)
    except Book.DoesNotExist:
        logger.error(f"[Admin PDF Task] ❌ Book not found: {book_id}")
        return

    if not book.pdf_file:
        logger.error(f"[Admin PDF Task] ❌ Book {book_id} has no PDF file.")
        return

    # Auto-fetch cover image if missing
    if not book.cover_image and not book.cover_image_url:
        cover_path = extract_first_page_as_image(book.pdf_file.path)
        if cover_path:
            book.cover_image = cover_path
            book.save(update_fields=['cover_image'])
        else:
            cover_url = fetch_cover_image_url(
                title=book.title,
                author=book.author,
                pdf_path=book.pdf_file.path
            )
            if cover_url:
                book.cover_image_url = cover_url
                book.save(update_fields=['cover_image_url'])

    book.processing_status = Book.ProcessingStatus.PROCESSING
    book.save(update_fields=['processing_status'])

    # Extract PDF pages
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

    # Group and process chapters
    raw_chapters = group_pages_into_chapters(pages, pages_per_chapter=17)
    processed_chapters = []

    for raw_ch in raw_chapters:
        chapter_result = process_chapter(raw_ch, book.title)
        processed_chapters.append(chapter_result)

    # Save to database
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

    total_chunks = sum(len(c.get('chunks', [])) for c in processed_chapters)
    logger.info(
        f"[Admin PDF Task] ✅ DONE — '{book.title}': "
        f"{len(processed_chapters)} chapters, {total_chunks} total chunks."
    )


# ── Private helpers ────────────────────────────────────────────────────────────

def _mark_failed(upload, book, error_message: str):
    """Set both upload and book to FAILED status."""
    try:
        upload.status = upload.Status.FAILED
        upload.error_message = error_message
        upload.save(update_fields=['status', 'error_message'])
    except Exception as e:
        logger.error(f"[_mark_failed] Could not update upload: {e}")

    try:
        book.processing_status = book.ProcessingStatus.FAILED
        book.processing_error = error_message
        book.save(update_fields=['processing_status', 'processing_error'])
    except Exception as e:
        logger.error(f"[_mark_failed] Could not update book: {e}")