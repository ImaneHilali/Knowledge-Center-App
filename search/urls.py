from django.urls import path


from . import views

urlpatterns = [
    path('', views.search_page, name='search_page'),
    path('insert_file/', views.insert_file, name='insert_file'),
    path('semantic_search/', views.semantic_search, name='semantic_search'),
    path('list_files/', views.list_files, name='list_files'),
    path('update_file/<int:file_id>/', views.update_file, name='update_file'),
    path('delete_file/<int:file_id>/', views.delete_file, name='delete_file'),
    path('chatbot/', views.chatbot, name='chatbot'),
]