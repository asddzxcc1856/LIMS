"""Tests for the statistics chart endpoints."""
import datetime as _dt

import pytest
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from orders.models import Order, OrderStage
from scheduling.models import EquipmentBooking, StageEvent
from scheduling.services import record_stage_event

from tests.factories import (
    EquipmentFactory,
    OrderFactory,
    OrderStageFactory,
    RecipeFactory,
    SuperUserFactory,
)


def _auth_client(user):
    """Re-mint a JWT inside the calling test's clock context.

    JWT iat/exp are validated against ``timezone.now()`` — when a test
    uses ``freeze_time`` the token has to be issued *inside* the frozen
    window or simplejwt will treat a real-time-issued token as
    coming from the future and 401 the request.
    """
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
    return client


@pytest.mark.integration
class TestChartEquipmentUtilization:
    def test_blocked_for_non_manager(self, employee_client):
        # Charts are now accessible to lab_manager + superuser. Requesters
        # must NOT see lab-wide utilization.
        response = employee_client.get('/api/monitoring/charts/equipment-utilization/')
        assert response.status_code in (401, 403)

    def test_manager_can_read_lab_scoped_chart(self, manager_client):
        response = manager_client.get('/api/monitoring/charts/equipment-utilization/?days=3')
        assert response.status_code == 200
        assert response.data['days'] == 3

    def test_returns_n_buckets(self, db):
        with freeze_time('2026-05-10 12:00:00'):
            EquipmentFactory()
            client = _auth_client(SuperUserFactory())
            response = client.get('/api/monitoring/charts/equipment-utilization/?days=3')
            assert response.status_code == 200
            assert response.data['days'] == 3
            assert len(response.data['series']) == 3

    def test_computes_overlap_utilization(self, db):
        with freeze_time('2026-05-10 12:00:00'):
            eq = EquipmentFactory()
            order = OrderFactory()
            EquipmentBooking.objects.create(
                order=order, equipment=eq,
                started_at=timezone.make_aware(_dt.datetime(2026, 5, 9, 8, 0)),
                ended_at=timezone.make_aware(_dt.datetime(2026, 5, 9, 14, 0)),
            )
            client = _auth_client(SuperUserFactory())
            response = client.get('/api/monitoring/charts/equipment-utilization/?days=2')
            # The seed-demo migration provisions baseline equipment so we
            # derive the expected percentage from the live count rather than
            # hard-coding 25%.
            from equipments.models import Equipment
            eq_count = Equipment.objects.count()
            expected_pct = round(6 * 3600 / (eq_count * 86400) * 100, 2)
            series = response.data['series']
            assert series[0]['date'] == '2026-05-09'
            assert series[0]['utilization'] == expected_pct
            assert series[0]['busy_hours'] == 6.0
            assert series[1]['utilization'] == 0.0


@pytest.mark.integration
class TestChartOrderTrend:
    def test_blocked_for_non_manager(self, employee_client):
        response = employee_client.get('/api/monitoring/charts/order-trend/')
        assert response.status_code in (401, 403)

    def test_manager_can_read(self, manager_client):
        response = manager_client.get('/api/monitoring/charts/order-trend/?days=3')
        assert response.status_code == 200

    def test_counts_created_and_done_per_day(self, db):
        with freeze_time('2026-05-10 12:00:00'):
            order_today = OrderFactory()
            order_today.status = Order.Status.REJECTED
            order_today.ended_at = timezone.now()
            order_today.save()

            order_yesterday = OrderFactory()
            yesterday = timezone.now() - _dt.timedelta(days=1)
            Order.objects.filter(pk=order_yesterday.pk).update(
                created_at=yesterday,
                ended_at=yesterday,
                status=Order.Status.DONE,
            )

            client = _auth_client(SuperUserFactory())
            response = client.get('/api/monitoring/charts/order-trend/?days=2')
            assert response.status_code == 200
            series = response.data['series']
            assert series[0]['done'] == 1
            assert series[1]['rejected'] == 1


@pytest.mark.integration
class TestChartOperatorActivity:
    def test_blocked_for_non_manager(self, employee_client):
        response = employee_client.get('/api/monitoring/charts/operator-activity/')
        assert response.status_code in (401, 403)

    def test_manager_can_read(self, manager_client):
        response = manager_client.get('/api/monitoring/charts/operator-activity/')
        assert response.status_code == 200

    def test_ranks_operators_by_event_volume(
        self, db, superuser_client, lab_member, lab_manager, order_stage,
    ):
        # Arrange — two events from lab_member, one approval from lab_manager
        record_stage_event(order_stage, event_type='note', operator=lab_member)
        record_stage_event(order_stage, event_type='note', operator=lab_member)
        from orders.models import Approval
        Approval.objects.create(
            stage=order_stage, actor=lab_manager, decision='approved', comment='ok',
        )
        # Act
        response = superuser_client.get(
            '/api/monitoring/charts/operator-activity/?days=30&limit=5',
        )
        # Assert
        series = response.data['series']
        assert series[0]['username'] == lab_member.username
        assert series[0]['events'] == 2
        assert series[1]['username'] == lab_manager.username
        assert series[1]['approvals'] == 1


@pytest.mark.integration
class TestChartOrderBusiness:
    def test_blocked_for_non_manager(self, employee_client):
        response = employee_client.get('/api/monitoring/charts/order-business/')
        assert response.status_code in (401, 403)

    def test_returns_business_blocks(self, manager_client):
        response = manager_client.get('/api/monitoring/charts/order-business/?days=7')
        assert response.status_code == 200
        body = response.data
        for key in (
            'totals', 'order_status', 'stage_status', 'sample_status',
            'lead_times', 'by_equipment_type',
        ):
            assert key in body
        assert isinstance(body['order_status'], list)
        assert {'created', 'done', 'rejected', 'rejection_rate_pct'}.issubset(
            body['totals'].keys(),
        )

    def test_lead_time_computed_for_done_orders(self, db, department):
        from tests.factories import (
            LabManagerFactory, OrderFactory, UserFactory,
        )
        manager = LabManagerFactory(department=department)
        requester = UserFactory(department=department, role='regular_employee')
        # Order ended in DONE 1h after creation
        with freeze_time('2026-05-10 09:00:00'):
            order = OrderFactory(
                user=requester, department=department,
                status=Order.Status.DONE,
            )
        with freeze_time('2026-05-10 10:00:00'):
            order.ended_at = timezone.now()
            order.save(update_fields=['ended_at'])
        with freeze_time('2026-05-10 12:00:00'):
            client = _auth_client(manager)
            response = client.get('/api/monitoring/charts/order-business/?days=3')
        assert response.status_code == 200
        # Mean of one row → 1.0 hour
        assert response.data['lead_times']['mean_hours_done'] == pytest.approx(1.0, rel=0.1)


@pytest.mark.integration
class TestOperatorActivityDetail:
    def test_blocked_for_non_manager(self, employee_client, lab_member):
        response = employee_client.get(
            f'/api/monitoring/charts/operator-activity/{lab_member.id}/',
        )
        assert response.status_code in (401, 403)

    def test_returns_timeline_with_approvals_and_events(
        self, db, department, manager_client, lab_member, order_stage,
    ):
        from orders.models import Approval
        Approval.objects.create(
            stage=order_stage, actor=lab_member,
            decision='approved', comment='lgtm',
        )
        record_stage_event(order_stage, event_type='load', operator=lab_member)
        record_stage_event(order_stage, event_type='unload', operator=lab_member)
        response = manager_client.get(
            f'/api/monitoring/charts/operator-activity/{lab_member.id}/?days=14',
        )
        assert response.status_code == 200
        body = response.data
        kinds = {row['kind'] for row in body['timeline']}
        assert {'approval', 'event'}.issubset(kinds)
        # Newest first
        timestamps = [row['ts'] for row in body['timeline']]
        assert timestamps == sorted(timestamps, reverse=True)
        # Totals tally
        assert body['totals']['load'] == 1
        assert body['totals']['unload'] == 1
        assert body['totals']['approved'] == 1

    def test_manager_cannot_drill_into_foreign_lab(
        self, db, manager_client, fab,
    ):
        from tests.factories import (
            DepartmentFactory, LabMemberFactory,
        )
        other_dept = DepartmentFactory(fab=fab, name='Other-Lab')
        outsider = LabMemberFactory(department=other_dept)
        response = manager_client.get(
            f'/api/monitoring/charts/operator-activity/{outsider.id}/',
        )
        assert response.status_code == 403


@pytest.mark.integration
class TestSampleHistory:
    def test_manager_can_view_lot_history(
        self, db, manager_client, department, equipment_type, lab_manager,
    ):
        from tests.factories import (
            LabCoordFactory, LabDispatcherFactory, LabEngineerFactory,
            LabOperatorFactory,
        )
        from orders.models import Sample, OrderStage
        from orders import services

        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        # 1) Sign-off (manager) — auto-receives.
        services.sign_off_stage(stage, actor=lab_manager, comment='lgtm')
        # 2) Split + dispatch + params with the right specialties.
        coord = LabCoordFactory(department=department)
        dispatcher = LabDispatcherFactory(department=department)
        engineer = LabEngineerFactory(department=department)
        operator = LabOperatorFactory(department=department)
        services.split_order(
            order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=coord,
        )
        sample = order.samples.get(sub_code='A')
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        from tests.factories import RecipeFactory
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        with freeze_time('2026-05-19 09:00:00'):
            services.dispatch_sample(
                sample, operator=dispatcher,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-19T10:00:00Z',
                schedule_end='2026-05-19T11:00:00Z',
            )
            services.set_sample_parameters(
                sample, operator=engineer, parameter_overrides={},
                # auto_assign defaults to True → operator becomes assignee
            )

        sample.refresh_from_db()
        response = manager_client.get(f'/api/monitoring/lot-history/{sample.id}/')
        assert response.status_code == 200, response.data
        body = response.data
        steps = [row['step'] for row in body['timeline']]
        # Must include the major lifecycle stamps (order may vary by ts).
        # split events are only emitted for IN_PROGRESS stages; the
        # test arrange leaves the stage at APPROVED so 'split' is OK
        # to be absent. The other milestones must all show up via
        # the new typed StageEvent rows.
        assert 'approval' in steps
        assert 'receive' in steps
        assert 'dispatch' in steps
        assert 'set_parameters' in steps
        assert 'assign' in steps

    def test_manager_cannot_view_foreign_lab_lot(
        self, db, manager_client, fab, equipment_type,
    ):
        from tests.factories import (
            DepartmentFactory, LabCoordFactory, LabMemberFactory, UserFactory,
        )
        from orders import services

        other_dept = DepartmentFactory(fab=fab, name='Outside-Lab')
        order = OrderFactory(department=other_dept)
        OrderStageFactory(
            order=order, department=other_dept, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        coord = LabCoordFactory(department=other_dept)
        services.split_order(
            order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=coord,
        )
        sample = order.samples.get(sub_code='A')
        response = manager_client.get(f'/api/monitoring/lot-history/{sample.id}/')
        assert response.status_code == 403

    def test_lab_member_can_only_view_samples_they_touched(
        self, db, member_client, lab_member, department, equipment_type,
    ):
        from orders.models import Sample
        from orders import services

        order = OrderFactory(department=department)
        OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        # The fixture's lab_member is the coord; they created the sample.
        services.split_order(
            order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        my_sample = order.samples.get(sub_code='A')
        # A sample they never touched
        other = Sample.objects.create(
            order=order, sub_code='B', wafer_count=1,
            status=Sample.Status.WAITING,
        )
        assert member_client.get(f'/api/monitoring/lot-history/{my_sample.id}/').status_code == 200
        assert member_client.get(f'/api/monitoring/lot-history/{other.id}/').status_code == 403


@pytest.mark.integration
class TestSampleListForReports:
    def test_manager_sees_their_lab_samples(
        self, db, manager_client, department, equipment_type, lab_member,
    ):
        from orders import services
        order = OrderFactory(department=department)
        OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        services.split_order(
            order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        response = manager_client.get('/api/monitoring/lot-history/?days=7')
        assert response.status_code == 200
        sub_codes = {row['sub_code'] for row in response.data['rows']}
        assert 'A' in sub_codes


@pytest.mark.integration
class TestDashboardUtilization24h:
    def test_dashboard_returns_rolling_24h(self, db):
        with freeze_time('2026-05-10 12:00:00'):
            eq = EquipmentFactory()
            order = OrderFactory()
            EquipmentBooking.objects.create(
                order=order, equipment=eq,
                started_at=timezone.now() - _dt.timedelta(hours=12),
                ended_at=timezone.now() - _dt.timedelta(hours=6),
            )
            client = _auth_client(SuperUserFactory())
            response = client.get('/api/monitoring/dashboard/')
            assert response.status_code == 200
            from equipments.models import Equipment
            expected = round(6 * 3600 / (Equipment.objects.count() * 86400) * 100, 2)
            assert response.data['equipment']['utilization_24h'] == expected
