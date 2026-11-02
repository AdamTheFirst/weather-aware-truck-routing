from django.urls import path

from routing import views

urlpatterns = [
    path("api/health", views.health_view),
    path("api/geocode", views.geocode_view),
    path("api/plan", views.plan_view),
]
