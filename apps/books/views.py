from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
import logging

logger = logging.getLogger(__name__)

from .models import Book, Chapter, Chunk, Summary, Flashcard, UserUploadedBook, ReadingSchedule
from .serializers import (
    BookListSerializer,
    BookDetailSerializer,
    ChapterSerializer,
    ChunkSerializer,
    SummarySerializer,
    FlashcardSerializer,
    UserUploadSerializer,
    UserUploadStatusSerializer,
    ReadingScheduleSerializer,
)
from .tasks import generate_chapter_metadata_task


class BookListView(APIView):
    """
    GET /books/
    Supports ?search=, ?category=
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(is_published=True)

        search = request.query_params.get('search')
        if search:
            books = books.filter(title__icontains=search) | books.filter(author__icontains=search)

        category = request.query_params.get('category')
        if category:
            books = books.filter(category__iexact=category)

        serializer = BookListSerializer(books, many=True, context={'request': request})
        return Response(serializer.data)


class RecommendedBooksView(APIView):
    """
    GET /books/recommended/
    Returns books marked is_recommended=True, EXCLUDING books the user
    already has in their library.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_book_ids = request.user.user_books.values_list('book_id', flat=True)

        books = Book.objects.filter(
            is_published=True,
            is_recommended=True,
            source=Book.Source.ADMIN,
        ).exclude(
            id__in=user_book_ids
        )

        serializer = BookListSerializer(books, many=True, context={'request': request})
        return Response(serializer.data)


class TrendingBooksView(APIView):
    """GET /books/trending/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(
            is_published=True,
            is_trending=True,
            source=Book.Source.ADMIN,
        ).order_by('badge')
        serializer = BookListSerializer(books, many=True, context={'request': request})
        return Response(serializer.data)


class BookDetailView(APIView):
    """GET /books/{id}/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Lazy AI: trigger book brief via intelligence pipeline if profile exists but brief missing
        try:
            profile = book.intelligence_profile
            if profile and not profile.book_brief:
                from apps.book_intelligence.tasks import generate_book_brief_task
                generate_book_brief_task.delay(str(profile.id), None)
        except Exception:
            pass

        serializer = BookDetailSerializer(book, context={'request': request})
        return Response(serializer.data)


class BookChaptersView(APIView):
    """GET /books/{id}/chapters/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        chapters = book.chapters.all()
        serializer = ChapterSerializer(chapters, many=True, context={'request': request})
        return Response(serializer.data)


class ChapterChunksView(APIView):
    """
    GET /books/{book_id}/chapters/{chapter_id}/chunks/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id, chapter_id):
        try:
            chapter = Chapter.objects.get(id=chapter_id, book_id=book_id)
        except Chapter.DoesNotExist:
            return Response(
                {'error': 'Chapter not found for this book.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Lazy AI: Generate metadata for this chapter and the next one (progressive generation)
        try:
            if not hasattr(chapter, 'summary'):
                generate_chapter_metadata_task.delay(str(chapter.id))
            
            next_chapter = Chapter.objects.filter(
                book_id=book_id, 
                chapter_number=chapter.chapter_number + 1
            ).first()
            if next_chapter and not hasattr(next_chapter, 'summary'):
                generate_chapter_metadata_task.delay(str(next_chapter.id))
        except Exception as e:
            logger.error(f"Failed to queue progressive generation: {e}")

        chunks = chapter.chunks.all()
        serializer = ChunkSerializer(chunks, many=True)
        return Response(serializer.data)


def _extract_summary_content(content: dict, mode: str) -> tuple:
    """Map ChapterIntelligence content dict → (summaryContent, keyTakeaways)."""
    if mode == 'skim':
        return content.get('one_liner', ''), []
    elif mode == 'concept':
        concepts = content.get('concepts', [])
        summary = '; '.join(c.get('name', '') for c in concepts[:3])
        takeaways = [
            f"{c.get('name', '')}: {c.get('description', '')}"
            for c in concepts
        ]
        return summary, takeaways
    elif mode == 'deep':
        return content.get('overview', ''), content.get('key_points', [])
    elif mode == 'exam':
        qa_pairs = content.get('qa_pairs', [])
        summary = f"{len(qa_pairs)} study questions"
        takeaways = [f"Q: {qa.get('question', '')}" for qa in qa_pairs]
        return summary, takeaways
    return '', []


class BookSummariesView(APIView):
    """GET /books/{id}/summaries/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        from apps.book_intelligence.models import ChapterIntelligence
        reading_mode = book.reading_mode or 'deep'
        try:
            profile = book.intelligence_profile
        except Exception:
            return Response([])

        summaries = []
        for ai_ch in profile.ai_chapters.order_by('chapter_number'):
            try:
                intel = ChapterIntelligence.objects.get(
                    ai_chapter=ai_ch, mode=reading_mode
                )
                summary_content, key_takeaways = _extract_summary_content(
                    intel.content or {}, reading_mode
                )
                summaries.append({
                    'id': str(intel.id),
                    'chapterNumber': ai_ch.chapter_number,
                    'title': ai_ch.title,
                    'summaryContent': summary_content,
                    'keyTakeaways': key_takeaways,
                    'isLocked': False,
                })
            except ChapterIntelligence.DoesNotExist:
                pass

        return Response(summaries)


class BookFlashcardsView(APIView):
    """GET /books/{id}/flashcards/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        from apps.book_intelligence.models import ChapterIntelligence
        import uuid
        try:
            profile = book.intelligence_profile
        except Exception:
            return Response([])

        flashcards = []
        for ai_ch in profile.ai_chapters.order_by('chapter_number'):
            try:
                intel = ChapterIntelligence.objects.get(
                    ai_chapter=ai_ch, mode='exam'
                )
                for i, qa in enumerate(intel.content.get('qa_pairs', [])):
                    deterministic_id = str(uuid.uuid5(
                        uuid.UUID(str(intel.id)), str(i)
                    ))
                    flashcards.append({
                        'id': deterministic_id,
                        'bookId': str(book.id),
                        'question': qa.get('question', ''),
                        'answer': qa.get('answer', ''),
                    })
            except ChapterIntelligence.DoesNotExist:
                pass

        return Response(flashcards)


class ChunkSummaryView(APIView):
    """
    GET /books/{id}/chapters/{chapter_id}/chunks/{chunk_id}/summary/
    On-demand page summary. Does a synchronous AI call and returns the summary text.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id, chapter_id, chunk_id):
        try:
            chunk = Chunk.objects.get(id=chunk_id, chapter_id=chapter_id, chapter__book_id=book_id)
        except Chunk.DoesNotExist:
            return Response({'error': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

        from openai import OpenAI
        from django.conf import settings

        api_key = getattr(settings, 'DEEPSEEK_API_KEY', '')
        if not api_key:
            return Response({'error': 'AI not configured.'}, status=status.HTTP_501_NOT_IMPLEMENTED)

        client = OpenAI(api_key=api_key, base_url='https://api.deepseek.com')
        
        prompt = f"""Summarize the following book page in 2-3 concise sentences. Focus on the core idea:

{chunk.text}

Return only the summary text, no markdown."""

        try:
            response = client.chat.completions.create(
                model='deepseek-chat',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=150,
                temperature=0.2,
            )
            summary = response.choices[0].message.content.strip()
            return Response({'summary': summary})
        except Exception as exc:
            logger.error(f"[Page Summary] Failed: {exc}")
            return Response({'error': 'Failed to generate summary.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ── User Upload Views ─────────────────────────────────────────────────────────

class UserBookUploadView(APIView):
    """
    POST /api/v1/books/upload/

    Accepts a PDF from the Flutter AddBookPage.
    Required fields: title, pdf_file, reading_mode, daily_minutes
    Creates UserUploadedBook, triggers Stage 1 (extract + detect chapters).
    Returns upload record with status=PENDING.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = UserUploadSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            upload = serializer.save()
            return Response(
                UserUploadStatusSerializer(upload).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserUploadStatusView(APIView):
    """
    GET /api/v1/books/upload/<upload_id>/status/

    Flutter polls this to track processing progress.
    Returns processingStage for granular status (e.g. 'awaiting_confirm').
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, upload_id):
        try:
            upload = UserUploadedBook.objects.select_related('book').get(
                id=upload_id,
                uploaded_by=request.user,
            )
        except UserUploadedBook.DoesNotExist:
            return Response({'error': 'Upload not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response(UserUploadStatusSerializer(upload).data)


class ReadingScheduleView(APIView):
    """
    GET /api/v1/books/<book_id>/schedule/

    Returns the user's reading schedule for a book.
    Schedule is created after chapter confirmation (Stage 3).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            schedule = ReadingSchedule.objects.select_related('book').get(
                book_id=book_id,
                user=request.user,
            )
        except ReadingSchedule.DoesNotExist:
            return Response(
                {'error': 'No reading schedule found. Complete chapter confirmation first.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ReadingScheduleSerializer(schedule).data)