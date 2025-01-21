from django.urls import path
from . import views

urlpatterns = [
    path('test/', views.test_connection, name='test_connection'),
    path('test_data/', views.test_data, name='test_data'),
    path('load_alimentos_test/', views.create_alimentos_data, name='load_alimentos_test')    
]
