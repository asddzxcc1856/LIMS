"""Tests for the 接件 step (lab receives the wafer)."""
import pytest
from rest_framework.exceptions import ValidationError

from orders import services
from orders.models import OrderStage
from scheduling.models import StageEvent

from tests.factories import (
    OrderFactory,
    OrderStageFactory,
    UserFactory,
)


@pytest.mark.unit
class TestReceiveStageService:
    def test_marks_stage_received_with_event(
        self, db, order, department, equipment_type, lab_member,
    ):
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        # Act
        services.receive_stage(stage, operator=lab_member)
        # Assert — stage timestamps + paired audit event
        stage.refresh_from_db()
        assert stage.received_at is not None
        assert stage.received_by_id == lab_member.id
        assert stage.events.filter(event_type=StageEvent.EventType.RECEIVE).count() == 1

    def test_double_receive_is_rejected(
        self, db, order, department, equipment_type, lab_member,
    ):
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        services.receive_stage(stage, operator=lab_member)
        with pytest.raises(ValidationError, match='already received'):
            services.receive_stage(stage, operator=lab_member)

    def test_cannot_receive_in_progress_stage(
        self, db, order, department, equipment_type, lab_member,
    ):
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.IN_PROGRESS,
        )
        with pytest.raises(ValidationError, match='Cannot receive'):
            services.receive_stage(stage, operator=lab_member)


@pytest.mark.integration
class TestReceiveStageAPI:
    """接件 is now folded into the manager's 簽核 step; the standalone
    receive endpoint stays available as a manager-only fallback for the
    rare case where a stage was created without going through sign-off
    (e.g. legacy data, admin tools). lab_members no longer have access."""

    def test_manager_can_receive(
        self, db, manager_client, lab_manager, department, equipment_type,
    ):
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        response = manager_client.post(
            f'/api/orders/stages/{stage.id}/receive/',
            {'notes': 'sample arrived'},
            format='json',
        )
        assert response.status_code == 200, response.data
        stage.refresh_from_db()
        assert stage.received_at is not None
        assert stage.received_by_id == lab_manager.id

    def test_lab_member_cannot_receive(
        self, db, member_client, department, equipment_type,
    ):
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        response = member_client.post(
            f'/api/orders/stages/{stage.id}/receive/', {}, format='json',
        )
        assert response.status_code == 403
        assert '主管' in response.data['detail']

    def test_requester_cannot_receive(
        self, db, employee_client, employee, equipment_type,
    ):
        order = OrderFactory(user=employee, department=employee.department)
        stage = OrderStageFactory(
            order=order, department=employee.department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        response = employee_client.post(
            f'/api/orders/stages/{stage.id}/receive/', {}, format='json',
        )
        assert response.status_code == 403

    def test_double_receive_returns_400(
        self, db, manager_client, department, equipment_type,
    ):
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        manager_client.post(f'/api/orders/stages/{stage.id}/receive/', {}, format='json')
        response = manager_client.post(
            f'/api/orders/stages/{stage.id}/receive/', {}, format='json',
        )
        assert response.status_code == 400
        assert 'already received' in response.data['detail']

    def test_signoff_auto_stamps_received(
        self, db, lab_manager, department, equipment_type,
    ):
        """簽核 should now leave the receive fields populated as a
        side-effect — the lab no longer needs a separate 接件 click."""
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        services.sign_off_stage(stage, actor=lab_manager, comment='ok')
        stage.refresh_from_db()
        assert stage.received_at is not None
        assert stage.received_by_id == lab_manager.id
        # And the audit event was appended.
        assert stage.events.filter(event_type=StageEvent.EventType.RECEIVE).count() == 1
