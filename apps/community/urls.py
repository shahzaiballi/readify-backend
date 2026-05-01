"""apps/community/urls.py"""
from django.urls import path
from . import views

urlpatterns = [
    # Community CRUD + discovery
    path('', views.CommunityListView.as_view(), name='community-list'),
    path('<uuid:community_id>/', views.CommunityDetailView.as_view(), name='community-detail'),

    # Membership
    path('<uuid:community_id>/join/', views.JoinCommunityView.as_view(), name='join-community'),
    path('<uuid:community_id>/leave/', views.LeaveCommunityView.as_view(), name='leave-community'),
    path('<uuid:community_id>/members/', views.CommunityMembersView.as_view(), name='community-members'),

    # Messages
    path('<uuid:community_id>/messages/', views.CommunityMessagesView.as_view(), name='community-messages'),
    path('messages/<uuid:message_id>/react/', views.MessageReactionView.as_view(), name='message-react'),
    path('messages/<uuid:message_id>/', views.DeleteMessageView.as_view(), name='delete-message'),

    # Invite link join (private groups)
    path('join/<str:token>/', views.JoinByInviteView.as_view(), name='join-by-invite'),

    # Buddy group suggestions
    path('suggestions/buddy/', views.BuddyGroupSuggestionsView.as_view(), name='buddy-suggestions'),
]