from django.urls import path

from routing import views

urlpatterns = [
    path("api/geocode", views.geocode_view),
    path("api/plan", views.plan_view),
]
