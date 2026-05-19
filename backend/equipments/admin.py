from django.contrib import admin
from .models import (
    Equipment,
    EquipmentType,
    Experiment,
    ExperimentRequiredEquipment,
    Recipe,
)


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


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ['name', 'equipment_type', 'version', 'is_active', 'updated_at']
    list_filter = ['equipment_type', 'is_active']
    search_fields = ['name', 'equipment_type__name']
