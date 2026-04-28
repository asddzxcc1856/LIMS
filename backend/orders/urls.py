from django.urls import path
from . import views

urlpatterns = [
    path('', views.OrderListView.as_view(), name='order-list'),
    path('stages/', views.OrderStageListView.as_view(), name='order-stage-list'),
    path('stages/<uuid:pk>/review/', views.OrderReviewView.as_view(), name='order-stage-review'),
    path('stages/<uuid:pk>/complete/', views.OrderCompleteView.as_view(), name='order-stage-complete'),
    path('create/', views.OrderCreateView.as_view(), name='order-create'),
    path('<uuid:pk>/', views.OrderDetailView.as_view(), name='order-detail'),
    path('<uuid:pk>/review/', views.OrderReviewView.as_view(), name='order-review'),
    path('<uuid:pk>/complete/', views.OrderCompleteView.as_view(), name='order-complete'),
]
