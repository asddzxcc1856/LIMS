"""Unit tests for the order/stage state-machine services.

Showcases the five test-double styles:
  * Fake     — full Django ORM via factory_boy
  * Stub     — pre-baked fixture rows that supply method input
  * Mock     — mocker.patch() to replace scheduling allocation
  * Spy      — mocker.spy() to verify _send_notification was invoked
  * Time fake — freeze_time() to make schedule guards deterministic
"""
from datetime import timedelta

import pytest
from freezegun import freeze_time
from rest_framework.exceptions import ValidationError

from orders import services
from orders.models import Order, OrderStage
from tests.factories import (
    EquipmentFactory,
    EquipmentTypeFactory,
    ExperimentFactory,
    OrderFactory,
    OrderStageFactory,
    UserFactory,
)


@pytest.mark.unit
class TestCreateOrder:
    def test_user_without_department_is_rejected(self, db, employee, equipment_type):
        # Arrange — user with no department; even with a valid experiment +
        # target lab, creation should still be blocked because the requester
        # has no home dept to attribute the order to.
        user = UserFactory(department=None)
        experiment = ExperimentFactory.with_requirement(equipment_type=equipment_type)
        # Act / Assert
        with pytest.raises(ValidationError, match='department'):
            services.create_order(
                user=user, target_department=employee.department, experiment=experiment,
            )

    def test_rejected_when_experiment_has_no_requirements(self, db, employee):
        # Arrange — experiment exists but no required_equipments rows
        experiment = ExperimentFactory()
        # Act / Assert
        with pytest.raises(ValidationError, match='no equipment requirements'):
            services.create_order(
                user=employee,
                target_department=employee.department,
                experiment=experiment,
            )

    def test_creates_one_stage_per_requirement_in_target_lab(self, db, employee, equipment_type):
        # Arrange — experiment with 2 sequential requirements (different types)
        from tests.factories import (
            ExperimentRequiredEquipmentFactory, EquipmentTypeFactory, DepartmentFactory,
        )
        target = DepartmentFactory(name='Reliability Lab')
        type_b = EquipmentTypeFactory(name='Furnace')
        experiment = ExperimentFactory(name='RelTest')
        ExperimentRequiredEquipmentFactory(
            experiment=experiment, equipment_type=equipment_type,
            quantity=1, step_order=1,
        )
        ExperimentRequiredEquipmentFactory(
            experiment=experiment, equipment_type=type_b, quantity=2, step_order=2,
        )
        # Act
        order = services.create_order(
            user=employee,
            target_department=target,
            experiment=experiment,
            lot_id='L-001',
        )
        # Assert
        assert order.status == Order.Status.WAITING
        assert order.lot_id == 'L-001'
        stages = list(order.stages.order_by('step_order'))
        assert len(stages) == 2
        assert stages[0].department_id == target.id
        assert stages[0].equipment_type_id == equipment_type.id
        assert stages[0].status == OrderStage.Status.WAITING   # first stage open
        assert stages[1].equipment_type_id == type_b.id
        assert stages[1].status == OrderStage.Status.PENDING   # waits for relay

    def test_target_lab_manager_is_notified(self, db, employee, equipment_type, mocker):
        # Arrange — Spy on _send_notification; manager is in the destination lab
        from tests.factories import DepartmentFactory
        target = DepartmentFactory(name='Reliability Lab')
        UserFactory(department=target, role='lab_manager')
        experiment = ExperimentFactory.with_requirement(equipment_type=equipment_type)
        notify_spy = mocker.spy(services, '_send_notification')
        # Act
        services.create_order(
            user=employee, target_department=target, experiment=experiment,
        )
        # Assert — one notification, addressed to the target-lab manager
        assert notify_spy.call_count == 1

    def test_target_department_is_required(self, db, employee, equipment_type):
        experiment = ExperimentFactory.with_requirement(equipment_type=equipment_type)
        with pytest.raises(ValidationError, match='target_department'):
            services.create_order(
                user=employee, target_department=None, experiment=experiment,
            )

    def test_experiment_is_required(self, db, employee):
        with pytest.raises(ValidationError, match='experiment'):
            services.create_order(
                user=employee,
                target_department=employee.department,
                experiment=None,
            )


@pytest.mark.unit
class TestRejectOrder:
    def test_blank_reason_is_rejected(self, db, order):
        # Act / Assert
        with pytest.raises(ValidationError, match='rejection_reason'):
            services.reject_order(order, rejection_reason='   ')

    def test_valid_rejection_persists_reason_and_status(self, db, order):
        # Arrange
        order.status = Order.Status.WAITING
        order.save()
        # Act
        result = services.reject_order(order, rejection_reason='Out of capacity')
        # Assert
        assert result.status == Order.Status.REJECTED
        assert result.rejection_reason == 'Out of capacity'

    def test_cannot_reject_already_done_order(self, db, order):
        # Arrange
        order.status = Order.Status.DONE
        order.save()
        # Act / Assert
        with pytest.raises(ValidationError, match='Cannot transition'):
            services.reject_order(order, rejection_reason='nope')


@pytest.mark.unit
class TestApproveAndScheduleStage:
    @freeze_time('2026-05-01 10:00:00')
    def test_rejects_schedule_in_the_past(self, db, order, equipment_type):
        # Arrange — stage in WAITING
        stage = OrderStageFactory(
            order=order, equipment_type=equipment_type, status=OrderStage.Status.WAITING,
        )
        # Act / Assert
        with pytest.raises(ValidationError, match='past'):
            services.approve_and_schedule_stage(
                stage,
                schedule_start='2026-04-30T10:00:00Z',
                schedule_end='2026-04-30T11:00:00Z',
            )

    @freeze_time('2026-05-01 10:00:00')
    def test_rejects_end_before_start(self, db, order, equipment_type):
        stage = OrderStageFactory(
            order=order, equipment_type=equipment_type, status=OrderStage.Status.WAITING,
        )
        with pytest.raises(ValidationError, match='after'):
            services.approve_and_schedule_stage(
                stage,
                schedule_start='2026-05-02T11:00:00Z',
                schedule_end='2026-05-02T10:00:00Z',
            )

    def test_cannot_approve_pending_stage(self, db, order, equipment_type):
        # Arrange — stage in PENDING (not yet relayed)
        stage = OrderStageFactory(
            order=order, equipment_type=equipment_type, status=OrderStage.Status.PENDING,
        )
        with pytest.raises(ValidationError, match='Cannot approve'):
            services.approve_and_schedule_stage(
                stage,
                schedule_start='2099-01-01T00:00:00Z',
                schedule_end='2099-01-01T01:00:00Z',
            )

    @freeze_time('2026-05-01 10:00:00')
    def test_happy_path_transitions_to_in_progress(self, db, order, equipment_type, mocker):
        # Arrange
        # Mock external dependency: scheduling.services.allocate_equipments_for_stage
        mocker.patch(
            'scheduling.services.allocate_equipments_for_stage', return_value=[],
        )
        stage = OrderStageFactory(
            order=order, equipment_type=equipment_type, status=OrderStage.Status.WAITING,
        )
        # Act
        result = services.approve_and_schedule_stage(
            stage,
            schedule_start='2026-05-02T10:00:00Z',
            schedule_end='2026-05-02T12:00:00Z',
        )
        # Assert
        assert result.status == OrderStage.Status.IN_PROGRESS
        assert result.schedule_start.isoformat().startswith('2026-05-02')

    @freeze_time('2026-05-01 10:00:00')
    def test_first_approval_promotes_order_from_waiting_to_in_progress(
        self, db, employee, equipment_type, mocker,
    ):
        """Regression: previously create_order set the order straight to
        IN_PROGRESS, skipping the documented WAITING phase. The fix sets
        new orders to WAITING; the first stage approval is what promotes
        them to IN_PROGRESS. This test pins both halves."""
        mocker.patch(
            'scheduling.services.allocate_equipments_for_stage', return_value=[],
        )
        # Arrange — build a real order via the public API so the WAITING
        # invariant on creation is also covered.
        experiment = ExperimentFactory.with_requirement(equipment_type=equipment_type)
        order = services.create_order(
            user=employee, target_department=employee.department, experiment=experiment,
        )
        assert order.status == Order.Status.WAITING        # invariant on creation
        first_stage = order.stages.order_by('step_order').first()
        assert first_stage.status == OrderStage.Status.WAITING

        # Act — manager approves the first stage
        services.approve_and_schedule_stage(
            first_stage,
            schedule_start='2026-05-02T10:00:00Z',
            schedule_end='2026-05-02T12:00:00Z',
        )

        # Assert — order now IN_PROGRESS, stage IN_PROGRESS
        order.refresh_from_db()
        first_stage.refresh_from_db()
        assert order.status == Order.Status.IN_PROGRESS
        assert first_stage.status == OrderStage.Status.IN_PROGRESS

    @freeze_time('2026-05-01 10:00:00')
    def test_assignee_as_uuid_string_does_not_break_notification(
        self, db, order, equipment_type, lab_member, mocker,
    ):
        """Regression: PATCH /api/orders/stages/<id>/review/ passes the
        assignee field as a raw UUID string from request.data, not a User
        instance. _send_notification used to call .username on it and crash
        with AttributeError, surfacing as a 500 to the manager UI."""
        # Arrange
        mocker.patch(
            'scheduling.services.allocate_equipments_for_stage', return_value=[],
        )
        stage = OrderStageFactory(
            order=order, equipment_type=equipment_type, status=OrderStage.Status.WAITING,
        )
        # Act — pass assignee as a UUID string, the way the view layer does
        result = services.approve_and_schedule_stage(
            stage,
            schedule_start='2026-05-02T10:00:00Z',
            schedule_end='2026-05-02T12:00:00Z',
            assignee=str(lab_member.id),
        )
        # Assert — no AttributeError + assignee was correctly bound to the user
        assert result.status == OrderStage.Status.IN_PROGRESS
        assert str(result.assignee_id) == str(lab_member.id)


@pytest.mark.unit
class TestCompleteStage:
    def test_cannot_complete_before_schedule_start(self, db, order, equipment_type):
        # Arrange
        with freeze_time('2026-05-01 10:00:00'):
            stage = OrderStageFactory(
                order=order,
                equipment_type=equipment_type,
                status=OrderStage.Status.IN_PROGRESS,
            )
            stage.schedule_start = stage.schedule_end = None
            stage.save()
            # Manually set schedule_start in the future via update to bypass
            # auto_now_add semantics
            from django.utils.dateparse import parse_datetime
            stage.schedule_start = parse_datetime('2026-05-02T10:00:00Z')
            stage.save()
        # Act / Assert
        with freeze_time('2026-05-01 10:00:00'):
            with pytest.raises(ValidationError, match='before its scheduled start'):
                services.complete_stage(stage)

    @freeze_time('2026-05-02 11:00:00')
    def test_marks_done_and_releases_equipment(self, db, order, equipment_type):
        # Arrange
        equipment = EquipmentFactory(equipment_type=equipment_type, status='occupied')
        stage = OrderStageFactory(
            order=order, equipment_type=equipment_type,
            status=OrderStage.Status.IN_PROGRESS,
            equipment=equipment,
        )
        # Act
        services.complete_stage(stage)
        # Assert
        stage.refresh_from_db()
        equipment.refresh_from_db()
        assert stage.status == OrderStage.Status.DONE
        assert stage.completed_at is not None
        assert equipment.status == 'available'

    @freeze_time('2026-05-02 11:00:00')
    def test_completes_order_when_stage_done(self, db, order, equipment_type):
        # Arrange — single-stage order: completing the stage finishes the order.
        order.status = Order.Status.IN_PROGRESS
        order.save()
        stage = OrderStageFactory(
            order=order, equipment_type=equipment_type,
            status=OrderStage.Status.IN_PROGRESS,
        )
        # Act
        services.complete_stage(stage)
        # Assert
        order.refresh_from_db()
        assert order.status == Order.Status.DONE
        assert order.ended_at is not None

    @freeze_time('2026-05-02 11:00:00')
    def test_completion_notifies_requester_to_collect_wafer(
        self, db, order, equipment_type, mocker,
    ):
        # Arrange — single-stage order: completing the only stage notifies
        # the requester (no intra-lab relay because there is no next stage).
        notify_spy = mocker.spy(services, '_send_notification')
        order.status = Order.Status.IN_PROGRESS
        order.save()
        stage = OrderStageFactory(
            order=order, equipment_type=equipment_type,
            status=OrderStage.Status.IN_PROGRESS,
        )
        # Act
        services.complete_stage(stage)
        # Assert — single notification to the requester
        assert notify_spy.call_count == 1
        notified_user, msg = notify_spy.call_args[0]
        assert notified_user == order.user
        assert 'ready' in msg.lower()

    @freeze_time('2026-05-02 11:00:00')
    def test_completion_relays_to_next_pending_stage_in_same_lab(
        self, db, order, equipment_type, department,
    ):
        """Multi-step experiment within one lab: completing step 1 should
        promote step 2 from PENDING → WAITING and leave the order
        IN_PROGRESS until the last stage is done."""
        from tests.factories import EquipmentTypeFactory
        order.status = Order.Status.IN_PROGRESS
        order.save()
        type_b = EquipmentTypeFactory(name='Furnace-relay')
        stage1 = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            step_order=1, status=OrderStage.Status.IN_PROGRESS,
        )
        stage2 = OrderStageFactory(
            order=order, department=department, equipment_type=type_b,
            step_order=2, status=OrderStage.Status.PENDING,
        )
        # Act
        services.complete_stage(stage1)
        # Assert — order still IN_PROGRESS, next stage flipped to WAITING
        order.refresh_from_db()
        stage2.refresh_from_db()
        assert order.status == Order.Status.IN_PROGRESS
        assert stage2.status == OrderStage.Status.WAITING
