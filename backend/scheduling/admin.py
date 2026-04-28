from django.contrib import admin
from .models import EquipmentBooking


@admin.register(EquipmentBooking)
class EquipmentBookingAdmin(admin.ModelAdmin):
    list_display = ['order', 'equipment', 'started_at', 'ended_at']
    list_filter = ['started_at']
