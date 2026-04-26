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

        # Filter by status tab
        status_filter = request.query_params.get('status')
        if status_filter:
            user_books = user_books.filter(status=status_filter)

        # Filter favorites
        favorite = request.query_params.get('favorite')
        if favorite == 'true':
            user_books = user_books.filter(is_favorite=True)

        serializer = LibraryBookSerializer(user_books, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = AddBookToLibrarySerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        book_id = serializer.validated_data['book_id']
        book = Book.objects.get(id=book_id)

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
            LibraryBookSerializer(user_book, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class LibraryBookDetailView(APIView):
    """
    PATCH  /library/{id}/ → update progress, favorite, status
    DELETE /library/{id}/ → remove from library

    NOTE: {id} here is the UserBook.id (UUID), NOT the Book.id.
    The Flutter app must send the userBookId field that is now
    included in the LibraryBookSerializer response.
    """
    permission_classes = [IsAuthenticated]

    def _get_user_book(self, request, pk):
        """
        Look up by UserBook primary key AND verify ownership.
        Accepts both the UserBook UUID and — for backwards compatibility —
        the Book UUID (we try the book lookup as a fallback).
        """
        # Primary lookup: UserBook.id
        try:
            return UserBook.objects.get(id=pk, user=request.user)
        except UserBook.DoesNotExist:
            pass

        # Fallback: Flutter might be sending the Book.id
        try:
            return UserBook.objects.get(book_id=pk, user=request.user)
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
            return Response(LibraryBookSerializer(user_book, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        user_book = self._get_user_book(request, pk)
        if not user_book:
            return Response(
                {'error': 'Book not found in your library.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # If this is a user-uploaded book, delete the Book record too
        # (which will cascade-delete the UserBook via ForeignKey)
        book = user_book.book
        if book.source == Book.Source.USER_UPLOAD:
            # Delete the book entirely (user upload)
            # This automatically deletes user_book due to CASCADE
            book.delete()
        else:
            # For admin books, just remove from user's library
            user_book.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentProgressView(APIView):
    """
    GET /reading/progress/
    Returns the book the user is currently reading, including the chapter
    and chunk to resume from.

    Returns 404 if no book is currently in progress.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_book = UserBook.objects.filter(
            user=request.user,
            status=UserBook.Status.IN_PROGRESS
        ).select_related('book', 'current_chapter').first()

        if not user_book:
            return Response(
                {'detail': 'No book currently in progress.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = UserProgressSerializer(user_book, context={'request': request})
        return Response(serializer.data)