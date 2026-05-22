"""
equipments/serializers.py
"""
from rest_framework import serializers
from .models import (
    Equipment,
    EquipmentType,
    Experiment,
    ExperimentRequiredEquipment,
    Recipe,
)


class EquipmentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentType
        fields = ['id', 'name', 'name_en']


class EquipmentSerializer(serializers.ModelSerializer):
    type_name = serializers.CharField(source='equipment_type.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Equipment
        fields = [
            'id', 'equipment_type', 'type_name', 'code', 'status',
            'department', 'department_name',
        ]


class ExperimentRequiredEquipmentSerializer(serializers.ModelSerializer):
    equipment_type_name = serializers.CharField(source='equipment_type.name', read_only=True)
    department_name = serializers.SerializerMethodField()

    class Meta:
        model = ExperimentRequiredEquipment
        fields = ['id', 'experiment', 'equipment_type', 'equipment_type_name', 'quantity', 'department_name', 'step_order']

    def get_department_name(self, obj):
        # Infer department from the first equipment of this type
        first_eq = Equipment.objects.filter(equipment_type=obj.equipment_type).first()
        return first_eq.department.name if first_eq and first_eq.department else "N/A"


class ExperimentSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Experiment
        fields = [
            'id', 'name', 'name_en', 'remark', 'remark_en',
            'department', 'department_name',
        ]


class RecipeSerializer(serializers.ModelSerializer):
    equipment_type_name = serializers.CharField(source='equipment_type.name', read_only=True)
    equipment_type_name_en = serializers.CharField(
        source='equipment_type.name_en', read_only=True, default='',
    )

    class Meta:
        model = Recipe
        fields = [
            'id', 'name', 'name_en', 'version', 'parameters',
            'remark', 'remark_en',
            'is_active',
            'equipment_type', 'equipment_type_name', 'equipment_type_name_en',
        ]
