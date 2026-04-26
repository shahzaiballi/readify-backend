from datetime import date, timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import ReadingSession, ReadingPlan
from .serializers import (
    ReadingPlanSerializer,
    CreateSessionSerializer,
    InsightsSerializer,
)
from apps.library.models import UserBook, ChapterProgress
from apps.books.models import Book, Chapter, Chunk


class ReadingSessionView(APIView):
    """
    POST /reading/session/
    Called by ChunkedReadingScreen when the user advances a chunk.
    Updates the user's progress and records reading time.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateSessionSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # 1. Get or create UserBook entry
        try:
            book = Book.objects.get(id=data['book_id'])
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        user_book, _ = UserBook.objects.get_or_create(
            user=request.user,
            book=book,
            defaults={'status': UserBook.Status.IN_PROGRESS}
        )

        # Ensure status is in_progress when actively reading
        if user_book.status == UserBook.Status.NOT_STARTED:
            user_book.status = UserBook.Status.IN_PROGRESS
            user_book.save()

        # 2. Get chapter and update chapter progress
        try:
            chapter = Chapter.objects.get(id=data['chapter_id'])
        except Chapter.DoesNotExist:
            return Response({'error': 'Chapter not found.'}, status=status.HTTP_404_NOT_FOUND)

        chapter_progress, _ = ChapterProgress.objects.get_or_create(
            user_book=user_book,
            chapter=chapter,
        )

        # Update which chunk the user is on
        total_chunks = chapter.chunks.count()
        chapter_progress.last_chunk_index = data['chunk_index']
        chapter_progress.is_active = True

        # Mark chapter complete if user reached the last chunk
        if total_chunks > 0 and data['chunk_index'] >= total_chunks - 1:
            chapter_progress.is_completed = True
            chapter_progress.is_active = False
            chapter_progress.completed_at = date.today()

        chapter_progress.save()

        # Deactivate all other chapters for this book
        ChapterProgress.objects.filter(
            user_book=user_book,
            is_active=True
        ).exclude(id=chapter_progress.id).update(is_active=False)

        # 3. Update overall book progress percentage
        total_chapters = book.chapters.count()
        if total_chapters > 0:
            completed_chapters = ChapterProgress.objects.filter(
                user_book=user_book,
                is_completed=True
            ).count()
            user_book.progress_percent = round(
                (completed_chapters / total_chapters) * 100
            )
            
            # If the current chapter is completed, move to the next chapter
            if chapter_progress.is_completed:
                # Find the next unread chapter
                next_chapter = Chapter.objects.filter(
                    book=book,
                    chapter_number__gt=chapter.chapter_number
                ).order_by('chapter_number').first()
                
                if next_chapter:
                    # Set next chapter as current
                    user_book.current_chapter = next_chapter
                    user_book.current_chunk_index = 0
                    
                    # Mark next chapter as active in chapter progress
                    next_chapter_progress, _ = ChapterProgress.objects.get_or_create(
                        user_book=user_book,
                        chapter=next_chapter,
                    )
                    next_chapter_progress.is_active = True
                    next_chapter_progress.save()
                else:
                    # No next chapter - user finished the book
                    user_book.current_chapter = chapter
                    user_book.current_chunk_index = data['chunk_index']
            else:
                # Current chapter not complete yet, keep it as current
                user_book.current_chapter = chapter
                user_book.current_chunk_index = data['chunk_index']

            # Mark whole book complete if all chapters done
            if user_book.progress_percent == 100:
                user_book.status = UserBook.Status.COMPLETED

            user_book.save()

        # 4. Record the reading session
        try:
            current_chunk = Chunk.objects.get(
                chapter=chapter,
                chunk_index=data['chunk_index']
            )
        except Chunk.DoesNotExist:
            current_chunk = None

        ReadingSession.objects.create(
            user_book=user_book,
            last_chunk=current_chunk,
            chunks_completed=data['chunks_completed'],
            duration_seconds=data['duration_seconds'],
        )

        return Response({
            'message': 'Session recorded.',
            'progress_percent': user_book.progress_percent,
        }, status=status.HTTP_201_CREATED)


class InsightsView(APIView):
    """
    GET /reading/insights/
    Matches your insightsProvider and InsightsGrid on the home screen.
    Returns cardsDue, readTodayMinutes, dayStreak.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        today = date.today()

        # 1. Cards due — count total flashcards across user's in-progress books
        in_progress_book_ids = UserBook.objects.filter(
            user=user,
            status=UserBook.Status.IN_PROGRESS
        ).values_list('book_id', flat=True)

        from apps.books.models import Flashcard
        cards_due = Flashcard.objects.filter(
            book_id__in=in_progress_book_ids
        ).count()

        # 2. Read today — sum of all session durations today
        today_sessions = ReadingSession.objects.filter(
            user_book__user=user,
            session_date=today
        )
        read_today_seconds = sum(s.duration_seconds for s in today_sessions)
        read_today_minutes = round(read_today_seconds / 60)

        # 3. Day streak — count consecutive days with at least one session
        streak = 0
        check_date = today
        while True:
            has_session = ReadingSession.objects.filter(
                user_book__user=user,
                session_date=check_date
            ).exists()
            if has_session:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break

        serializer = InsightsSerializer({
            'cardsDue': cards_due,
            'readTodayMinutes': read_today_minutes,
            'dayStreak': streak,
        })

        return Response(serializer.data)


class ReadingPlanView(APIView):
    """
    GET /reading-plan/  → get user's reading plan
    PUT /reading-plan/  → update reading plan
    Matches your ReadingPlanPage and readingPlanProvider.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plan, _ = ReadingPlan.objects.get_or_create(
            user=request.user,
            defaults={
                'daily_minutes': 45,
                'days_per_week': 5,
                'preferred_time': 'Evening',
            }
        )
        serializer = ReadingPlanSerializer(plan)
        return Response(serializer.data)

    def put(self, request):
        plan, _ = ReadingPlan.objects.get_or_create(user=request.user)
        serializer = ReadingPlanSerializer(plan, data=request.data)

        if serializer.is_valid():
            # Map camelCase back to snake_case for saving
            plan.daily_minutes = serializer.validated_data.get(
                'daily_minutes', plan.daily_minutes
            )
            plan.days_per_week = serializer.validated_data.get(
                'days_per_week', plan.days_per_week
            )
            plan.preferred_time = serializer.validated_data.get(
                'preferred_time', plan.preferred_time
            )
            plan.save()
            return Response(ReadingPlanSerializer(plan).data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)