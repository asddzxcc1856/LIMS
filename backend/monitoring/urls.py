from django.urls import path

from .views import ActivityLogListView, DashboardStatsView

app_name = 'monitoring'

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('logs/', ActivityLogListView.as_view(), name='activity-logs'),
]
