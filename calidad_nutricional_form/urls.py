from django.urls import path, include

urlpatterns = [
    path('api/', include('api.urls')),
    path("", include("initial_form.urls")),  # Incluye las rutas de la app `form`
]

