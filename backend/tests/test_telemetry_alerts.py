"""Tests for the three production-readiness features the spec calls out:

1. Charts visible to lab_manager (lab-scoped).
2. 數據蒐集: per-sample telemetry endpoint + auto_close_stalled_samples.
3. 報警系統: equipment status change → manager notification +
   schedule-overrun Celery scan → critical alert.
"""
import datetime as _dt

import pytest
from django.utils import timezone
from freezegun import freeze_time

from equipments.models import Equipment
from monitoring.models import Notification
from orders import services
from orders.models import OrderStage, Sample
from scheduling.tasks import (
    alert_schedule_overruns,
    auto_close_stalled_samples,
)

from tests.factories import (
    EquipmentFactory,
    LabDispatcherFactory,
    LabEngineerFactory,
    LabMemberFactory,
    LabOperatorFactory,
    OrderFactory,
    OrderStageFactory,
    RecipeFactory,
)


@pytest.fixture
def running_sample(db, department, equipment_type, lab_member):
    """Helper — get a Sample into RUNNING status with all upstream chain
    completed. Uses freeze_time around the prep so timestamps land in
    the past relative to the test's clock."""
    order = OrderFactory(department=department)
    OrderStageFactory(
        order=order, department=department, equipment_type=equipment_type,
        status=OrderStage.Status.APPROVED,
    )
    eq = EquipmentFactory(equipment_type=equipment_type, department=department)
    recipe = RecipeFactory(equipment_type=equipment_type, parameters={'temp_C': 250})

    splitter = lab_member  # fixture default = coord
    dispatcher = LabDispatcherFactory(department=department)
    param_setter = LabEngineerFactory(department=department)
    executor = LabOperatorFactory(department=department)

    with freeze_time('2026-05-20 09:00:00'):
        services.split_order(
            order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=splitter,
        )
        sample = order.samples.get(sub_code='A')
        services.dispatch_sample(
            sample, operator=dispatcher,
            equipment=str(eq.id), recipe=str(recipe.id),
            schedule_start='2026-05-21T09:00:00Z',
            schedule_end='2026-05-21T10:00:00Z',
        )
        services.set_sample_parameters(
            sample, operator=param_setter, parameter_overrides={},
            auto_assign=False,
        )
        services.assign_sample(
            sample, operator=param_setter, assignee=executor,
        )

    # Load the sample inside its scheduled window so load_sample's
    # time-lock guard passes (>= schedule_start).
    with freeze_time('2026-05-21 09:15:00'):
        services.load_sample(sample, operator=executor)

    sample.refresh_from_db()
    return sample, executor


@pytest.mark.unit
class TestSampleTelemetry:
    def test_records_measurement_event(self, db, running_sample):
        sample, executor = running_sample
        with freeze_time('2026-05-21 09:30:00'):
            services.record_sample_telemetry(
                sample, operator=executor,
                measurement={'kV': 99.8, 'pressure_mTorr': 12},
            )
        events = sample.order.stages.first().events.filter(event_type='note')
        latest = events.order_by('-occurred_at').first()
        assert latest is not None
        assert latest.measurement == {'kV': 99.8, 'pressure_mTorr': 12}

    def test_finished_flag_auto_closes_sample(self, db, running_sample):
        sample, executor = running_sample
        with freeze_time('2026-05-21 09:55:00'):
            services.record_sample_telemetry(
                sample, operator=executor,
                measurement={'result': 'ok'},
                finished=True,
            )
        sample.refresh_from_db()
        assert sample.status == Sample.Status.DONE
        assert sample.completed_at is not None


@pytest.mark.unit
class TestAutoCloseStalledSamples:
    def test_closes_running_sample_past_schedule_end(self, db, running_sample):
        sample, _executor = running_sample
        # schedule_end = 2026-05-21 10:00:00 — run sweep 30 min later
        with freeze_time('2026-05-21 10:30:00'):
            closed = auto_close_stalled_samples(grace_minutes=5)
        assert str(sample.id) in closed
        sample.refresh_from_db()
        assert sample.status == Sample.Status.DONE

    def test_no_op_inside_grace_window(self, db, running_sample):
        sample, _executor = running_sample
        with freeze_time('2026-05-21 10:02:00'):  # only 2 min over
            closed = auto_close_stalled_samples(grace_minutes=5)
        assert str(sample.id) not in closed
        sample.refresh_from_db()
        assert sample.status == Sample.Status.RUNNING


@pytest.mark.unit
class TestScheduleOverrunAlert:
    def test_fires_critical_notification_to_assignee_and_manager(
        self, db, running_sample, lab_manager,
    ):
        sample, executor = running_sample
        # Clear baseline notifications (split / dispatch / assign all
        # write info-level rows we don't care about for this assertion)
        Notification.objects.all().delete()

        with freeze_time('2026-05-21 11:00:00'):  # 1 hour past schedule_end
            alerted = alert_schedule_overruns(grace_minutes=30)

        assert str(sample.id) in alerted
        # Assignee got an alert
        crit = Notification.objects.filter(
            recipient=executor, level=Notification.Level.CRITICAL,
        )
        assert crit.count() == 1
        assert '超時' in crit.first().title
        # Manager of the lab also got one
        mgr_crit = Notification.objects.filter(
            recipient=lab_manager, level=Notification.Level.CRITICAL,
        )
        assert mgr_crit.count() == 1


@pytest.mark.integration
class TestSampleTelemetryEndpoint:
    def test_only_assignee_can_post_telemetry(
        self, db, running_sample, api_client,
    ):
        sample, executor = running_sample
        # A different lab_member tries → 403
        outsider = LabMemberFactory(department=executor.department)
        from rest_framework_simplejwt.tokens import RefreshToken
        with freeze_time('2026-05-21 09:30:00'):
            api_client.credentials(
                HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(outsider).access_token}',
            )
            response = api_client.post(
                f'/api/orders/samples/{sample.id}/telemetry/',
                {'measurement': {'kV': 100}},
                format='json',
            )
            assert response.status_code == 403

    def test_assignee_can_post_telemetry(
        self, db, running_sample, api_client,
    ):
        sample, executor = running_sample
        from rest_framework_simplejwt.tokens import RefreshToken
        with freeze_time('2026-05-21 09:30:00'):
            api_client.credentials(
                HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(executor).access_token}',
            )
            response = api_client.post(
                f'/api/orders/samples/{sample.id}/telemetry/',
                {'measurement': {'kV': 100}, 'finished': False},
                format='json',
            )
            assert response.status_code == 200


@pytest.mark.integration
class TestSampleAbnormalReport:
    def test_assignee_can_report_abnormal_and_engineer_gets_critical(
        self, db, running_sample, api_client, department,
    ):
        """Operator presses 回報異常 → CRITICAL Notification fans out to
        every engineer-specialty lab_member in the same lab; equipment
        flips to maintenance."""
        sample, executor = running_sample
        engineer = LabEngineerFactory(department=department)
        from rest_framework_simplejwt.tokens import RefreshToken
        with freeze_time('2026-05-21 09:30:00'):
            api_client.credentials(
                HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(executor).access_token}',
            )
            response = api_client.post(
                f'/api/orders/samples/{sample.id}/report-abnormal/',
                {'reason': '腔體壓力超出規格'},
                format='json',
            )
        assert response.status_code == 200, response.data
        # Engineer received CRITICAL notification.
        critical = Notification.objects.filter(
            recipient=engineer, level=Notification.Level.CRITICAL,
        )
        assert critical.exists()
        msg = (critical.first().title + ' ' + critical.first().body)
        assert '腔體壓力超出規格' in msg
        # Equipment was flipped to maintenance.
        eq = Equipment.objects.get(pk=sample.equipment_id)
        assert eq.status == Equipment.Status.MAINTENANCE

    def test_non_assignee_cannot_report_abnormal(
        self, db, running_sample, api_client, department,
    ):
        sample, executor = running_sample
        outsider = LabMemberFactory(department=department)
        from rest_framework_simplejwt.tokens import RefreshToken
        with freeze_time('2026-05-21 09:30:00'):
            api_client.credentials(
                HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(outsider).access_token}',
            )
            response = api_client.post(
                f'/api/orders/samples/{sample.id}/report-abnormal/',
                {'reason': 'whatever'},
                format='json',
            )
            assert response.status_code == 403

    def test_empty_reason_rejected(
        self, db, running_sample, api_client,
    ):
        sample, executor = running_sample
        from rest_framework_simplejwt.tokens import RefreshToken
        with freeze_time('2026-05-21 09:30:00'):
            api_client.credentials(
                HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(executor).access_token}',
            )
            response = api_client.post(
                f'/api/orders/samples/{sample.id}/report-abnormal/',
                {'reason': '   '},
                format='json',
            )
            assert response.status_code == 400


@pytest.mark.integration
class TestEquipmentStatusPatchTriggersAlert:
    def test_manager_patch_to_maintenance_notifies_lab_managers(
        self, db, manager_client, lab_manager, department, equipment_type,
    ):
        eq = EquipmentFactory(
            equipment_type=equipment_type, department=department,
            status=Equipment.Status.AVAILABLE,
        )
        Notification.objects.all().delete()

        response = manager_client.patch(
            f'/api/equipments/{eq.id}/',
            {'status': 'maintenance'},
            format='json',
        )
        assert response.status_code == 200
        # The post_save signal in equipments.signals fans out a CRITICAL
        # equipment_alert to lab_managers of the equipment's department.
        crit = Notification.objects.filter(
            recipient=lab_manager,
            level=Notification.Level.CRITICAL,
            kind=Notification.Kind.EQUIPMENT_ALERT,
        )
        assert crit.count() == 1
        assert eq.code in crit.first().title

    def test_lab_member_cannot_patch_equipment_status(
        self, db, member_client, department, equipment_type,
    ):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        response = member_client.patch(
            f'/api/equipments/{eq.id}/',
            {'status': 'maintenance'},
            format='json',
        )
        assert response.status_code == 403
