from django.contrib import admin
from .models import Order, OrderStage


class OrderStageInline(admin.TabularInline):
    model = OrderStage
    extra = 0
    readonly_fields = ['completed_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_no', 'user', 'experiment', 'status', 'is_urgent', 'created_at']
    list_filter = ['status', 'is_urgent']
    readonly_fields = ['order_no', 'created_at', 'updated_at']
    inlines = [OrderStageInline]


@admin.register(OrderStage)
class OrderStageAdmin(admin.ModelAdmin):
    list_display = ['order', 'step_order', 'department', 'equipment_type', 'status', 'assignee']
    list_filter = ['status', 'department']
