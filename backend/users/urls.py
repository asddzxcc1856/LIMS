from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

urlpatterns = [
    # Auth
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    # Lookup
    path('fabs/', views.FABListView.as_view(), name='fab-list'),
    path('departments/', views.DepartmentListView.as_view(), name='department-list'),
    path('', views.UserListView.as_view(), name='user-list'),
]
