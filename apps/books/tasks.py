"""
apps/books/tasks.py

Background tasks for PDF processing.

This file is the core of the "AI chunking" feature.
Celery picks up tasks from this file and runs them in the background
while Django continues serving API requests.

WHAT HAPPENS when a PDF is uploaded:
1. Admin uploads PDF in Django admin panel  →  process_admin_book_pdf(book_id) fires
2. User uploads PDF from Flutter app       →  process_user_uploaded_book(upload_id) fires
3. Task extracts text from PDF using PyMuPDF (fitz)
4. Text is split into logical chapters (by headings or page groups)
5. Each chapter's text is sent to Claude to:
   - Generate a short chapter title
   - Split into readable chunks (~300 words each, ~2 min read)
   - Write a chapter summary
   - Extract 3-5 key takeaways
   - Generate 2-3 flashcard Q&A pairs
6. All of this is saved to the database
7. Status is updated to COMPLETED

HOW TO RUN THE WORKER:
    celery -A config worker --loglevel=info
"""

import re
import json
import logging
from datetime import timezone, datetime
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Extract text from a PDF file using PyMuPDF (fitz).

    Returns a list of page dicts:
        [{'page_number': 1, 'text': '...'}, ...]

    Why page-by-page?  We need to know page numbers so we can set
    meaningful page ranges on chapters (e.g. "Pages 1-15").
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError(
            "PyMuPDF is not installed. Run: pip install PyMuPDF"
        )

    pages = []
    doc = fitz.open(pdf_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        if text:  # skip blank pages
            pages.append({
                'page_number': page_num + 1,
                'text': text,
            })

    doc.close()
    return pages


def group_pages_into_chapters(pages: list[dict], pages_per_chapter: int = 15) -> list[dict]:
    """
    Group pages into chapters.

    Simple strategy: group every N pages together.
    This works well for books that don't have clear heading markers.

    Returns a list of chapter dicts:
        [{'chapter_number': 1, 'pages': [1,2,...], 'text': '...combined text...'}, ...]
    """
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
    """
    Send chapter text to Claude and get back structured data:
    - title
    - chunks (list of text strings)
    - summary
    - key_takeaways
    - flashcards

    Uses claude-haiku-4-5 (fastest and cheapest model) for processing.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Truncate text to avoid hitting token limits
    # ~4 chars per token, 8000 tokens max for safety
    max_chars = 32_000
    if len(chapter_text) > max_chars:
        chapter_text = chapter_text[:max_chars] + '\n\n[...text truncated...]'

    prompt = f"""You are processing Chapter {chapter_number} of the book "{book_title}".

Here is the chapter text:
<chapter_text>
{chapter_text}
</chapter_text>

Please analyze this chapter and return a JSON object with EXACTLY this structure (no other text):

{{
  "title": "A descriptive title for this chapter (max 60 characters)",
  "chunks": [
    "First chunk of text (~200-300 words, suitable for 2 minutes of reading)",
    "Second chunk of text...",
    "..."
  ],
  "summary": "A 2-3 sentence summary of what this chapter covers",
  "key_takeaways": [
    "First key insight from this chapter",
    "Second key insight",
    "Third key insight"
  ],
  "flashcards": [
    {{"question": "A question testing understanding of a key concept", "answer": "The clear, concise answer"}},
    {{"question": "Another question", "answer": "Another answer"}}
  ],
  "estimated_read_minutes": 15
}}

Rules:
- chunks: Split the text into 3-8 natural reading segments. Each chunk should be self-contained and readable in ~2 minutes.
- key_takeaways: 3-5 bullet points, each max 1 sentence
- flashcards: 2-3 Q&A pairs testing the most important concepts
- Return ONLY valid JSON, no explanation text before or after"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if Claude added them
    if response_text.startswith('```'):
        response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)

    return json.loads(response_text)


def save_book_content_to_db(book, chapters_data: list[dict]):
    """
    Save all processed chapter/chunk/summary/flashcard data to the database.

    This runs inside the Celery task after Claude processing is complete.
    """
    from apps.books.models import Chapter, Chunk, Summary, Flashcard

    # Clear any existing content (in case of reprocessing)
    book.chapters.all().delete()
    book.flashcards.all().delete()

    total_flashcards = 0

    for chapter_data in chapters_data:
        # Create the Chapter
        chapter = Chapter.objects.create(
            book=book,
            chapter_number=chapter_data['chapter_number'],
            title=chapter_data.get('title', f"Chapter {chapter_data['chapter_number']}"),
            page_range=chapter_data.get('page_range', ''),
            duration_in_minutes=chapter_data.get('estimated_read_minutes', 15),
            is_locked=False,
        )

        # Create Chunks
        chunks = chapter_data.get('chunks', [])
        for i, chunk_text in enumerate(chunks):
            if chunk_text.strip():
                # Estimate reading time: ~200 words per minute
                word_count = len(chunk_text.split())
                estimated_minutes = max(1, round(word_count / 200))

                Chunk.objects.create(
                    chapter=chapter,
                    chunk_index=i,
                    text=chunk_text.strip(),
                    estimated_minutes=estimated_minutes,
                )

        # Create Summary (if we have one)
        summary_text = chapter_data.get('summary', '')
        key_takeaways = chapter_data.get('key_takeaways', [])
        if summary_text:
            Summary.objects.create(
                chapter=chapter,
                title=chapter.title,
                summary_content=summary_text,
                key_takeaways=key_takeaways,
                is_locked=False,
            )

        # Create Flashcards for the whole book
        for fc in chapter_data.get('flashcards', []):
            if fc.get('question') and fc.get('answer'):
                Flashcard.objects.create(
                    book=book,
                    question=fc['question'],
                    answer=fc['answer'],
                )
                total_flashcards += 1

    # Update book metadata
    book.total_chapters = len(chapters_data)
    book.flashcards_count = total_flashcards
    book.save(update_fields=['total_chapters', 'flashcards_count'])


# ── Tasks ──────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=2)
def process_admin_book_pdf(self, book_id: str):
    """
    Process a PDF uploaded by the admin.

    Triggered automatically when admin saves a Book with a pdf_file.
    On completion, the book's chapters/chunks are created and
    is_recommended is set to True so it appears on the home screen.

    Args:
        book_id: UUID string of the Book to process
    """
    from apps.books.models import Book

    logger.info(f"[PDF Task] Starting admin book processing: {book_id}")

    try:
        book = Book.objects.get(id=book_id)
    except Book.DoesNotExist:
        logger.error(f"[PDF Task] Book {book_id} not found")
        return

    if not book.pdf_file:
        logger.error(f"[PDF Task] Book {book_id} has no PDF file")
        return

    try:
        # Mark as processing
        book.processing_status = Book.ProcessingStatus.PROCESSING
        book.save(update_fields=['processing_status'])

        # Step 1: Extract text from PDF
        logger.info(f"[PDF Task] Extracting text from PDF for book: {book.title}")
        pages = extract_text_from_pdf(book.pdf_file.path)

        if not pages:
            raise ValueError("PDF appears to be empty or contains no readable text")

        # Step 2: Group pages into chapters
        # Use 15 pages per chapter as default
        logger.info(f"[PDF Task] Grouping {len(pages)} pages into chapters")
        chapters = group_pages_into_chapters(pages, pages_per_chapter=15)

        # Step 3: Process each chapter with Claude
        processed_chapters = []
        for chapter in chapters:
            logger.info(
                f"[PDF Task] Processing chapter {chapter['chapter_number']}/{len(chapters)} "
                f"with Claude for book: {book.title}"
            )
            try:
                claude_result = call_claude_for_chapter(
                    chapter_text=chapter['text'],
                    chapter_number=chapter['chapter_number'],
                    book_title=book.title,
                )
                # Merge page range info into Claude's result
                claude_result['chapter_number'] = chapter['chapter_number']
                claude_result['page_range'] = chapter['page_range']
                processed_chapters.append(claude_result)

            except Exception as claude_error:
                logger.warning(
                    f"[PDF Task] Claude failed for chapter {chapter['chapter_number']}: {claude_error}. "
                    f"Falling back to basic chunking."
                )
                # Fallback: split text into ~300-word chunks without AI
                words = chapter['text'].split()
                chunks = []
                chunk_size = 300
                for i in range(0, len(words), chunk_size):
                    chunk_words = words[i:i + chunk_size]
                    chunks.append(' '.join(chunk_words))

                processed_chapters.append({
                    'chapter_number': chapter['chapter_number'],
                    'title': f"Chapter {chapter['chapter_number']}",
                    'page_range': chapter['page_range'],
                    'chunks': chunks,
                    'summary': '',
                    'key_takeaways': [],
                    'flashcards': [],
                    'estimated_read_minutes': len(words) // 200,
                })

        # Step 4: Save everything to DB
        logger.info(f"[PDF Task] Saving {len(processed_chapters)} chapters to DB for book: {book.title}")
        save_book_content_to_db(book, processed_chapters)

        # Step 5: Mark as completed and publish
        book.processing_status = Book.ProcessingStatus.COMPLETED
        book.is_published = True
        book.is_recommended = True  # Show in recommended section
        book.save(update_fields=['processing_status', 'is_published', 'is_recommended'])

        logger.info(f"[PDF Task] ✅ Successfully processed admin book: {book.title}")

    except Exception as exc:
        logger.error(f"[PDF Task] ❌ Failed to process book {book_id}: {exc}", exc_info=True)
        book.processing_status = Book.ProcessingStatus.FAILED
        book.processing_error = str(exc)
        book.save(update_fields=['processing_status', 'processing_error'])

        # Retry up to 2 times with a 60-second delay
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=2)
def process_user_uploaded_book(self, upload_id: str):
    """
    Process a PDF uploaded by a user from the Flutter app.

    Flow:
    1. Creates a Book record linked to the UserUploadedBook
    2. Processes the PDF (same pipeline as admin)
    3. Creates a UserBook so the book appears in the user's library
    4. Does NOT set is_recommended (user uploads are private)

    Args:
        upload_id: UUID string of the UserUploadedBook to process
    """
    from apps.books.models import Book, UserUploadedBook
    from apps.library.models import UserBook

    logger.info(f"[PDF Task] Starting user upload processing: {upload_id}")

    try:
        upload = UserUploadedBook.objects.select_related('uploaded_by').get(id=upload_id)
    except UserUploadedBook.DoesNotExist:
        logger.error(f"[PDF Task] UserUploadedBook {upload_id} not found")
        return

    try:
        # Mark as processing
        upload.status = UserUploadedBook.Status.PROCESSING
        upload.save(update_fields=['status'])

        # Step 1: Create the Book record
        book = Book.objects.create(
            title=upload.title,
            author=upload.author or 'Unknown Author',
            category='Personal Library',
            description=f'Uploaded by {upload.uploaded_by.full_name or upload.uploaded_by.email}',
            source=Book.Source.USER_UPLOAD,
            processing_status=Book.ProcessingStatus.PROCESSING,
            is_published=True,
            is_recommended=False,   # User uploads are NOT shown globally
        )

        # Link the upload to the book
        upload.book = book
        upload.save(update_fields=['book'])

        # Step 2: Extract text
        logger.info(f"[PDF Task] Extracting text from user PDF: {upload.title}")
        pages = extract_text_from_pdf(upload.pdf_file.path)

        if not pages:
            raise ValueError("PDF appears to be empty or contains no readable text")

        # Step 3: Group into chapters
        chapters = group_pages_into_chapters(pages, pages_per_chapter=15)

        # Step 4: Process with Claude
        processed_chapters = []
        for chapter in chapters:
            logger.info(
                f"[PDF Task] Processing user chapter {chapter['chapter_number']}/{len(chapters)}"
            )
            try:
                claude_result = call_claude_for_chapter(
                    chapter_text=chapter['text'],
                    chapter_number=chapter['chapter_number'],
                    book_title=upload.title,
                )
                claude_result['chapter_number'] = chapter['chapter_number']
                claude_result['page_range'] = chapter['page_range']
                processed_chapters.append(claude_result)

            except Exception as claude_error:
                logger.warning(f"[PDF Task] Claude failed, using basic chunking: {claude_error}")
                words = chapter['text'].split()
                chunks = [
                    ' '.join(words[i:i + 300])
                    for i in range(0, len(words), 300)
                ]
                processed_chapters.append({
                    'chapter_number': chapter['chapter_number'],
                    'title': f"Chapter {chapter['chapter_number']}",
                    'page_range': chapter['page_range'],
                    'chunks': chunks,
                    'summary': '',
                    'key_takeaways': [],
                    'flashcards': [],
                    'estimated_read_minutes': len(words) // 200,
                })

        # Step 5: Save to DB
        save_book_content_to_db(book, processed_chapters)
        book.processing_status = Book.ProcessingStatus.COMPLETED
        book.save(update_fields=['processing_status'])

        # Step 6: Add to user's library automatically
        UserBook.objects.get_or_create(
            user=upload.uploaded_by,
            book=book,
            defaults={'status': UserBook.Status.NOT_STARTED}
        )

        # Step 7: Mark upload as done
        upload.status = UserUploadedBook.Status.COMPLETED
        upload.processed_at = datetime.now(tz=timezone.utc)
        upload.save(update_fields=['status', 'processed_at'])

        logger.info(f"[PDF Task] ✅ Successfully processed user upload: {upload.title}")

    except Exception as exc:
        logger.error(f"[PDF Task] ❌ Failed upload {upload_id}: {exc}", exc_info=True)

        upload.status = UserUploadedBook.Status.FAILED
        upload.error_message = str(exc)
        upload.save(update_fields=['status', 'error_message'])

        # Also update book status if it was created
        if upload.book:
            upload.book.processing_status = Book.ProcessingStatus.FAILED
            upload.book.processing_error = str(exc)
            upload.book.save(update_fields=['processing_status', 'processing_error'])

        raise self.retry(exc=exc, countdown=60)