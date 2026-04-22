from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import UserBook
from .serializers import (
    LibraryBookSerializer,
    AddBookToLibrarySerializer,
    UpdateLibraryBookSerializer,
    UserProgressSerializer,
)
from apps.books.models import Book


class LibraryView(APIView):
    """
    GET  /library/        → user's full library
    POST /library/        → add book to library

    Supports ?status=in_progress|completed|not_started
    and ?favorite=true for your segmented control filters.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_books = UserBook.objects.filter(
            user=request.user
        ).select_related('book')

        # Filter by status tab (matches your LibrarySegmentedControl)
        status_filter = request.query_params.get('status')
        if status_filter:
            user_books = user_books.filter(status=status_filter)

        # Filter favorites
        favorite = request.query_params.get('favorite')
        if favorite == 'true':
            user_books = user_books.filter(is_favorite=True)

        serializer = LibraryBookSerializer(user_books, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = AddBookToLibrarySerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        book_id = serializer.validated_data['book_id']
        book = Book.objects.get(id=book_id)

        # get_or_create prevents duplicates
        user_book, created = UserBook.objects.get_or_create(
            user=request.user,
            book=book,
        )

        if not created:
            return Response(
                {'error': 'This book is already in your library.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            LibraryBookSerializer(user_book).data,
            status=status.HTTP_201_CREATED
        )


class LibraryBookDetailView(APIView):
    """
    PATCH  /library/{id}/ → update progress, favorite, status
    DELETE /library/{id}/ → remove from library
    """
    permission_classes = [IsAuthenticated]

    def _get_user_book(self, request, pk):
        """Helper to get user_book and verify ownership."""
        try:
            return UserBook.objects.get(id=pk, user=request.user)
        except UserBook.DoesNotExist:
            return None

    def patch(self, request, pk):
        user_book = self._get_user_book(request, pk)
        if not user_book:
            return Response(
                {'error': 'Book not found in your library.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = UpdateLibraryBookSerializer(
            user_book,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(LibraryBookSerializer(user_book).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        user_book = self._get_user_book(request, pk)
        if not user_book:
            return Response(
                {'error': 'Book not found in your library.'},
                status=status.HTTP_404_NOT_FOUND
            )

        user_book.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentProgressView(APIView):
    """
    GET /reading/progress/
    Returns the book the user is currently reading.
    Matches your currentProgressProvider and CurrentlyReadingCard.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Most recently read in-progress book
        user_book = UserBook.objects.filter(
            user=request.user,
            status=UserBook.Status.IN_PROGRESS
        ).select_related('book').first()

        if not user_book:
            return Response(
                {'error': 'No book currently in progress.'},
                status=status.HTTP_200_OK
            )

        serializer = UserProgressSerializer(user_book)
        return Response(serializer.data)