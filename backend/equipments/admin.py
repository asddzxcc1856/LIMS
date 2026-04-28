from django.contrib import admin
from .models import Experiment, EquipmentType, Equipment, ExperimentRequiredEquipment


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ['name', 'remark']


@admin.register(EquipmentType)
class EquipmentTypeAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ['code', 'equipment_type', 'status']
    list_filter = ['status', 'equipment_type']


@admin.register(ExperimentRequiredEquipment)
class ExperimentRequiredEquipmentAdmin(admin.ModelAdmin):
    list_display = ['experiment', 'equipment_type', 'quantity']
