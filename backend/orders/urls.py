from django.urls import path
from . import views

urlpatterns = [
    path('', views.OrderListView.as_view(), name='order-list'),
    path('stages/', views.OrderStageListView.as_view(), name='order-stage-list'),
    path('stages/<uuid:pk>/review/', views.OrderReviewView.as_view(), name='order-stage-review'),
    path('stages/<uuid:pk>/receive/', views.OrderReceiveView.as_view(), name='order-stage-receive'),
    path('stages/<uuid:pk>/dispatch/', views.StageDispatchView.as_view(), name='order-stage-dispatch'),
    path('stages/<uuid:pk>/parameters/', views.StageParametersView.as_view(), name='order-stage-parameters'),
    path('stages/<uuid:pk>/start/', views.StageStartView.as_view(), name='order-stage-start'),
    path('stages/<uuid:pk>/complete/', views.OrderCompleteView.as_view(), name='order-stage-complete'),
    # Per-sample dispatch chain — every sub-LOT can travel independently.
    path('samples/', views.SampleListView.as_view(), name='sample-list'),
    path('samples/<uuid:pk>/dispatch/', views.SampleDispatchView.as_view(), name='sample-dispatch'),
    path('samples/<uuid:pk>/parameters/', views.SampleParametersView.as_view(), name='sample-parameters'),
    path('samples/<uuid:pk>/assign/', views.SampleAssignView.as_view(), name='sample-assign'),
    path('samples/<uuid:pk>/load/', views.SampleLoadView.as_view(), name='sample-load'),
    path('samples/<uuid:pk>/telemetry/', views.SampleTelemetryView.as_view(), name='sample-telemetry'),
    path('samples/<uuid:pk>/report-abnormal/', views.SampleReportAbnormalView.as_view(), name='sample-report-abnormal'),
    path('samples/<uuid:pk>/complete/', views.SampleCompleteView.as_view(), name='sample-complete'),
    path('stages/<uuid:pk>/events/', views.StageEventListCreateView.as_view(), name='stage-event-list'),
    path('stages/<uuid:pk>/approvals/', views.StageApprovalListCreateView.as_view(), name='stage-approval-list'),
    path('create/', views.OrderCreateView.as_view(), name='order-create'),
    path('<uuid:pk>/', views.OrderDetailView.as_view(), name='order-detail'),
    path('<uuid:pk>/review/', views.OrderReviewView.as_view(), name='order-review'),
    path('<uuid:pk>/samples/', views.OrderSampleListCreateView.as_view(), name='order-samples'),
    path('<uuid:pk>/complete/', views.OrderCompleteView.as_view(), name='order-complete'),
]
