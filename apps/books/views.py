from datetime import date, timedelta

from django.db.models import Sum
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


# ── Today's Reading Views ──────────────────────────────────────────────────────

class TodayReadingView(APIView):
    """
    GET /api/v1/books/<book_id>/today/

    Returns today's pages based on the user's pages_per_day setting.
    Uses positional slicing: chunks[(current_day-1)*ppd : current_day*ppd]
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        from math import ceil
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Determine pages_per_day from user's reading plan
        from apps.reading.models import ReadingPlan
        reading_plan = getattr(request.user, 'reading_plan', None)
        plan_ppd = reading_plan.pages_per_day if reading_plan else 10

        # Count chunks using a single COUNT query (P5 fix)
        total_chunks = Chunk.objects.filter(chapter__book=book).count()

        if total_chunks == 0:
            return Response(
                {'error': 'This book has no reading content yet.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get or auto-create schedule (stores pages_per_day for L2 consistency)
        schedule = self._get_or_create_schedule(request.user, book, total_chunks, plan_ppd)

        # Always use the schedule's stored pages_per_day for slice consistency (L2)
        pages_per_day = schedule.pages_per_day or plan_ppd

        total_days = ceil(total_chunks / pages_per_day)
        # Update total_days and pages_per_day if reading plan changed
        if schedule.total_days != total_days or schedule.pages_per_day != pages_per_day:
            schedule.total_days = total_days
            schedule.pages_per_day = pages_per_day
            schedule.save(update_fields=['total_days', 'pages_per_day', 'updated_at'])

        # Book complete?
        if schedule.current_day > total_days:
            return Response({
                'dayNumber': total_days,
                'totalDays': total_days,
                'daysRemaining': 0,
                'progressPercent': 100,
                'projectedFinishDate': str(date.today()),
                'pagesPerDay': pages_per_day,
                'totalPages': total_chunks,
                'isTodayComplete': True,
                'isBookComplete': True,
                'chapters': [],
            })

        # Slice today's pages using DB-level slicing (P5 fix — no full table load)
        start_idx = (schedule.current_day - 1) * pages_per_day
        end_idx = min(start_idx + pages_per_day, total_chunks)
        todays_chunks = list(
            Chunk.objects
            .filter(chapter__book=book)
            .select_related('chapter')
            .order_by('chapter__chapter_number', 'chunk_index')
            [start_idx:end_idx]
        )

        # Group by chapter
        chapters_map = {}
        for i, chunk in enumerate(todays_chunks):
            ch = chunk.chapter
            if ch.id not in chapters_map:
                chapters_map[ch.id] = {
                    'id': str(ch.id),
                    'number': ch.chapter_number,
                    'title': ch.title,
                    'chunks': [],
                }
            chapters_map[ch.id]['chunks'].append({
                'id': str(chunk.id),
                'text': chunk.text,
                'chunkIndex': chunk.chunk_index,
                'pageNumber': start_idx + i + 1,
                'wordsCount': chunk.words_count,
            })

        chapters_list = list(chapters_map.values())

        # Progress
        pages_done = start_idx
        progress_percent = round((pages_done / total_chunks) * 100) if total_chunks > 0 else 0
        days_remaining = total_days - (schedule.current_day - 1)
        projected_finish = date.today() + timedelta(days=days_remaining)

        # is_today_complete: False — after completing, current_day always points to the
        # NEXT unread day. The Flutter controller handles the just-completed state locally.
        # (B9 fix: old session-today check incorrectly returned True for unread new days)
        from apps.library.models import UserBook
        user_book = UserBook.objects.filter(user=request.user, book=book).first()
        is_today_complete = False

        return Response({
            'dayNumber': schedule.current_day,
            'totalDays': total_days,
            'daysRemaining': days_remaining,
            'progressPercent': progress_percent,
            'projectedFinishDate': str(projected_finish),
            'pagesPerDay': pages_per_day,
            'totalPages': total_chunks,
            'pagesReadSoFar': pages_done,
            'todayPageStart': start_idx + 1,
            'todayPageEnd': end_idx,
            'isTodayComplete': is_today_complete,
            'isBookComplete': False,
            'chapters': chapters_list,
        })

    def _get_or_create_schedule(self, user, book, total_chunks, pages_per_day):
        """Return existing schedule or auto-create one (stores pages_per_day for L2 fix)."""
        from math import ceil
        try:
            return ReadingSchedule.objects.get(user=user, book=book)
        except ReadingSchedule.DoesNotExist:
            pass

        from apps.library.models import UserBook
        UserBook.objects.get_or_create(
            user=user,
            book=book,
            defaults={'status': UserBook.Status.IN_PROGRESS},
        )

        total_days = ceil(total_chunks / max(pages_per_day, 1))
        schedule = ReadingSchedule.objects.create(
            user=user,
            book=book,
            total_days=total_days,
            current_day=1,
            pages_per_day=pages_per_day,
            start_date=date.today(),
            schedule_data=[],
        )
        return schedule


class TodayCompleteView(APIView):
    """
    POST /api/v1/books/<book_id>/today/complete/

    Marks today's pages as done:
    - Advances current_day on ReadingSchedule
    - Records a ReadingSession
    - Updates UserBook.progress_percent using page-based progress
    - Detects milestones (25/50/75/100%) and book completion
    """
    permission_classes = [IsAuthenticated]

    MILESTONES = [25, 50, 75, 100]

    def post(self, request, book_id):
        from math import ceil
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            schedule = ReadingSchedule.objects.get(user=request.user, book=book)
        except ReadingSchedule.DoesNotExist:
            return Response(
                {'error': 'No reading schedule found for this book.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        duration_seconds = request.data.get('duration_seconds', 0)

        # Use schedule's stored pages_per_day for slice consistency (L2 fix)
        from apps.reading.models import ReadingPlan, ReadingSession
        reading_plan = getattr(request.user, 'reading_plan', None)
        pages_per_day = schedule.pages_per_day or (reading_plan.pages_per_day if reading_plan else 10)

        # Total chunks in the book
        total_chunks = Chunk.objects.filter(chapter__book=book).count()

        # Pages read today (positional slice)
        completed_day = schedule.current_day
        start_idx = (completed_day - 1) * pages_per_day
        end_idx = min(start_idx + pages_per_day, total_chunks)
        pages_read_today = end_idx - start_idx

        # Identify today's chunks for session recording
        all_chunks = list(
            Chunk.objects
            .filter(chapter__book=book)
            .select_related('chapter')
            .order_by('chapter__chapter_number', 'chunk_index')
        )
        todays_chunks = all_chunks[start_idx:end_idx]

        # Idempotency guard: compare day_number sent by client against schedule.current_day.
        # If the client sends day_number and it doesn't match the current schedule day,
        # the request is stale (already advanced) — return without double-advancing.
        day_number_from_client = request.data.get('day_number')
        if day_number_from_client is not None:
            try:
                if int(day_number_from_client) != completed_day:
                    from apps.library.models import UserBook as _UB2
                    _ub2 = _UB2.objects.filter(user=request.user, book=book).first()
                    return Response({
                        'progressPercent': _ub2.progress_percent if _ub2 else 0,
                        'pagesReadToday': pages_read_today,
                        'totalPagesRead': end_idx,
                        'totalPages': total_chunks,
                        'nextDayNumber': schedule.current_day,
                        'totalDays': schedule.total_days,
                        'daysRemaining': max(0, schedule.total_days - (schedule.current_day - 1)),
                        'milestone': None,
                        'isBookComplete': schedule.current_day > schedule.total_days,
                    })
            except (ValueError, TypeError):
                pass

        # Advance schedule
        schedule.current_day += 1
        total_days = ceil(total_chunks / max(pages_per_day, 1))
        schedule.total_days = total_days
        schedule.save(update_fields=['current_day', 'total_days', 'updated_at'])

        # Get or create UserBook
        from apps.library.models import UserBook, ChapterProgress
        user_book, _ = UserBook.objects.get_or_create(
            user=request.user,
            book=book,
            defaults={'status': UserBook.Status.IN_PROGRESS},
        )
        if user_book.status == UserBook.Status.NOT_STARTED:
            user_book.status = UserBook.Status.IN_PROGRESS
            user_book.save(update_fields=['status'])

        # Record reading session
        first_chunk = todays_chunks[0] if todays_chunks else None
        ReadingSession.objects.create(
            user_book=user_book,
            last_chunk=first_chunk,
            chunks_completed=pages_read_today,
            duration_seconds=duration_seconds,
        )

        # Mark chapter progress for touched chapters
        chapters_seen = {}
        for chunk in todays_chunks:
            chapters_seen[chunk.chapter_id] = chunk.chapter

        for chapter_id, chapter in chapters_seen.items():
            ch_chunks = [c for c in all_chunks if c.chapter_id == chapter_id]
            last_chunk_in_chapter = ch_chunks[-1] if ch_chunks else None

            cp, _ = ChapterProgress.objects.get_or_create(
                user_book=user_book,
                chapter_id=chapter_id,
            )
            cp.is_active = True
            # Chapter complete if the last chunk of the chapter is within pages read so far
            if last_chunk_in_chapter and all_chunks.index(last_chunk_in_chapter) < end_idx:
                cp.is_completed = True
                cp.is_active = False
                cp.completed_at = date.today()
            cp.save()

        # Page-based progress
        pages_done = end_idx
        progress_percent = round((pages_done / total_chunks) * 100) if total_chunks > 0 else 0
        progress_percent = min(99, progress_percent)

        # Milestone detection
        old_progress = user_book.progress_percent
        milestone_hit = None
        for m in self.MILESTONES:
            if old_progress < m <= progress_percent:
                milestone_hit = f'{m}_percent'
                break

        # Book completion
        is_book_complete = schedule.current_day > total_days
        if is_book_complete:
            progress_percent = 100
            user_book.status = UserBook.Status.COMPLETED
            milestone_hit = milestone_hit or '100_percent'

        user_book.progress_percent = progress_percent
        user_book.save(update_fields=['progress_percent', 'status'])

        # Update User reading stats ─────────────────────────────────────
        user = request.user

        # Streak: single-query set-based calculation (P1 fix — replaces N+1 loop)
        cutoff = date.today() - timedelta(days=366)
        session_dates = set(
            ReadingSession.objects.filter(
                user_book__user=user,
                session_date__gte=cutoff,
            ).values_list('session_date', flat=True).distinct()
        )
        streak = 0
        check_date = date.today()
        while check_date in session_dates:
            streak += 1
            check_date -= timedelta(days=1)
        user.current_streak = streak

        # Total pages ever read
        user.total_pages_read = ReadingSession.objects.filter(
            user_book__user=user,
        ).aggregate(total=Sum('chunks_completed'))['total'] or 0

        # Books read = completed books count
        if is_book_complete:
            user.books_read = UserBook.objects.filter(
                user=user, status=UserBook.Status.COMPLETED
            ).count()
            if user.books_read >= 5:
                user.is_avid_reader = True

        user.save(update_fields=['current_streak', 'total_pages_read', 'books_read', 'is_avid_reader'])

        # Fix 5: Pre-clean next day's chunks proactively (fire-and-forget)
        if not is_book_complete:
            try:
                from apps.book_intelligence.tasks import task_clean_chunk
                next_start = end_idx
                next_end = min(next_start + pages_per_day, total_chunks)
                next_chunks = all_chunks[next_start:next_end]
                for chunk in next_chunks:
                    if not chunk.is_cleaned:
                        task_clean_chunk.delay(str(chunk.id))
            except Exception:
                pass

        return Response({
            'progressPercent': progress_percent,
            'pagesReadToday': pages_read_today,
            'totalPagesRead': pages_done,
            'totalPages': total_chunks,
            'nextDayNumber': schedule.current_day,
            'totalDays': total_days,
            'daysRemaining': max(0, total_days - (schedule.current_day - 1)),
            'milestone': milestone_hit,
            'isBookComplete': is_book_complete,
        })


class TodaySummaryView(APIView):
    """
    GET /api/v1/books/<book_id>/today/summary/?day=N

    Returns the AI-generated summary for a reading day's content.
    Uses positional slicing — consistent with TodayReadingView.
    Defaults to current_day-1 (the day just completed).
    Accepts ?day=N to override (e.g. during reading, before completing).

    Fixes: B2 (wrong task args), B3 (AIChapter import), B4+B5 (day_number broken).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            schedule = ReadingSchedule.objects.get(user=request.user, book=book)
        except ReadingSchedule.DoesNotExist:
            return Response({'error': 'No reading schedule found.'}, status=status.HTTP_404_NOT_FOUND)

        reading_mode = book.reading_mode or 'deep'
        pages_per_day = schedule.pages_per_day or 10

        # Determine which day to summarise (B4 fix: default to last completed day)
        try:
            target_day = int(request.query_params.get('day', schedule.current_day - 1))
        except (ValueError, TypeError):
            target_day = schedule.current_day - 1
        target_day = max(1, target_day)

        # Use positional slicing — same logic as TodayReadingView (B5 fix)
        total_chunks = Chunk.objects.filter(chapter__book=book).count()
        if total_chunks == 0:
            return Response({'error': 'No reading content found.'}, status=status.HTTP_404_NOT_FOUND)

        start_idx = (target_day - 1) * pages_per_day
        if start_idx >= total_chunks:
            return Response({'error': 'No reading content found for that day.'}, status=status.HTTP_404_NOT_FOUND)
        end_idx = min(start_idx + pages_per_day, total_chunks)

        todays_chunks = list(
            Chunk.objects
            .filter(chapter__book=book)
            .select_related('chapter')
            .order_by('chapter__chapter_number', 'chunk_index')
            [start_idx:end_idx]
        )
        chapter_ids = list({c.chapter_id for c in todays_chunks})
        if not chapter_ids:
            return Response({'error': 'No reading content found for that day.'}, status=status.HTTP_404_NOT_FOUND)

        chapters = Chapter.objects.filter(id__in=chapter_ids).order_by('chapter_number')

        # Import correct model name (B3 fix: was AIChapter, correct is BookIntelligenceChapter)
        try:
            from apps.book_intelligence.models import ChapterIntelligence, BookIntelligenceChapter
            profile = book.intelligence_profile
        except Exception:
            return Response({'status': 'generating', 'summaries': []}, status=status.HTTP_202_ACCEPTED)

        summaries = []
        needs_generation = False

        for chapter in chapters:
            ai_chapter = None
            try:
                ai_chapter = BookIntelligenceChapter.objects.get(
                    profile=profile, chapter_number=chapter.chapter_number
                )
                intel = ChapterIntelligence.objects.get(ai_chapter=ai_chapter, mode=reading_mode)
                summary_content, key_takeaways = _extract_summary_content(intel.content or {}, reading_mode)
                summaries.append({
                    'chapterNumber': chapter.chapter_number,
                    'chapterTitle': chapter.title,
                    'mode': reading_mode,
                    'summaryContent': summary_content,
                    'keyTakeaways': key_takeaways,
                })
            except (ChapterIntelligence.DoesNotExist, BookIntelligenceChapter.DoesNotExist):
                needs_generation = True
                if ai_chapter:
                    try:
                        # B2 fix: pass correct ai_chapter.id and mode (not profile.id + chapter_number)
                        from apps.book_intelligence.tasks import generate_chapter_intelligence_task
                        generate_chapter_intelligence_task.delay(str(ai_chapter.id), reading_mode)
                    except Exception as gen_err:
                        logger.error(f'[TodaySummary] Failed to trigger generation: {gen_err}')

        if needs_generation and not summaries:
            return Response({'status': 'generating', 'summaries': []}, status=status.HTTP_202_ACCEPTED)

        return Response({
            'status': 'ready',
            'readingMode': reading_mode,
            'summaries': summaries,
        })