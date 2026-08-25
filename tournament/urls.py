from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('teams/', views.teams, name='teams'),
    path('schedule/', views.schedule, name='schedule'),
    path('standings/', views.standings, name='standings'),
    path('results-admin/', views.results_admin, name='results_admin'),
]
