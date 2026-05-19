"""Tests for the machine telemetry endpoint and the auto-close Celery task."""
import datetime as _dt

import pytest
from django.utils import timezone
from freezegun import freeze_time

from orders.models import Order, OrderStage
from scheduling.models import StageEvent
from scheduling.tasks import auto_close_stalled_stages
from scheduling.services import record_stage_event

from tests.factories import (
    EquipmentFactory,
    OrderFactory,
    OrderStageFactory,
)


@pytest.mark.integration
class TestTelemetryEndpoint:
    def test_requester_forbidden(self, db, employee_client, equipment_type, department):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        response = employee_client.post(
            f'/api/equipments/{eq.id}/telemetry/',
            {'measurement': {'temp': 100}},
            format='json',
        )
        assert response.status_code == 403

    def test_writes_event_to_active_stage(
        self, db, member_client, department, equipment_type, lab_member,
    ):
        # Arrange — equipment in lab + an active stage pinned to it.
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            equipment=eq,
            assignee=lab_member,
            status=OrderStage.Status.IN_PROGRESS,
        )
        # Act
        response = member_client.post(
            f'/api/equipments/{eq.id}/telemetry/',
            {'measurement': {'temp': 250, 'kV': 30}, 'notes': 'mid-run sample'},
            format='json',
        )
        # Assert
        assert response.status_code == 201, response.data
        stage.refresh_from_db()
        event = stage.events.first()
        assert event is not None
        assert event.measurement == {'temp': 250, 'kV': 30}
        assert event.notes == 'mid-run sample'
        assert response.data['completed'] is False

    def test_finished_flag_closes_stage(
        self, db, member_client, department, equipment_type, lab_member,
    ):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            equipment=eq,
            assignee=lab_member,
            status=OrderStage.Status.IN_PROGRESS,
        )
        # Act
        response = member_client.post(
            f'/api/equipments/{eq.id}/telemetry/',
            {'measurement': {'result': 'ok'}, 'finished': True},
            format='json',
        )
        # Assert — stage closed + unload event appended
        assert response.status_code == 201
        assert response.data['completed'] is True
        stage.refresh_from_db()
        assert stage.status == OrderStage.Status.DONE
        assert stage.events.filter(event_type=StageEvent.EventType.UNLOAD).exists()

    def test_no_active_stage_returns_409(
        self, db, member_client, department, equipment_type,
    ):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        response = member_client.post(
            f'/api/equipments/{eq.id}/telemetry/',
            {'measurement': {}},
            format='json',
        )
        assert response.status_code == 409

    def test_out_of_lab_equipment_404(
        self, db, member_client, fab, equipment_type,
    ):
        from tests.factories import DepartmentFactory
        other_dept = DepartmentFactory(fab=fab)
        eq = EquipmentFactory(equipment_type=equipment_type, department=other_dept)
        response = member_client.post(
            f'/api/equipments/{eq.id}/telemetry/',
            {'measurement': {}},
            format='json',
        )
        assert response.status_code == 404


@pytest.mark.integration
class TestAutoCloseStalledStages:
    def test_no_op_when_nothing_stalled(self, db):
        assert auto_close_stalled_stages() == []

    def test_closes_stage_with_telemetry_past_schedule_end(
        self, db, department, equipment_type, lab_member,
    ):
        with freeze_time('2026-05-15 12:00:00'):
            eq = EquipmentFactory(equipment_type=equipment_type, department=department)
            order = OrderFactory(department=department)
            past_start = timezone.now() - _dt.timedelta(hours=2)
            past_end = timezone.now() - _dt.timedelta(hours=1)
            stage = OrderStageFactory(
                order=order, department=department,
                equipment_type=equipment_type,
                equipment=eq,
                assignee=lab_member,
                status=OrderStage.Status.IN_PROGRESS,
                schedule_start=past_start,
                schedule_end=past_end,
            )
            record_stage_event(stage, event_type='note', operator=lab_member,
                               measurement={'last_seen': 'idle'})
            # Act
            closed = auto_close_stalled_stages(grace_minutes=5)
            # Assert
            assert str(stage.id) in closed
            stage.refresh_from_db()
            assert stage.status == OrderStage.Status.DONE

    def test_skips_stages_inside_grace_window(
        self, db, department, equipment_type, lab_member,
    ):
        with freeze_time('2026-05-15 12:00:00'):
            eq = EquipmentFactory(equipment_type=equipment_type, department=department)
            order = OrderFactory(department=department)
            stage = OrderStageFactory(
                order=order, department=department,
                equipment_type=equipment_type,
                equipment=eq,
                assignee=lab_member,
                status=OrderStage.Status.IN_PROGRESS,
                schedule_start=timezone.now() - _dt.timedelta(minutes=10),
                schedule_end=timezone.now() - _dt.timedelta(minutes=2),
            )
            record_stage_event(stage, event_type='note', operator=lab_member)
            # Act — grace is 5 min, only 2 min past schedule_end
            closed = auto_close_stalled_stages(grace_minutes=5)
            # Assert
            assert str(stage.id) not in closed
            stage.refresh_from_db()
            assert stage.status == OrderStage.Status.IN_PROGRESS

    def test_skips_stages_without_any_telemetry(
        self, db, department, equipment_type, lab_member,
    ):
        with freeze_time('2026-05-15 12:00:00'):
            eq = EquipmentFactory(equipment_type=equipment_type, department=department)
            order = OrderFactory(department=department)
            stage = OrderStageFactory(
                order=order, department=department,
                equipment_type=equipment_type,
                equipment=eq,
                assignee=lab_member,
                status=OrderStage.Status.IN_PROGRESS,
                schedule_start=timezone.now() - _dt.timedelta(hours=2),
                schedule_end=timezone.now() - _dt.timedelta(hours=1),
            )
            # No record_stage_event call.
            closed = auto_close_stalled_stages(grace_minutes=5)
            assert closed == []
            stage.refresh_from_db()
            assert stage.status == OrderStage.Status.IN_PROGRESS
