from rest_framework.routers import DefaultRouter

from . import views

app_name = 'admin_api'

router = DefaultRouter()
router.register(r'fabs', views.FABViewSet, basename='admin-fab')
router.register(r'departments', views.DepartmentViewSet, basename='admin-department')
router.register(r'wafer-lots', views.WaferLotViewSet, basename='admin-wafer-lot')
router.register(r'users', views.UserViewSet, basename='admin-user')
router.register(r'experiments', views.ExperimentViewSet, basename='admin-experiment')
router.register(r'equipment-types', views.EquipmentTypeViewSet, basename='admin-equipment-type')
router.register(r'equipment', views.EquipmentViewSet, basename='admin-equipment')
router.register(r'recipes', views.RecipeViewSet, basename='admin-recipe')
router.register(
    r'experiment-requirements',
    views.ExperimentRequiredEquipmentViewSet,
    basename='admin-experiment-requirement',
)
router.register(r'orders', views.OrderViewSet, basename='admin-order')
router.register(r'order-stages', views.OrderStageViewSet, basename='admin-order-stage')
router.register(r'bookings', views.EquipmentBookingViewSet, basename='admin-booking')
router.register(r'stage-events', views.StageEventViewSet, basename='admin-stage-event')
router.register(r'approvals', views.ApprovalViewSet, basename='admin-approval')
router.register(r'notifications', views.NotificationViewSet, basename='admin-notification')
router.register(r'samples', views.SampleViewSet, basename='admin-sample')

urlpatterns = router.urls
