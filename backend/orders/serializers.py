"""
orders/serializers.py
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Approval, Order, OrderStage, Sample

User = get_user_model()


def _viewer_is_requester(serializer):
    """Return True when the request user is a regular_employee (廠區送樣).

    Used to scrub operator identities from the response — the spec wants
    requesters to know *which lab* is handling their order, not *which
    person*. Manager / lab_member / superuser see the full set.
    """
    request = serializer.context.get('request') if hasattr(serializer, 'context') else None
    user = getattr(request, 'user', None) if request else None
    return getattr(user, 'role', None) == 'regular_employee'


# Fields whose values would leak operator identity to the requester. Keys
# stay in the response so the frontend doesn't break; values are blanked
# when ``_viewer_is_requester`` is true.
_OPERATOR_IDENTITY_FIELDS = (
    'assignee', 'assignee_name', 'assignee_username',
    'received_by', 'received_by_username',
    'parameters_set_by', 'parameters_set_by_username',
    'dispatched_by', 'dispatched_by_username',
    'created_by', 'created_by_username',
    'loaded_by', 'loaded_by_username',
    'completed_by', 'completed_by_username',
)


class _MaskOperatorMixin:
    """Mixin that scrubs operator identity when the viewer is a
    regular_employee. Department / experiment / status / schedule
    stay visible — only the *who* is masked.
    """
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if _viewer_is_requester(self):
            for f in _OPERATOR_IDENTITY_FIELDS:
                if f in data:
                    data[f] = None
        return data


class OrderStageSerializer(_MaskOperatorMixin, serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    assignee_name = serializers.CharField(source='assignee.username', read_only=True)
    equipment_code = serializers.CharField(source='equipment.code', read_only=True)
    recipe_name = serializers.CharField(source='recipe.name', read_only=True, default=None)
    recipe_version = serializers.IntegerField(source='recipe.version', read_only=True, default=None)
    recipe_parameters = serializers.JSONField(source='recipe.parameters', read_only=True, default=None)
    received_by_username = serializers.CharField(
        source='received_by.username', read_only=True, default=None,
    )
    parameters_set_by_username = serializers.CharField(
        source='parameters_set_by.username', read_only=True, default=None,
    )
    # ``sample_count`` is read by the lab workbench tabs to decide whether
    # the stage has already been split — it's the gate that keeps 待分貨
    # and 待派工 distinct (no count → still in 分貨 queue).
    sample_count = serializers.IntegerField(
        source='order.samples.count', read_only=True,
    )

    # Metadata from parent order — the manager uses experiment_name as the
    # recipe context when scheduling. equipment_type_name is kept for legacy
    # rows but is normally NULL on new stages.
    order_no = serializers.CharField(source='order.order_no', read_only=True)
    user_name = serializers.CharField(source='order.user.username', read_only=True)
    lot_id = serializers.CharField(source='order.lot_id', read_only=True, default='')
    experiment_name = serializers.CharField(source='order.experiment.name', read_only=True)
    is_urgent = serializers.BooleanField(source='order.is_urgent', read_only=True)
    requirements = serializers.CharField(source='order.requirements', read_only=True)
    remark = serializers.CharField(source='order.remark', read_only=True)
    equipment_type_name = serializers.CharField(source='equipment_type.name', read_only=True)

    class Meta:
        model = OrderStage
        fields = [
            'id', 'order', 'step_order', 'department_name',
            'status', 'assignee', 'assignee_name', 'equipment', 'equipment_code',
            'recipe', 'recipe_name', 'recipe_version', 'recipe_parameters',
            'parameter_overrides',
            'parameters_set_at', 'parameters_set_by', 'parameters_set_by_username',
            'sample_count',
            'received_at', 'received_by', 'received_by_username',
            'order_no', 'user_name', 'lot_id',
            'experiment_name', 'is_urgent', 'requirements', 'remark', 'equipment_type_name',
            'schedule_start', 'schedule_end', 'completed_at',
        ]


class OrderListSerializer(serializers.ModelSerializer):
    """Compact representation for list views."""
    user_name = serializers.CharField(source='user.username', read_only=True)
    experiment_name = serializers.CharField(source='experiment.name', read_only=True)
    # ``Order.lot`` is now an FK to WaferLot (whose PK is the code), so
    # ``order.lot_id`` returns the underlying code string. Expose it under
    # the historical "lot_id" field name to keep frontend reads stable.
    lot_id = serializers.CharField(read_only=True, default='')
    stages = OrderStageSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_no', 'user_name', 'experiment_name',
            'lot_id', 'status', 'is_urgent', 'requirements', 'remark',
            'created_at', 'stages',
        ]
        read_only_fields = ['id', 'order_no', 'status', 'created_at']


class OrderDetailSerializer(_MaskOperatorMixin, serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    experiment_name = serializers.CharField(source='experiment.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    assignee_name = serializers.CharField(source='assignee.username', read_only=True)
    lot_id = serializers.CharField(read_only=True, default='')
    experiment_details = serializers.SerializerMethodField()
    # The detail drawer in the requester UI renders a relay-progress
    # ant-design Steps component off this list; without it the tracker
    # silently disappears.
    stages = OrderStageSerializer(many=True, read_only=True)

    def get_experiment_details(self, obj):
        if obj.experiment is None:
            return None
        from equipments.serializers import ExperimentSerializer
        return ExperimentSerializer(obj.experiment).data


    class Meta:
        model = Order
        fields = [
            'id', 'order_no', 'user', 'user_name',
            'department', 'department_name',
            'experiment', 'experiment_name', 'experiment_details',
            'status', 'is_urgent', 'lot_id', 'assignee', 'assignee_name',
            'schedule_start', 'schedule_end',
            'rejection_reason', 'requirements', 'remark',
            'created_at', 'updated_at', 'ended_at',
            'stages',
        ]
        read_only_fields = [
            'id', 'order_no', 'status', 'rejection_reason', 'assignee_name',
            'created_at', 'updated_at', 'ended_at',
        ]


class OrderCreateSerializer(serializers.Serializer):
    """Requester creates a single-lab-visit order.

    Experiments are pinned to a lab, so the requester only picks the
    experiment plus optional metadata; the order routes to the experiment's
    lab automatically and the requester never sees machines.

    ``lot_id`` MUST resolve to an existing WaferLot row (it's the PK of
    that table) — the form uses a dropdown sourced from the registered
    lots so a typo cannot reach the API.
    """
    experiment = serializers.UUIDField()
    is_urgent = serializers.BooleanField(default=False)
    lot_id = serializers.CharField(max_length=50)
    requirements = serializers.CharField(required=False, default='', allow_blank=True)
    remark = serializers.CharField(required=False, default='', allow_blank=True)


class ApprovalSerializer(serializers.ModelSerializer):
    """Audit row written by every manager decision on a stage."""

    actor_username = serializers.CharField(source='actor.username', read_only=True, default=None)
    decision_display = serializers.CharField(source='get_decision_display', read_only=True)
    order_no = serializers.CharField(source='stage.order.order_no', read_only=True)
    step_order = serializers.IntegerField(source='stage.step_order', read_only=True)

    class Meta:
        model = Approval
        fields = [
            'id', 'stage', 'order_no', 'step_order',
            'actor', 'actor_username',
            'decision', 'decision_display',
            'comment', 'decided_at',
        ]
        read_only_fields = ['id', 'actor', 'decided_at']


class SampleSerializer(_MaskOperatorMixin, serializers.ModelSerializer):
    """Sample row — used by /samples/ endpoints and admin CRUD.

    Surfaces the per-sample dispatch fields so the lab workbench can
    show one row per sub-LOT in each phase tab.
    """

    full_code = serializers.CharField(read_only=True)
    order_no = serializers.CharField(source='order.order_no', read_only=True)
    created_by_username = serializers.CharField(
        source='created_by.username', read_only=True, default=None,
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    equipment_code = serializers.CharField(source='equipment.code', read_only=True, default=None)
    equipment_type_name = serializers.CharField(
        source='equipment.equipment_type.name', read_only=True, default=None,
    )
    equipment_type_name_en = serializers.CharField(
        source='equipment.equipment_type.name_en', read_only=True, default=None,
    )
    recipe_name = serializers.CharField(source='recipe.name', read_only=True, default=None)
    recipe_name_en = serializers.CharField(source='recipe.name_en', read_only=True, default=None)
    recipe_version = serializers.IntegerField(source='recipe.version', read_only=True, default=None)
    recipe_parameters = serializers.JSONField(source='recipe.parameters', read_only=True, default=None)
    assignee_username = serializers.CharField(source='assignee.username', read_only=True, default=None)
    parameters_set_by_username = serializers.CharField(
        source='parameters_set_by.username', read_only=True, default=None,
    )
    dispatched_by_username = serializers.CharField(
        source='dispatched_by.username', read_only=True, default=None,
    )
    loaded_by_username = serializers.CharField(
        source='loaded_by.username', read_only=True, default=None,
    )
    completed_by_username = serializers.CharField(
        source='completed_by.username', read_only=True, default=None,
    )
    # Surface lab + experiment context so the workbench can group by
    # lab without re-fetching the parent stage.
    department_name = serializers.CharField(source='order.department.name', read_only=True)
    experiment_name = serializers.CharField(source='order.experiment.name', read_only=True, default=None)
    experiment_name_en = serializers.CharField(source='order.experiment.name_en', read_only=True, default=None)
    lot_id = serializers.CharField(source='order.lot_id', read_only=True, default='')

    class Meta:
        model = Sample
        fields = [
            'id', 'order', 'order_no',
            'sub_code', 'full_code', 'wafer_count', 'notes',
            'parent_sample',
            'status', 'status_display',
            'equipment', 'equipment_code', 'equipment_type_name', 'equipment_type_name_en',
            'recipe', 'recipe_name', 'recipe_name_en', 'recipe_version', 'recipe_parameters',
            'parameter_overrides',
            'parameters_set_at', 'parameters_set_by', 'parameters_set_by_username',
            'dispatched_by', 'dispatched_by_username',
            'assignee', 'assignee_username',
            'schedule_start', 'schedule_end',
            'loaded_at', 'loaded_by', 'loaded_by_username',
            'completed_at', 'completed_by', 'completed_by_username',
            'department_name', 'experiment_name', 'experiment_name_en', 'lot_id',
            'created_at', 'created_by', 'created_by_username',
        ]
        read_only_fields = [
            'id', 'created_at', 'created_by',
            'status', 'equipment', 'recipe', 'parameter_overrides',
            'parameters_set_at', 'parameters_set_by',
            'assignee', 'schedule_start', 'schedule_end',
            'loaded_at', 'loaded_by', 'completed_at', 'completed_by',
        ]


class OrderReviewSerializer(serializers.Serializer):
    """Lab Manager approves (with schedule) or rejects (with reason)."""
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    rejection_reason = serializers.CharField(required=False, default='', allow_blank=True)
    schedule_start = serializers.DateTimeField(required=False)
    schedule_end = serializers.DateTimeField(required=False)
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role__in=['lab_member', 'lab_manager']),
        required=False, allow_null=True
    )


    def validate(self, data):
        if data['action'] == 'approve':
            if not data.get('schedule_start') or not data.get('schedule_end'):
                raise serializers.ValidationError(
                    'schedule_start and schedule_end are required when approving.'
                )
        if data['action'] == 'reject':
            if not data.get('rejection_reason', '').strip():
                raise serializers.ValidationError(
                    'rejection_reason is required when rejecting.'
                )
        return data
