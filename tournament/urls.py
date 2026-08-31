from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('teams/', views.teams, name='teams'),
    path('schedule/', views.schedule, name='schedule'),
    path('standings/', views.standings, name='standings'),
    path('upper/', views.upper, name='upper'),
    path('final-ranking/', views.final_ranking, name='final_ranking'),
    path('group-assignment/', views.group_assignment, name='group_assignment'),
    path('results-admin/', views.results_admin, name='results_admin'),
    path('reset-results/', views.reset_results, name='reset_results'),
    path('manual-tiebreaks/', views.manual_tiebreaks, name='manual_tiebreaks'),
]
