"""
apps/book_intelligence/views.py

All API views for Book Intelligence Agent.
Base URL: /api/v1/intelligence/

Endpoints:
  POST  books/<book_id>/analyze/                    — trigger analysis
  GET   books/<book_id>/status/                     — check intelligence status
  GET   books/<book_id>/brief/                      — get/generate Book Brief
  GET   books/<book_id>/chapters/                   — AI chapter structure
  PATCH books/<book_id>/chapters/<ch_id>/           — user edits chapter
  GET   books/<book_id>/chapters/<ch_id>/summary/   — chapter in selected mode
  POST  books/<book_id>/qa/                         — ask a question
  GET   books/<book_id>/qa/history/                 — Q&A history
  GET   books/<book_id>/notifications/today/        — today's 4 pieces
  POST  books/<book_id>/notifications/generate/     — trigger notification generation
"""

import logging
from datetime import date

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.books.models import Book
from .models import (
    BookIntelligenceProfile,
    BookIntelligenceChapter,
    ChapterIntelligence,
    NotificationContent,
    QAConversation,
    QAMessage,
)
from .serializers import (
    BookIntelligenceProfileSerializer,
    BookIntelligenceChapterSerializer,
    BookIntelligenceChapterUpdateSerializer,
    ChapterIntelligenceSerializer,
    BookBriefSerializer,
    NotificationContentSerializer,
    QAConversationSerializer,
    QAMessageSerializer,
    AskQuestionSerializer,
)
from .tasks import (
    classify_and_structure_book,
    generate_book_brief_task,
    generate_chapter_intelligence_task,
    generate_daily_notifications_task,
)
from apps.books.tasks import task_build_reading_schedule

logger = logging.getLogger(__name__)


def _get_book_or_404(book_id) -> tuple:
    """Returns (book, Response|None). If Response is not None, return it immediately."""
    try:
        return Book.objects.get(id=book_id, is_published=True), None
    except Book.DoesNotExist:
        return None, Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)


def _get_profile_or_404(book) -> tuple:
    """Returns (profile, Response|None)."""
    try:
        return book.intelligence_profile, None
    except BookIntelligenceProfile.DoesNotExist:
        return None, Response(
            {'error': 'Intelligence profile not ready. Trigger /analyze/ first.'},
            status=status.HTTP_404_NOT_FOUND,
        )


# ── 1. Trigger Analysis ───────────────────────────────────────────────────────

class AnalyzeBookView(APIView):
    """
    POST /api/v1/intelligence/books/<book_id>/analyze/

    Triggers the full intelligence pipeline:
    classify → structure → build RAG embeddings

    Safe to call multiple times — skips if already READY.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, book_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        if book.processing_status != 'completed':
            return Response(
                {'error': 'Book PDF is still being processed. Wait for processing to complete first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already being processed
        try:
            profile = book.intelligence_profile
            if profile.status == BookIntelligenceProfile.Status.READY:
                return Response({
                    'message': 'Intelligence already ready.',
                    'status': profile.status,
                    'profile_id': str(profile.id),
                })
            if profile.status in [
                BookIntelligenceProfile.Status.CLASSIFYING,
                BookIntelligenceProfile.Status.STRUCTURING,
                BookIntelligenceProfile.Status.EMBEDDING,
            ]:
                return Response({
                    'message': 'Intelligence pipeline already running.',
                    'status': profile.status,
                    'profile_id': str(profile.id),
                })
        except BookIntelligenceProfile.DoesNotExist:
            pass

        # Queue the task
        classify_and_structure_book.delay(str(book_id))

        return Response({
            'message': 'Intelligence pipeline started.',
            'book_id': str(book_id),
        }, status=status.HTTP_202_ACCEPTED)


# ── 2. Status Check ───────────────────────────────────────────────────────────

class IntelligenceStatusView(APIView):
    """GET /api/v1/intelligence/books/<book_id>/status/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        try:
            profile = book.intelligence_profile
            return Response({
                'status': profile.status,
                'book_type': profile.book_type,
                'detected_language': profile.detected_language,
                'complexity_level': profile.complexity_level,
                'embeddings_built': profile.embeddings_built,
                'brief_ready': bool(profile.book_brief),
                'chapters_count': profile.ai_chapters.count(),
                'error_message': profile.error_message or None,
            })
        except BookIntelligenceProfile.DoesNotExist:
            return Response({'status': 'not_started', 'brief_ready': False})


# ── 3. Book Brief ─────────────────────────────────────────────────────────────

class BookBriefView(APIView):
    """
    GET /api/v1/intelligence/books/<book_id>/brief/

    Returns cached Book Brief. If not generated yet, triggers generation
    and returns 202 with a retry hint.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        profile, err = _get_profile_or_404(book)
        if err:
            return err

        if profile.book_brief:
            return Response({
                'ready': True,
                'brief': profile.book_brief,
                'generated_at': profile.brief_generated_at,
            })

        # Not generated yet — trigger async generation
        generate_book_brief_task.delay(str(profile.id))

        return Response({
            'ready': False,
            'message': 'Book Brief is being generated. Poll this endpoint again in 10-15 seconds.',
        }, status=status.HTTP_202_ACCEPTED)


# ── 4. AI Chapters ────────────────────────────────────────────────────────────

class AIChaptersView(APIView):
    """GET /api/v1/intelligence/books/<book_id>/chapters/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        profile, err = _get_profile_or_404(book)
        if err:
            return err

        chapters = profile.ai_chapters.all()
        serializer = BookIntelligenceChapterSerializer(chapters, many=True)
        return Response(serializer.data)


class AIChapterDetailView(APIView):
    """PATCH /api/v1/intelligence/books/<book_id>/chapters/<chapter_id>/"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, book_id, chapter_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        try:
            chapter = BookIntelligenceChapter.objects.get(
                id=chapter_id, profile__book=book
            )
        except BookIntelligenceChapter.DoesNotExist:
            return Response({'error': 'Chapter not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = BookIntelligenceChapterUpdateSerializer(
            chapter, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(BookIntelligenceChapterSerializer(chapter).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── 5. Chapter Summary by Mode ────────────────────────────────────────────────

class ChapterSummaryByModeView(APIView):
    """
    GET /api/v1/intelligence/books/<book_id>/chapters/<chapter_id>/summary/?mode=skim|concept|deep|exam

    Returns cached chapter summary for the given mode.
    If not cached, triggers async generation and returns 202.
    """
    permission_classes = [IsAuthenticated]

    VALID_MODES = {'skim', 'concept', 'deep', 'exam'}

    def get(self, request, book_id, chapter_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        mode = request.query_params.get('mode', 'deep')
        if mode not in self.VALID_MODES:
            return Response(
                {'error': f'Invalid mode. Choose from: {", ".join(self.VALID_MODES)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ai_chapter = BookIntelligenceChapter.objects.get(
                id=chapter_id, profile__book=book
            )
        except BookIntelligenceChapter.DoesNotExist:
            return Response({'error': 'Chapter not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            intelligence = ChapterIntelligence.objects.get(
                ai_chapter=ai_chapter, mode=mode
            )
            return Response({
                'ready': True,
                'mode': mode,
                'chapter_title': ai_chapter.title,
                'chapter_number': ai_chapter.chapter_number,
                'content': intelligence.content,
                'generated_at': intelligence.generated_at,
            })
        except ChapterIntelligence.DoesNotExist:
            # Trigger async generation
            generate_chapter_intelligence_task.delay(str(ai_chapter.id), mode)
            return Response({
                'ready': False,
                'mode': mode,
                'message': f'{mode.capitalize()} summary is being generated. Poll again in 10-15 seconds.',
            }, status=status.HTTP_202_ACCEPTED)


# ── 6. Q&A (Ask Your Book) ────────────────────────────────────────────────────

class AskYourBookView(APIView):
    """
    POST /api/v1/intelligence/books/<book_id>/qa/

    Body: {"question": "..."}
    Returns: {"answer": "...", "source_pages": [...]}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, book_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        profile, err = _get_profile_or_404(book)
        if err:
            return err

        serializer = AskQuestionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question = serializer.validated_data['question']

        if not profile.embeddings_built:
            return Response(
                {'error': 'RAG index not ready yet. Check /status/ for progress.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .rag_engine import find_relevant_chunks
        from .ai_client import answer_question_with_context

        # Find relevant chunks
        relevant = find_relevant_chunks(
            profile_id=str(profile.id),
            question=question,
            top_k=3,
        )

        if not relevant:
            return Response({
                'answer': "I couldn't find relevant content in the book for your question.",
                'source_pages': [],
            })

        context_chunks = [r['text'] for r in relevant]
        source_pages = list({r['page_number'] for r in relevant})

        # Get last 3 conversation exchanges for context
        history = []
        try:
            conv = QAConversation.objects.get(user=request.user, profile=profile)
            history = list(
                conv.messages.order_by('-created_at')[:3].values('question', 'answer')
            )
        except QAConversation.DoesNotExist:
            pass

        # Get grounded answer from DeepSeek
        answer = answer_question_with_context(
            book_title=book.title,
            question=question,
            context_chunks=context_chunks,
            conversation_history=history,
        )

        # Save to conversation history
        conversation, _ = QAConversation.objects.get_or_create(
            user=request.user,
            profile=profile,
        )
        message = QAMessage.objects.create(
            conversation=conversation,
            question=question,
            answer=answer,
            source_pages=sorted(source_pages),
        )

        return Response({
            'answer': answer,
            'source_pages': sorted(source_pages),
            'message_id': str(message.id),
        })


class QAHistoryView(APIView):
    """GET /api/v1/intelligence/books/<book_id>/qa/history/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        profile, err = _get_profile_or_404(book)
        if err:
            return err

        try:
            conversation = QAConversation.objects.get(
                user=request.user, profile=profile
            )
            # Get last 3 exchanges for context (per implementation guide)
            history = conversation.messages.order_by('-created_at')[:3].values(
                'question', 'answer'
            )
            return Response({
                'conversation_id': str(conversation.id),
                'messages': QAMessageSerializer(conversation.messages.order_by('created_at'), many=True).data,
                'history': list(history),
            })
        except QAConversation.DoesNotExist:
            return Response({'conversation_id': None, 'messages': [], 'history': []})

# ── 7. Notifications ──────────────────────────────────────────────────────────

class TodayNotificationsView(APIView):
    """GET /api/v1/intelligence/books/<book_id>/notifications/today/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        profile, err = _get_profile_or_404(book)
        if err:
            return err

        today = date.today()
        try:
            notif = NotificationContent.objects.get(
                user=request.user,
                profile=profile,
                date=today,
            )
            return Response({
                'ready': True,
                'notifications': NotificationContentSerializer(notif).data,
            })
        except NotificationContent.DoesNotExist:
            # Auto-trigger generation
            generate_daily_notifications_task.delay(
                str(profile.id),
                request.user.id,
                today.isoformat(),
            )
            return Response({
                'ready': False,
                'message': "Today's notifications are being generated. Check back in a few seconds.",
            }, status=status.HTTP_202_ACCEPTED)


# ── 8. Confirm Chapters ───────────────────────────────────────────────────────

class ConfirmChaptersView(APIView):
    """
    POST /api/v1/intelligence/books/<book_id>/chapters/confirm/

    Called by Flutter after the user reviews the detected chapter list.
    Accepts optional edits (renames/reorders) and triggers Stage 3:
    task_build_reading_schedule.

    Request body (all optional):
    {
      "chapters": [
        {"chapter_number": 1, "title": "Optional new title"},
        ...
      ]
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, book_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        profile, err = _get_profile_or_404(book)
        if err:
            return err

        edits = request.data.get('chapters', [])

        # Apply optional reading preference updates before building the schedule
        reading_mode = request.data.get('reading_mode', '').strip()
        daily_minutes = request.data.get('daily_minutes') or request.data.get('pages_per_day')
        valid_modes = {'skim', 'concept', 'deep', 'exam'}
        book_dirty_fields = []
        if reading_mode in valid_modes:
            book.reading_mode = reading_mode
            book_dirty_fields.append('reading_mode')
        if daily_minutes is not None:
            try:
                mins = int(daily_minutes)
                if 1 <= mins <= 480:
                    book.daily_minutes = mins
                    book_dirty_fields.append('daily_minutes')
            except (ValueError, TypeError):
                pass
        if book_dirty_fields:
            book.save(update_fields=book_dirty_fields)

        # Apply user title edits if provided
        if edits:
            for edit in edits:
                ch_num = edit.get('chapter_number')
                new_title = edit.get('title', '').strip()
                if ch_num and new_title:
                    BookIntelligenceChapter.objects.filter(
                        profile=profile,
                        chapter_number=ch_num,
                    ).update(title=new_title[:255])

        # Mark all chapters as confirmed
        profile.ai_chapters.all().update(user_confirmed=True)

        # Check if schedule already exists (idempotent)
        from apps.books.models import ReadingSchedule
        if ReadingSchedule.objects.filter(
            user=request.user, book=book
        ).exists():
            return Response({
                'message': 'Chapters already confirmed. Schedule exists.',
                'book_id': str(book_id),
            })

        # Trigger Stage 3: build reading schedule
        task_build_reading_schedule.delay(str(book_id), request.user.id)

        # Update upload status to SCHEDULING
        try:
            from apps.books.models import UserUploadedBook
            upload = book.user_upload_source
            if upload:
                upload.status = UserUploadedBook.Status.SCHEDULING
                upload.processing_stage = 'building_schedule'
                upload.save(update_fields=['status', 'processing_stage'])
        except Exception:
            pass

        chapters_data = BookIntelligenceChapterSerializer(
            profile.ai_chapters.all(), many=True
        ).data

        return Response({
            'message': 'Chapters confirmed. Building your reading schedule...',
            'book_id': str(book_id),
            'chapters': chapters_data,
        }, status=status.HTTP_202_ACCEPTED)


class GenerateNotificationsView(APIView):
    """POST /api/v1/intelligence/books/<book_id>/notifications/generate/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, book_id):
        book, err = _get_book_or_404(book_id)
        if err:
            return err

        profile, err = _get_profile_or_404(book)
        if err:
            return err

        target_date = request.data.get('date', date.today().isoformat())

        generate_daily_notifications_task.delay(
            str(profile.id),
            request.user.id,
            target_date,
        )

        return Response({
            'message': f'Notification generation queued for {target_date}.',
        }, status=status.HTTP_202_ACCEPTED)
