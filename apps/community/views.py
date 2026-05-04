"""
apps/community/views.py

Fixed:
- Book community creation without requiring catalog book_id
- Image upload for community cover
- Leave/Delete community endpoints
- Faster message loading with select_related optimizations
- Admin kick member endpoint
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
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
    GET  /community/  → discover public communities
    POST /community/  → create a new community (supports multipart for image upload)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        mine = request.query_params.get('mine') == 'true'
        private = request.query_params.get('private') == 'true'
        book_id = request.query_params.get('book_id')
        comm_type = request.query_params.get('type')
        search = request.query_params.get('search', '')

        if private:
            communities = Community.objects.filter(
                members__user=request.user,
                privacy='private',
            )
        elif mine:
            communities = Community.objects.filter(members__user=request.user)
        else:
            communities = Community.objects.filter(privacy='public')

        if book_id:
            communities = communities.filter(book_id=book_id)

        if comm_type:
            communities = communities.filter(community_type=comm_type)

        if search:
            communities = communities.filter(name__icontains=search)

        communities = communities.select_related(
            'book', 'created_by'
        ).prefetch_related(
            'members'
        ).distinct().order_by('-member_count', '-created_at')

        serializer = CommunityListSerializer(
            communities, many=True, context={'request': request}
        )
        return Response(serializer.data)

    def post(self, request):
        serializer = CreateCommunitySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # ── Resolve book ───────────────────────────────────────────────────────
        book = None
        if data.get('community_type') == 'book':
            if data.get('book_id'):
                # Exact match by ID
                from apps.books.models import Book
                try:
                    book = Book.objects.get(id=data['book_id'])
                except Book.DoesNotExist:
                    return Response({'error': 'Book not found.'}, status=404)
            elif data.get('book_name'):
                # Search by title in catalog
                from apps.books.models import Book
                book_name = data['book_name'].strip()
                book = Book.objects.filter(
                    title__icontains=book_name,
                    is_published=True
                ).first()
                # If not in catalog, that's OK — community will have no book link
                # but we store the name in the description if needed

        # ── Create community ───────────────────────────────────────────────────
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

        # ── Handle image upload ────────────────────────────────────────────────
        cover_image = data.get('cover_image')
        if cover_image:
            community.cover_image = cover_image
            community.save(update_fields=['cover_image'])

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
    """GET/DELETE /community/{id}/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        try:
            community = Community.objects.select_related(
                'book', 'created_by'
            ).get(id=community_id)
        except Community.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        if community.privacy == 'private':
            if not community.members.filter(user=request.user).exists():
                return Response({'error': 'Not a member.'}, status=403)

        return Response(
            CommunityDetailSerializer(community, context={'request': request}).data
        )

    def delete(self, request, community_id):
        """DELETE — only admin/creator can delete"""
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        is_admin = community.members.filter(
            user=request.user, role=CommunityMember.Role.ADMIN
        ).exists()

        if not is_admin:
            return Response({'error': 'Only admins can delete this community.'}, status=403)

        community.delete()
        return Response(status=204)

    def patch(self, request, community_id):
        """PATCH — update community name/description/emoji (admin only)"""
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        is_admin = community.members.filter(
            user=request.user, role=CommunityMember.Role.ADMIN
        ).exists()

        if not is_admin:
            return Response({'error': 'Only admins can edit this community.'}, status=403)

        if 'name' in request.data:
            community.name = request.data['name']
        if 'description' in request.data:
            community.description = request.data['description']
        if 'cover_emoji' in request.data:
            community.cover_emoji = request.data['cover_emoji']
        if 'cover_image' in request.FILES:
            community.cover_image = request.FILES['cover_image']

        community.save()
        return Response(
            CommunityDetailSerializer(community, context={'request': request}).data
        )


class JoinCommunityView(APIView):
    """POST /community/{id}/join/"""
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
            community.refresh_from_db()

        return Response({
            'joined': True,
            'memberCount': community.member_count
        })


class JoinByInviteView(APIView):
    """POST /community/join/{token}/"""
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
            community.refresh_from_db()

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

        # Check if this is the last admin — prevent orphaning
        is_admin = membership.role == CommunityMember.Role.ADMIN
        if is_admin:
            admin_count = CommunityMember.objects.filter(
                community_id=community_id,
                role=CommunityMember.Role.ADMIN
            ).count()
            member_count_total = CommunityMember.objects.filter(
                community_id=community_id
            ).count()

            if admin_count == 1 and member_count_total > 1:
                return Response({
                    'error': 'You are the only admin. Please promote another member before leaving.'
                }, status=400)

        membership.delete()

        try:
            community = Community.objects.get(id=community_id)
            new_count = max(0, community.member_count - 1)
            community.member_count = new_count
            community.save(update_fields=['member_count'])
        except Community.DoesNotExist:
            pass

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


class KickMemberView(APIView):
    """DELETE /community/{id}/members/{user_id}/ — admin only"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, community_id, user_id):
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        is_admin = community.members.filter(
            user=request.user, role=CommunityMember.Role.ADMIN
        ).exists()

        if not is_admin:
            return Response({'error': 'Only admins can remove members.'}, status=403)

        # Cannot kick yourself
        if str(request.user.id) == str(user_id):
            return Response({'error': 'Cannot kick yourself. Use leave instead.'}, status=400)

        try:
            membership = CommunityMember.objects.get(
                community=community, user_id=user_id
            )
            membership.delete()
            new_count = max(0, community.member_count - 1)
            Community.objects.filter(id=community_id).update(member_count=new_count)
            return Response({'removed': True})
        except CommunityMember.DoesNotExist:
            return Response({'error': 'Member not found.'}, status=404)


class PromoteMemberView(APIView):
    """POST /community/{id}/members/{user_id}/promote/ — admin only"""
    permission_classes = [IsAuthenticated]

    def post(self, request, community_id, user_id):
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)

        is_admin = community.members.filter(
            user=request.user, role=CommunityMember.Role.ADMIN
        ).exists()

        if not is_admin:
            return Response({'error': 'Only admins can promote members.'}, status=403)

        try:
            membership = CommunityMember.objects.get(
                community=community, user_id=user_id
            )
            membership.role = CommunityMember.Role.ADMIN
            membership.save()
            return Response({'promoted': True})
        except CommunityMember.DoesNotExist:
            return Response({'error': 'Member not found.'}, status=404)


class CommunityMessagesView(APIView):
    """
    GET  /community/{id}/messages/     → paginated message history (FAST)
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

        before_id = request.query_params.get('before')

        # Optimized query with all related data in one hit
        messages = community.messages.select_related(
            'sender',
            'reply_to',
            'reply_to__sender',
        ).prefetch_related(
            'reactions',
            'reactions__user',
        )

        if before_id:
            try:
                pivot = Message.objects.get(id=before_id)
                messages = messages.filter(created_at__lt=pivot.created_at)
            except Message.DoesNotExist:
                pass

        messages = messages.order_by('-created_at')[:50]
        messages = list(reversed(messages))

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

        # Refresh with related data for proper serialization
        message = Message.objects.select_related(
            'sender', 'reply_to', 'reply_to__sender'
        ).prefetch_related('reactions').get(id=message.id)

        return Response(
            MessageSerializer(message, context={'request': request}).data,
            status=201,
        )


class MessageReactionView(APIView):
    """POST /community/messages/{id}/react/"""
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
    """GET /community/suggestions/buddy/"""
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
            community = Community.objects.filter(
                book=book, privacy='public'
            ).order_by('-member_count').first()

            if community:
                suggestions.append(
                    CommunityListSerializer(community, context={'request': request}).data
                )

        return Response(suggestions)