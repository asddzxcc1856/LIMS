from django.urls import path
from . import views

urlpatterns = [
    path('experiments/', views.ExperimentListView.as_view(), name='experiment-list'),
    path('experiments/<uuid:pk>/', views.ExperimentDetailView.as_view(), name='experiment-detail'),
    path('types/', views.EquipmentTypeListView.as_view(), name='equipment-type-list'),
    path('status-matrix/', views.EquipmentStatusMatrixView.as_view(), name='equipment-status-matrix'),
    path('capacity-check/', views.CapacityCheckView.as_view(), name='capacity-check'),
    path('', views.EquipmentListView.as_view(), name='equipment-list'),
    path('<uuid:pk>/', views.EquipmentDetailView.as_view(), name='equipment-detail'),
]
