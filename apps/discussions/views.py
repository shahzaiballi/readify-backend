from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Post, Reply, PostLike, ReplyLike
from .serializers import (
    PostListSerializer,
    PostDetailSerializer,
    ReplySerializer,
    CreatePostSerializer,
    CreateReplySerializer,
)


class DiscussionsListView(APIView):
    """
    GET  /discussions/  → paginated feed with filters
    POST /discussions/  → create new post

    Filters (match your Flutter discussionFilterProvider):
      ?filter=All       → all posts
      ?filter=Popular   → sorted by likes_count
      ?filter=Recent    → sorted by created_at (default)
      ?filter=My Posts  → only current user's posts
      ?book_id=uuid     → posts for a specific book
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        posts = Post.objects.select_related('user', 'book').all()

        # Filter by book (used in BookDetailPage discussions tab)
        book_id = request.query_params.get('book_id')
        if book_id:
            posts = posts.filter(book__id=book_id)

        # Apply tab filter — matches your discussion filter tabs exactly
        filter_type = request.query_params.get('filter', 'All')

        if filter_type == 'Popular':
            posts = posts.order_by('-likes_count', '-created_at')
        elif filter_type == 'My Posts':
            posts = posts.filter(user=request.user)
        else:
            # All and Recent — newest first
            posts = posts.order_by('-created_at')

        serializer = PostListSerializer(
            posts,
            many=True,
            context={'request': request},
        )
        return Response(serializer.data)

    def post(self, request):
        serializer = CreatePostSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        # Resolve book if provided
        book = None
        if data.get('book_id'):
            from apps.books.models import Book
            book = Book.objects.get(id=data['book_id'])

        post = Post.objects.create(
            user=request.user,
            book=book,
            title=data['title'],
            content=data['content'],
            chapter_tag=data.get('chapter_tag', ''),
        )

        return Response(
            PostDetailSerializer(post, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class DiscussionDetailView(APIView):
    """
    GET /discussions/{id}/
    Returns full post detail.
    Used by DiscussionDetailPage to render the post card at the top.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, post_id):
        try:
            post = Post.objects.select_related('user', 'book').get(
                id=post_id,
            )
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PostDetailSerializer(
            post,
            context={'request': request},
        )
        return Response(serializer.data)

    def delete(self, request, post_id):
        """
        DELETE /discussions/{id}/
        Only the post author can delete their post.
        """
        try:
            post = Post.objects.get(id=post_id, user=request.user)
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found or not yours.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DiscussionRepliesView(APIView):
    """
    GET  /discussions/{id}/replies/  → list all replies
    POST /discussions/{id}/replies/  → add a reply

    Matches your replyControllerProvider and ReplyInputBar.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, post_id):
        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        replies = post.replies.select_related('user').all()
        serializer = ReplySerializer(
            replies,
            many=True,
            context={'request': request},
        )
        return Response(serializer.data)

    def post(self, request, post_id):
        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CreateReplySerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        reply = Reply.objects.create(
            post=post,
            user=request.user,
            content=serializer.validated_data['content'],
        )

        # Increment cached comments count on the post
        Post.objects.filter(id=post_id).update(
            comments_count=post.comments_count + 1,
        )

        return Response(
            ReplySerializer(reply, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class TogglePostLikeView(APIView):
    """
    POST /discussions/{id}/like/
    Toggles like on a post — like if not liked, unlike if already liked.
    Matches the like button in your PostCard.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):
        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return Response(
                {'error': 'Post not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        like, created = PostLike.objects.get_or_create(
            user=request.user,
            post=post,
        )

        if created:
            # User is liking the post
            Post.objects.filter(id=post_id).update(
                likes_count=post.likes_count + 1,
            )
            post.refresh_from_db()
            return Response({
                'liked': True,
                'likesCount': post.likes_count,
            })
        else:
            # User is unliking the post
            like.delete()
            Post.objects.filter(id=post_id).update(
                likes_count=max(0, post.likes_count - 1),
            )
            post.refresh_from_db()
            return Response({
                'liked': False,
                'likesCount': post.likes_count,
            })


class ToggleReplyLikeView(APIView):
    """
    POST /discussions/replies/{id}/like/
    Toggles like on a reply.
    Matches the like button in your ReplyCard.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, reply_id):
        try:
            reply = Reply.objects.get(id=reply_id)
        except Reply.DoesNotExist:
            return Response(
                {'error': 'Reply not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        like, created = ReplyLike.objects.get_or_create(
            user=request.user,
            reply=reply,
        )

        if created:
            Reply.objects.filter(id=reply_id).update(
                likes_count=reply.likes_count + 1,
            )
            reply.refresh_from_db()
            return Response({
                'liked': True,
                'likesCount': reply.likes_count,
            })
        else:
            like.delete()
            Reply.objects.filter(id=reply_id).update(
                likes_count=max(0, reply.likes_count - 1),
            )
            reply.refresh_from_db()
            return Response({
                'liked': False,
                'likesCount': reply.likes_count,
            })