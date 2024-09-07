from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_files, name='upload_files'),
    path('success/', views.upload_success, name='upload_success'),
    path('merge_data/', views.merge_data, name='merge_data'),
    path('release_invoice/', views.release_invoice, name='release_invoice'),
    path('data_analysis/', views.data_analysis, name='data_analysis'),
    path('get_count/', views.get_count, name='get_count'),
    path('get_table_data/', views.get_table_data, name='get_table_data'),
    path('visualize_merged_data/', views.visualize_merged_data, name='visualize_merged_data'),
    path('export_to_excel/', views.export_to_excel, name='export_to_excel'),

]
