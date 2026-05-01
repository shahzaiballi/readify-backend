"""
apps/community/views.py
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Community, CommunityMember, Message, MessageReaction
from .serializers import (
    CommunityListSerializer, CommunityDetailSerializer,
    CreateCommunitySerializer, MessageSerializer,
    SendMessageSerializer, ToggleReactionSerializer,
    MemberUserSerializer,
)


class CommunityListView(APIView):
    """
    GET  /community/                  → discover public communities
    POST /community/                  → create a new community

    Query params:
      ?type=general|book              → filter by type
      ?book_id=<uuid>                 → book-specific communities
      ?mine=true                      → communities I joined/created
      ?private=true                   → my private communities
      ?search=<str>                   → search by name
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        mine = request.query_params.get('mine') == 'true'
        private = request.query_params.get('private') == 'true'
        book_id = request.query_params.get('book_id')
        comm_type = request.query_params.get('type')
        search = request.query_params.get('search', '')

        if private:
            # Private communities where I'm a member
            communities = Community.objects.filter(
                members__user=request.user,
                privacy='private',
            )
        elif mine:
            # All communities I've joined (public or private)
            communities = Community.objects.filter(members__user=request.user)
        else:
            # Public discovery
            communities = Community.objects.filter(privacy='public')

        if book_id:
            communities = communities.filter(book_id=book_id)

        if comm_type:
            communities = communities.filter(community_type=comm_type)

        if search:
            communities = communities.filter(name__icontains=search)

        communities = communities.distinct().order_by('-member_count', '-created_at')

        serializer = CommunityListSerializer(
            communities, many=True, context={'request': request}
        )
        return Response(serializer.data)

    def post(self, request):
        serializer = CreateCommunitySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        book = None
        if data.get('book_id'):
            from apps.books.models import Book
            try:
                book = Book.objects.get(id=data['book_id'])
            except Book.DoesNotExist:
                return Response({'error': 'Book not found.'}, status=404)

        community = Community.objects.create(
            name=data['name'],
            description=data.get('description', ''),
            community_type=data['community_type'],
            privacy=data['privacy'],
            created_by=request.user,
            book=book,
            cover_emoji=data.get('cover_emoji', '📚'),
            member_count=1,
        )

        # Creator becomes admin
        CommunityMember.objects.create(
            community=community,
            user=request.user,
            role=CommunityMember.Role.ADMIN,
        )

        return Response(
            CommunityDetailSerializer(community, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class CommunityDetailView(APIView):
    """GET /community/{id}/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        # Private communities only visible to members
        if community.privacy == 'private':
            if not community.members.filter(user=request.user).exists():
                return Response({'error': 'Not a member.'}, status=403)

        return Response(
            CommunityDetailSerializer(community, context={'request': request}).data
        )

    def delete(self, request, community_id):
        try:
            community = Community.objects.get(id=community_id, created_by=request.user)
        except Community.DoesNotExist:
            return Response({'error': 'Not found or not admin.'}, status=404)
        community.delete()
        return Response(status=204)


class JoinCommunityView(APIView):
    """POST /community/{id}/join/ — join a public community"""
    permission_classes = [IsAuthenticated]

    def post(self, request, community_id):
        try:
            community = Community.objects.get(id=community_id, privacy='public')
        except Community.DoesNotExist:
            return Response({'error': 'Community not found or is private.'}, status=404)

        _, created = CommunityMember.objects.get_or_create(
            community=community, user=request.user,
            defaults={'role': CommunityMember.Role.MEMBER}
        )
        if created:
            Community.objects.filter(id=community_id).update(
                member_count=community.member_count + 1
            )
        return Response({'joined': True, 'memberCount': community.member_count + (1 if created else 0)})


class JoinByInviteView(APIView):
    """POST /community/join/{token}/ — join a private community via invite link"""
    permission_classes = [IsAuthenticated]

    def post(self, request, token):
        try:
            community = Community.objects.get(invite_token=token)
        except Community.DoesNotExist:
            return Response({'error': 'Invalid invite link.'}, status=404)

        _, created = CommunityMember.objects.get_or_create(
            community=community, user=request.user,
            defaults={'role': CommunityMember.Role.MEMBER}
        )
        if created:
            Community.objects.filter(id=community.id).update(
                member_count=community.member_count + 1
            )
        return Response(
            CommunityDetailSerializer(community, context={'request': request}).data
        )


class LeaveCommunityView(APIView):
    """POST /community/{id}/leave/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, community_id):
        try:
            membership = CommunityMember.objects.get(
                community_id=community_id, user=request.user
            )
        except CommunityMember.DoesNotExist:
            return Response({'error': 'Not a member.'}, status=404)
        membership.delete()
        Community.objects.filter(id=community_id).update(
            member_count=max(0, Community.objects.get(id=community_id).member_count - 1)
        )
        return Response({'left': True})


class CommunityMembersView(APIView):
    """GET /community/{id}/members/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        if community.privacy == 'private':
            if not community.members.filter(user=request.user).exists():
                return Response({'error': 'Not a member.'}, status=403)

        members = community.members.select_related('user').order_by('joined_at')
        serializer = MemberUserSerializer(members, many=True, context={'request': request})
        return Response(serializer.data)


class CommunityMessagesView(APIView):
    """
    GET  /community/{id}/messages/     → paginated message history
    POST /community/{id}/messages/     → send a message
    """
    permission_classes = [IsAuthenticated]

    def _check_member(self, community, user):
        return community.members.filter(user=user).exists()

    def get(self, request, community_id):
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        if not self._check_member(community, request.user):
            return Response({'error': 'Not a member.'}, status=403)

        # Pagination: ?before=<message_id> for cursor-based loading
        before_id = request.query_params.get('before')
        messages = community.messages.filter(is_deleted=False).select_related(
            'sender', 'reply_to__sender'
        ).prefetch_related('reactions__user')

        if before_id:
            try:
                pivot = Message.objects.get(id=before_id)
                messages = messages.filter(created_at__lt=pivot.created_at)
            except Message.DoesNotExist:
                pass

        messages = messages.order_by('-created_at')[:50]
        messages = list(reversed(messages))  # chronological order

        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request, community_id):
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        if not self._check_member(community, request.user):
            return Response({'error': 'Not a member.'}, status=403)

        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        reply_to = None
        if serializer.validated_data.get('reply_to_id'):
            try:
                reply_to = Message.objects.get(
                    id=serializer.validated_data['reply_to_id'],
                    community=community,
                )
            except Message.DoesNotExist:
                pass

        message = Message.objects.create(
            community=community,
            sender=request.user,
            content=serializer.validated_data['content'],
            reply_to=reply_to,
        )

        return Response(
            MessageSerializer(message, context={'request': request}).data,
            status=201,
        )


class MessageReactionView(APIView):
    """POST /community/messages/{id}/react/ — toggle a reaction"""
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        serializer = ToggleReactionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        try:
            message = Message.objects.get(id=message_id)
        except Message.DoesNotExist:
            return Response({'error': 'Message not found.'}, status=404)

        emoji = serializer.validated_data['emoji']
        reaction, created = MessageReaction.objects.get_or_create(
            message=message, user=request.user, emoji=emoji
        )
        if not created:
            reaction.delete()
            return Response({'reacted': False, 'emoji': emoji})

        return Response({'reacted': True, 'emoji': emoji})


class DeleteMessageView(APIView):
    """DELETE /community/messages/{id}/"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, message_id):
        try:
            message = Message.objects.get(id=message_id, sender=request.user)
        except Message.DoesNotExist:
            return Response({'error': 'Not found or not yours.'}, status=404)
        message.is_deleted = True
        message.content = 'This message was deleted.'
        message.save(update_fields=['is_deleted', 'content'])
        return Response(status=204)


class BuddyGroupSuggestionsView(APIView):
    """
    GET /community/suggestions/buddy/
    Returns one suggested group per paused/not-started book the user has.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.library.models import UserBook

        paused_books = UserBook.objects.filter(
            user=request.user,
            status__in=['not_started', 'in_progress'],
        ).select_related('book').exclude(
            book__communities__members__user=request.user
        )[:5]

        suggestions = []
        for ub in paused_books:
            book = ub.book
            # Find or suggest the most popular community for this book
            community = Community.objects.filter(
                book=book, privacy='public'
            ).order_by('-member_count').first()

            if community:
                suggestions.append(
                    CommunityListSerializer(community, context={'request': request}).data
                )

        return Response(suggestions)