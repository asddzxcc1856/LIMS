from django.urls import path

from .views import (
    ActivityLogListView,
    ChartEquipmentUtilizationView,
    ChartOperatorActivityView,
    ChartOrderTrendView,
    DashboardStatsView,
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationSummaryView,
)

app_name = 'monitoring'

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('logs/', ActivityLogListView.as_view(), name='activity-logs'),
    path(
        'charts/equipment-utilization/',
        ChartEquipmentUtilizationView.as_view(),
        name='chart-equipment-utilization',
    ),
    path(
        'charts/order-trend/',
        ChartOrderTrendView.as_view(),
        name='chart-order-trend',
    ),
    path(
        'charts/operator-activity/',
        ChartOperatorActivityView.as_view(),
        name='chart-operator-activity',
    ),
    path(
        'notifications/',
        NotificationListView.as_view(),
        name='notification-list',
    ),
    path(
        'notifications/summary/',
        NotificationSummaryView.as_view(),
        name='notification-summary',
    ),
    path(
        'notifications/mark-all-read/',
        NotificationMarkAllReadView.as_view(),
        name='notification-mark-all-read',
    ),
    path(
        'notifications/<uuid:pk>/mark-read/',
        NotificationMarkReadView.as_view(),
        name='notification-mark-read',
    ),
]
