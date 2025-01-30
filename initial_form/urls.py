from django.urls import path
from . import views

urlpatterns = [
    path("", views.set_basic_data, name="set_basic_data"),
    path("set_breakfast", views.set_breakfast, name="set_breakfast"),
    path("set_breakfast_additional", views.set_breakfast_additional, name="set_breakfast_additional"),
    path("set_lunch", views.set_lunch, name="set_lunch"),
    path("set_lunch_additional", views.set_lunch_additional, name="set_lunch_additional"),
    path("set_dinner", views.set_dinner, name="set_dinner"),
    path("set_dinner_additional", views.set_dinner_additional, name="set_dinner_additional"),
    path("dashboard", views.dashboard, name="dashboard"),
    path("load_comidas/", views.load_comidas_from_api, name="load_comidas"),
    path('query_selected_comidas_details/', views.query_selected_comidas_details, name='query_selected_comidas_details'),
    path("send_report/", views.send_report, name="send_report"),
    path('did_eat_breakfast/', views.did_eat_breakfast, name='did_eat_breakfast'),
    path('did_eat_breakfast_additional/', views.did_eat_breakfast_additional, name='did_eat_breakfast_additional'),
    path('did_eat_lunch/', views.did_eat_lunch, name='did_eat_lunch'),
    path('did_eat_lunch_additional/', views.did_eat_lunch_additional, name='did_eat_lunch_additional'),
    path('did_eat_dinner/', views.did_eat_dinner, name='did_eat_dinner'),
    path('did_eat_dinner_additional/', views.did_eat_dinner_additional, name='did_eat_dinner_additional'),
    path("guardar-busqueda-sin-coincidencia/", views.guardar_busqueda_sin_coincidencia, name="guardar_busqueda_sin_coincidencia"),
]