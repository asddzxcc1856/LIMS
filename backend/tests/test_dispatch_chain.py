"""Tests for the split-of-duties dispatch chain:
分貨 → 派工 (dispatch) → 設定參數 (parameters) → 啟動 (start).

Each step is its own service + endpoint so different lab_members can
own each sub-action. The manager is excluded from these endpoints
(role gate) — they only sign off / reject.
"""
import pytest
from freezegun import freeze_time
from rest_framework.exceptions import ValidationError

from orders import services
from orders.models import OrderStage, Sample

from tests.factories import (
    EquipmentFactory,
    EquipmentTypeFactory,
    OrderStageFactory,
    RecipeFactory,
)


def _seed_sample(order):
    """Helper: dispatch_stage now requires at least one Sample on the
    order (分貨 → 派工 sequence). Tests that exercise dispatch directly
    use this so they don't drift back to the old skip-able behaviour."""
    Sample.objects.get_or_create(
        order=order, sub_code='A',
        defaults={'wafer_count': 1},
    )


@pytest.mark.unit
class TestDispatchStage:
    @freeze_time('2026-05-15 10:00:00')
    def test_pins_machine_recipe_and_schedule(
        self, db, order, department, equipment_type, lab_member, mocker,
    ):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type)
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        _seed_sample(order)   # 分貨 must precede 派工 (req)

        def fake_allocate(stg, equipment_id=None):
            stg.equipment = eq
            stg.save(update_fields=['equipment'])
        mocker.patch(
            'scheduling.services.allocate_equipments_for_stage',
            side_effect=fake_allocate,
        )

        services.dispatch_stage(
            stage,
            operator=lab_member,
            equipment=str(eq.id),
            recipe=str(recipe.id),
            schedule_start='2026-05-16T10:00:00Z',
            schedule_end='2026-05-16T12:00:00Z',
        )
        stage.refresh_from_db()
        assert stage.status == OrderStage.Status.APPROVED  # stays approved
        assert stage.recipe_id == recipe.id
        assert stage.schedule_start is not None
        # No assignee yet — that's the 啟動 step
        assert stage.assignee_id is None

    def test_rejects_non_approved_stage(
        self, db, order, department, equipment_type, lab_member,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        with pytest.raises(ValidationError, match='Cannot dispatch'):
            services.dispatch_stage(
                stage,
                operator=lab_member,
                equipment=None,
                recipe=None,
                schedule_start='2099-01-01T00:00:00Z',
                schedule_end='2099-01-01T01:00:00Z',
            )

    @freeze_time('2026-05-15 10:00:00')
    def test_rejects_dispatch_without_samples(
        self, db, order, department, equipment_type, lab_member,
    ):
        """分貨 must precede 派工 — dispatch refuses an order with no Sample."""
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        # Deliberately NO _seed_sample(order) here.
        with pytest.raises(ValidationError, match='Cannot dispatch before 分貨'):
            services.dispatch_stage(
                stage,
                operator=lab_member,
                equipment=None,
                recipe=None,
                schedule_start='2026-05-16T10:00:00Z',
                schedule_end='2026-05-16T12:00:00Z',
            )


@pytest.mark.unit
class TestSetStageParameters:
    @freeze_time('2026-05-15 10:00:00')
    def test_records_ack_with_actor(
        self, db, order, department, equipment_type, lab_member, mocker,
    ):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(
            equipment_type=equipment_type,
            parameters={'temp_C': 250, 'time_sec': 600},
        )
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            equipment=eq, recipe=recipe,
            status=OrderStage.Status.APPROVED,
        )
        services.set_stage_parameters(
            stage,
            operator=lab_member,
            parameter_overrides={'temp_C': 260},
        )
        stage.refresh_from_db()
        assert stage.parameters_set_at is not None
        assert stage.parameters_set_by_id == lab_member.id
        assert stage.parameter_overrides == {'temp_C': 260}

    def test_rejects_without_recipe(
        self, db, order, department, equipment_type, lab_member,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        with pytest.raises(ValidationError, match='Dispatch and pick a recipe'):
            services.set_stage_parameters(
                stage, operator=lab_member, parameter_overrides={},
            )

    def test_empty_overrides_is_valid_ack(
        self, db, order, department, equipment_type, lab_member,
    ):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            equipment=eq, recipe=recipe,
            status=OrderStage.Status.APPROVED,
        )
        services.set_stage_parameters(
            stage, operator=lab_member, parameter_overrides={},
        )
        stage.refresh_from_db()
        assert stage.parameters_set_at is not None
        assert stage.parameter_overrides == {}


@pytest.mark.unit
class TestStartStage:
    def _ready_stage(self, order, department, equipment_type, mocker=None):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        from django.utils import timezone
        import datetime as _dt
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            equipment=eq, recipe=recipe,
            schedule_start=timezone.now() + _dt.timedelta(hours=1),
            schedule_end=timezone.now() + _dt.timedelta(hours=2),
            parameters_set_at=timezone.now(),
            status=OrderStage.Status.APPROVED,
        )
        return stage

    def test_assigns_lab_member_and_flips_to_in_progress(
        self, db, order, department, equipment_type, lab_member,
    ):
        stage = self._ready_stage(order, department, equipment_type)
        services.start_stage(stage, operator=lab_member, assignee=lab_member)
        stage.refresh_from_db()
        assert stage.status == OrderStage.Status.IN_PROGRESS
        assert stage.assignee_id == lab_member.id

    def test_rejects_lab_manager_as_assignee(
        self, db, order, department, equipment_type, lab_member, lab_manager,
    ):
        stage = self._ready_stage(order, department, equipment_type)
        with pytest.raises(ValidationError, match='not a manager'):
            services.start_stage(
                stage, operator=lab_member, assignee=lab_manager,
            )

    def test_missing_equipment_blocks_start(
        self, db, order, department, equipment_type, lab_member,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        with pytest.raises(ValidationError, match='Dispatch to a machine'):
            services.start_stage(
                stage, operator=lab_member, assignee=lab_member,
            )

    def test_missing_param_ack_blocks_start(
        self, db, order, department, equipment_type, lab_member,
    ):
        from django.utils import timezone
        import datetime as _dt
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            equipment=eq, recipe=recipe,
            schedule_start=timezone.now() + _dt.timedelta(hours=1),
            schedule_end=timezone.now() + _dt.timedelta(hours=2),
            status=OrderStage.Status.APPROVED,
        )
        with pytest.raises(ValidationError, match='設定參數'):
            services.start_stage(
                stage, operator=lab_member, assignee=lab_member,
            )


@pytest.mark.integration
class TestEndpointRoleGating:
    def test_dispatch_forbidden_for_manager(
        self, db, manager_client, order, department, equipment_type,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        response = manager_client.post(
            f'/api/orders/stages/{stage.id}/dispatch/',
            {}, format='json',
        )
        assert response.status_code == 403

    def test_parameters_forbidden_for_manager(
        self, db, manager_client, order, department, equipment_type,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        response = manager_client.post(
            f'/api/orders/stages/{stage.id}/parameters/',
            {}, format='json',
        )
        assert response.status_code == 403

    def test_start_forbidden_for_manager(
        self, db, manager_client, order, department, equipment_type,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        response = manager_client.post(
            f'/api/orders/stages/{stage.id}/start/',
            {}, format='json',
        )
        assert response.status_code == 403

    def test_review_approve_forbidden_for_manager(
        self, db, manager_client, order, department, equipment_type,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        # Combined approve+schedule path is now lab_member only too
        response = manager_client.patch(
            f'/api/orders/stages/{stage.id}/review/',
            {'action': 'approve', 'schedule_start': '2099-01-01T00:00:00Z',
             'schedule_end': '2099-01-01T01:00:00Z'},
            format='json',
        )
        assert response.status_code == 403

    def test_reject_still_allowed_for_manager(
        self, db, manager_client, order, department, equipment_type,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        response = manager_client.patch(
            f'/api/orders/stages/{stage.id}/review/',
            {'action': 'reject', 'rejection_reason': 'duplicate request'},
            format='json',
        )
        assert response.status_code == 200

    def test_user_list_filter_role_excludes_managers(
        self, db, member_client, lab_member, lab_manager,
    ):
        # ``?role=lab_member`` must NOT return the lab_manager fixture
        response = member_client.get('/api/users/?role=lab_member')
        assert response.status_code == 200
        rows = response.data.get('results') or response.data
        roles = {r['role'] for r in rows}
        assert roles == {'lab_member'}
        usernames = {r['username'] for r in rows}
        assert lab_manager.username not in usernames
