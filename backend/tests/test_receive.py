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
    def test_lab_member_can_receive(
        self, db, member_client, lab_member, department, equipment_type,
    ):
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        # Act
        response = member_client.post(
            f'/api/orders/stages/{stage.id}/receive/',
            {'notes': 'sample arrived'},
            format='json',
        )
        # Assert
        assert response.status_code == 200, response.data
        stage.refresh_from_db()
        assert stage.received_at is not None
        assert stage.received_by_id == lab_member.id

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
            f'/api/orders/stages/{stage.id}/receive/',
            {},
            format='json',
        )
        assert response.status_code == 403

    def test_other_lab_member_gets_404(
        self, db, api_client, fab, department, equipment_type,
    ):
        from tests.factories import DepartmentFactory
        outsider = UserFactory(department=DepartmentFactory(fab=fab), role='lab_member')
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        from rest_framework_simplejwt.tokens import RefreshToken
        api_client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(outsider).access_token}',
        )
        response = api_client.post(f'/api/orders/stages/{stage.id}/receive/', {}, format='json')
        # row-level scoping — outside lab → 404
        assert response.status_code == 404

    def test_double_receive_returns_400(
        self, db, member_client, lab_member, department, equipment_type,
    ):
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        member_client.post(f'/api/orders/stages/{stage.id}/receive/', {}, format='json')
        response = member_client.post(
            f'/api/orders/stages/{stage.id}/receive/', {}, format='json',
        )
        assert response.status_code == 400
        assert 'already received' in response.data['detail']

    def test_stage_serializer_exposes_received_at(
        self, db, member_client, lab_member, department, equipment_type,
    ):
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
            assignee=lab_member,
        )
        # Receive it then read back via the list endpoint
        member_client.post(f'/api/orders/stages/{stage.id}/receive/', {}, format='json')
        response = member_client.get('/api/orders/stages/')
        # The stage is assigned to the lab_member so it's in scope.
        assert response.status_code == 200
        rows = response.data.get('results') or response.data
        target = next((r for r in rows if r['id'] == str(stage.id)), None)
        assert target is not None
        assert target['received_at'] is not None
        assert target['received_by_username'] == lab_member.username
