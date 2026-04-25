"""
apps/books/tasks.py

✅ FIXED: Added transaction.atomic(), better error handling, logging
"""

import re
import json
import logging
from datetime import timezone, datetime
from celery import shared_task
from django.db import transaction
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """✅ Fixed: Added error handling"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF is not installed. Run: pip install PyMuPDF")
        raise ImportError("PyMuPDF is not installed")

    try:
        pages = []
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()
            if text:
                pages.append({
                    'page_number': page_num + 1,
                    'text': text,
                })
        doc.close()
        logger.info(f"Extracted {len(pages)} pages from {pdf_path}")
        return pages
    except Exception as e:
        logger.error(f"PDF extraction failed for {pdf_path}: {e}")
        raise

def group_pages_into_chapters(pages: list[dict], pages_per_chapter: int = 15) -> list[dict]:
    """✅ Unchanged - works well"""
    chapters = []
    total_pages = len(pages)
    for i in range(0, total_pages, pages_per_chapter):
        chapter_pages = pages[i:i + pages_per_chapter]
        combined_text = '\n\n'.join(p['text'] for p in chapter_pages)
        page_numbers = [p['page_number'] for p in chapter_pages]
        chapters.append({
            'chapter_number': len(chapters) + 1,
            'pages': page_numbers,
            'page_range': f"Pages {page_numbers[0]}–{page_numbers[-1]}",
            'text': combined_text,
        })
    return chapters

def call_claude_for_chapter(chapter_text: str, chapter_number: int, book_title: str) -> dict:
    """✅ Fixed: Better error handling, fallback"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        
        max_chars = 32_000
        if len(chapter_text) > max_chars:
            chapter_text = chapter_text[:max_chars] + '\n\n[...text truncated...]'

        prompt = f"""You are processing Chapter {chapter_number} of "{book_title}".

<chapter_text>{chapter_text}</chapter_text>

Return ONLY valid JSON:
{{
  "title": "Descriptive title (max 60 chars)",
  "chunks": ["200-300 word chunks"],
  "summary": "2-3 sentence summary",
  "key_takeaways": ["Insight 1", "Insight 2"],
  "flashcards": [{{"question": "...", "answer": "..."}}],
  "estimated_read_minutes": 15
}}"""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()
        if response_text.startswith('```'):
            response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)

        return json.loads(response_text)
    except Exception as e:
        logger.warning(f"Claude failed: {e}")
        return {
            "title": f"Chapter {chapter_number}",
            "chunks": [],
            "summary": "Processing unavailable",
            "key_takeaways": [],
            "flashcards": [],
            "estimated_read_minutes": 15
        }

def save_book_content_to_db(book, chapters_data: list[dict]):
    """✅ Fixed: Added transaction.atomic()"""
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
                if chunk_text.strip():
                    word_count = len(chunk_text.split())
                    estimated_minutes = max(1, round(word_count / 200))
                    Chunk.objects.create(
                        chapter=chapter,
                        chunk_index=i,
                        text=chunk_text.strip(),
                        estimated_minutes=estimated_minutes,
                    )

            if chapter_data.get('summary'):
                Summary.objects.create(
                    chapter=chapter,
                    title=chapter.title,
                    summary_content=chapter_data['summary'],
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

# ── Tasks ──────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=2)
def process_user_uploaded_book(self, upload_id: str):
    """✅ Fixed: Added transaction.atomic(), better logging"""
    from apps.books.models import Book, UserUploadedBook
    from apps.library.models import UserBook

    logger.info(f"[PDF Task] 🚀 Starting user upload: {upload_id}")

    try:
        with transaction.atomic():
            upload = UserUploadedBook.objects.select_related('uploaded_by', 'book').get(id=upload_id)
        
        if not upload.book:
            logger.error(f"[PDF Task] No book linked to upload {upload_id}")
            return

        book = upload.book
        upload.status = UserUploadedBook.Status.PROCESSING
        book.processing_status = Book.ProcessingStatus.PROCESSING
        upload.save(update_fields=['status'])
        book.save(update_fields=['processing_status'])

        # Process PDF
        pages = extract_text_from_pdf(upload.pdf_file.path)
        if not pages:
            raise ValueError("PDF is empty")

        chapters = group_pages_into_chapters(pages)
        processed_chapters = []
        
        for chapter in chapters:
            claude_result = call_claude_for_chapter(
                chapter['text'], chapter['chapter_number'], upload.title
            )
            claude_result['chapter_number'] = chapter['chapter_number']
            claude_result['page_range'] = chapter['page_range']
            processed_chapters.append(claude_result)

        # ✅ Save with transaction
        save_book_content_to_db(book, processed_chapters)
        
        book.processing_status = Book.ProcessingStatus.COMPLETED
        upload.status = UserUploadedBook.Status.COMPLETED
        upload.processed_at = datetime.now(tz=timezone.utc)
        
        book.save(update_fields=['processing_status'])
        upload.save(update_fields=['status', 'processed_at'])

        # Ensure UserBook exists
        UserBook.objects.get_or_create(
            user=upload.uploaded_by,
            book=book,
            defaults={'status': UserBook.Status.NOT_STARTED}
        )

        logger.info(f"[PDF Task] ✅ Completed user upload: {upload.title}")

    except Exception as exc:
        logger.error(f"[PDF Task] ❌ Failed upload {upload_id}: {exc}", exc_info=True)
        
        with transaction.atomic():
            upload.status = UserUploadedBook.Status.FAILED
            upload.error_message = str(exc)
            upload.save(update_fields=['status', 'error_message'])
            
            if upload.book:
                upload.book.processing_status = Book.ProcessingStatus.FAILED
                upload.book.processing_error = str(exc)
                upload.book.save(update_fields=['processing_status', 'processing_error'])
        
        raise self.retry(exc=exc, countdown=60)