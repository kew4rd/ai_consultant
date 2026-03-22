from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_view, name='chat'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('send/', views.send_message, name='send_message'),
    path('stream/', views.send_message_stream, name='send_message_stream'),
    path('conversations/new/', views.new_conversation, name='new_conversation'),
    path('conversations/', views.get_conversations, name='get_conversations'),
    path('conversations/<int:conversation_id>/', views.get_conversation_messages, name='conversation_messages'),
    path('conversations/<int:conversation_id>/delete/', views.delete_conversation, name='delete_conversation'),
]
