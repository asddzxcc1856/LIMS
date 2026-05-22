from django.urls import path

from .views import (
    ActivityLogListView,
    ChartEquipmentUtilizationView,
    ChartOperatorActivityView,
    ChartOrderBusinessView,
    ChartOrderTrendView,
    DashboardStatsView,
    MyStatsView,
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationSummaryView,
    OperatorActivityDetailView,
    SampleHistoryView,
    SampleListForReportsView,
)

app_name = 'monitoring'

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('my-stats/', MyStatsView.as_view(), name='my-stats'),
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
        'charts/operator-activity/<uuid:user_id>/',
        OperatorActivityDetailView.as_view(),
        name='operator-activity-detail',
    ),
    path(
        'charts/order-business/',
        ChartOrderBusinessView.as_view(),
        name='chart-order-business',
    ),
    path(
        'lot-history/',
        SampleListForReportsView.as_view(),
        name='lot-history-list',
    ),
    path(
        'lot-history/<uuid:sample_id>/',
        SampleHistoryView.as_view(),
        name='sample-history',
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
