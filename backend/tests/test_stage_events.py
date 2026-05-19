"""Tests for the 上 / 下貨 audit trail (``StageEvent``).

Coverage:
* service-level event creation
* complete_stage auto-appends an UNLOAD event
* list / create API with row-level visibility scoping
* permission gating on POST (assignee or lab manager only)
* admin CRUD on /api/admin/stage-events/
"""
import pytest
from freezegun import freeze_time

from orders import services
from orders.models import OrderStage
from scheduling.models import StageEvent
from scheduling.services import record_stage_event

from tests.factories import (
    EquipmentFactory,
    OrderStageFactory,
    UserFactory,
)


@pytest.mark.unit
class TestRecordStageEvent:
    def test_creates_event_with_stage_context(self, db, order_stage, lab_member, equipment_type, department):
        # Arrange — pin the stage onto a real equipment so the event copies
        # equipment + recipe context.
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        order_stage.equipment = eq
        order_stage.save(update_fields=['equipment'])
        # Act
        event = record_stage_event(
            order_stage,
            event_type='load',
            operator=lab_member,
            notes='Wafer carrier 7 loaded',
        )
        # Assert
        assert event.event_type == 'load'
        assert event.stage_id == order_stage.id
        assert event.equipment_id == eq.id
        assert event.operator_id == lab_member.id
        assert event.notes == 'Wafer carrier 7 loaded'

    def test_unknown_event_type_is_rejected(self, db, order_stage):
        from rest_framework.exceptions import ValidationError
        with pytest.raises(ValidationError, match='Unknown event_type'):
            record_stage_event(order_stage, event_type='bogus')


@pytest.mark.unit
class TestCompleteStageAutoUnload:
    @freeze_time('2026-05-10 10:00:00')
    def test_complete_stage_appends_unload_event(
        self, db, order, department, equipment_type, lab_member,
    ):
        # Arrange — stage in progress (post-dispatch)
        stage = OrderStageFactory(
            order=order,
            department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.IN_PROGRESS,
        )
        # Act
        services.complete_stage(stage, operator=lab_member)
        # Assert
        unload_events = stage.events.filter(event_type=StageEvent.EventType.UNLOAD)
        assert unload_events.count() == 1
        assert unload_events.first().operator_id == lab_member.id

    @freeze_time('2026-05-10 10:00:00')
    def test_complete_stage_does_not_duplicate_unload(
        self, db, order, department, equipment_type, lab_member,
    ):
        # Arrange — stage with a pre-existing UNLOAD event (member already pressed unload)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.IN_PROGRESS,
        )
        record_stage_event(stage, event_type='unload', operator=lab_member)
        # Act
        services.complete_stage(stage, operator=lab_member)
        # Assert — the auto-append is skipped
        assert stage.events.filter(event_type=StageEvent.EventType.UNLOAD).count() == 1


@pytest.mark.integration
class TestStageEventAPI:
    def _stage(self, **kwargs):
        return OrderStageFactory(status=OrderStage.Status.IN_PROGRESS, **kwargs)

    def test_assignee_can_post_load_event(
        self, db, api_client, lab_member, department, equipment_type,
    ):
        # Arrange — stage assigned to lab_member; auth client as them.
        from tests.factories import OrderFactory
        order = OrderFactory(department=department)
        stage = self._stage(
            order=order, department=department, equipment_type=equipment_type,
            assignee=lab_member,
        )
        from rest_framework_simplejwt.tokens import RefreshToken
        api_client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(lab_member).access_token}',
        )
        # Act
        response = api_client.post(
            f'/api/orders/stages/{stage.id}/events/',
            {'event_type': 'load', 'notes': 'carrier 7'},
            format='json',
        )
        # Assert
        assert response.status_code == 201, response.data
        assert response.data['event_type'] == 'load'
        assert stage.events.count() == 1

    def test_other_lab_member_gets_404(
        self, db, api_client, department, equipment_type, fab,
    ):
        # Arrange — stage in dept A, but caller is a lab_member in dept B
        from tests.factories import OrderFactory, DepartmentFactory
        other_dept = DepartmentFactory(fab=fab)
        other_member = UserFactory(department=other_dept, role='lab_member')
        order = OrderFactory(department=department)
        stage = self._stage(
            order=order, department=department, equipment_type=equipment_type,
        )
        from rest_framework_simplejwt.tokens import RefreshToken
        api_client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(other_member).access_token}',
        )
        # Act
        response = api_client.post(
            f'/api/orders/stages/{stage.id}/events/',
            {'event_type': 'load'},
            format='json',
        )
        # Assert — out-of-scope → 404 (row-level scoping leaks no existence)
        assert response.status_code == 404

    def test_unrelated_assignee_gets_403_on_post(
        self, db, manager_client, department, equipment_type, lab_member,
    ):
        # Arrange — stage assigned to some other lab_member; manager is in same lab.
        # manager is allowed (same lab). To trigger 403 we need a user in scope
        # but not assignee/manager — e.g. a different lab_member who's reading.
        # That's covered via row-level filtering returning 404; here we test
        # that a regular employee reading their own order's stage cannot post.
        from tests.factories import OrderFactory
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework.test import APIClient
        requester = UserFactory(department=department, role='regular_employee')
        order = OrderFactory(user=requester, department=department)
        stage = self._stage(order=order, department=department, equipment_type=equipment_type)
        # Use a fresh client to avoid leaking the manager fixture's creds.
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(requester).access_token}',
        )
        # Act — requester sees the row (own order) but is not the assignee.
        response = client.post(
            f'/api/orders/stages/{stage.id}/events/',
            {'event_type': 'note'},
            format='json',
        )
        # Assert
        assert response.status_code == 403

    def test_get_returns_chronological_events(
        self, db, member_client, lab_member, department, equipment_type,
    ):
        # Arrange — stage assigned to lab_member with several events
        from tests.factories import OrderFactory
        order = OrderFactory(department=department)
        stage = self._stage(
            order=order, department=department, equipment_type=equipment_type,
            assignee=lab_member,
        )
        record_stage_event(stage, event_type='load', operator=lab_member, notes='L1')
        record_stage_event(stage, event_type='note', operator=lab_member, notes='N1')
        record_stage_event(stage, event_type='unload', operator=lab_member, notes='U1')
        # Act
        response = member_client.get(f'/api/orders/stages/{stage.id}/events/')
        # Assert
        assert response.status_code == 200
        types = [row['event_type'] for row in response.data]
        # ordering = -occurred_at, so unload (latest) comes first
        assert types == ['unload', 'note', 'load']


@pytest.mark.integration
class TestAdminStageEventCRUD:
    def test_superuser_can_list(self, superuser_client, order_stage, lab_member):
        record_stage_event(order_stage, event_type='load', operator=lab_member)
        response = superuser_client.get('/api/admin/stage-events/')
        assert response.status_code == 200
        assert response.data['count'] >= 1

    def test_non_superuser_blocked(self, manager_client):
        response = manager_client.get('/api/admin/stage-events/')
        assert response.status_code in (401, 403)
