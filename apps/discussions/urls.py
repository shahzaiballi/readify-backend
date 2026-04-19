from django.urls import path
from . import views

urlpatterns = [
    # Feed and create
    path(
        '',
        views.DiscussionsListView.as_view(),
        name='discussions-list',
    ),

    # Single post detail and delete
    path(
        '<uuid:post_id>/',
        views.DiscussionDetailView.as_view(),
        name='discussion-detail',
    ),

    # Replies for a post
    path(
        '<uuid:post_id>/replies/',
        views.DiscussionRepliesView.as_view(),
        name='discussion-replies',
    ),

    # Like / unlike a post
    path(
        '<uuid:post_id>/like/',
        views.TogglePostLikeView.as_view(),
        name='toggle-post-like',
    ),

    # Like / unlike a reply
    path(
        'replies/<uuid:reply_id>/like/',
        views.ToggleReplyLikeView.as_view(),
        name='toggle-reply-like',
    ),
]