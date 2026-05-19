"""Tests for the statistics chart endpoints."""
import datetime as _dt

import pytest
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from orders.models import Order
from scheduling.models import EquipmentBooking, StageEvent
from scheduling.services import record_stage_event

from tests.factories import (
    EquipmentFactory,
    OrderFactory,
    OrderStageFactory,
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
    def test_requires_superuser(self, manager_client):
        response = manager_client.get('/api/monitoring/charts/equipment-utilization/')
        assert response.status_code in (401, 403)

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
    def test_requires_superuser(self, manager_client):
        response = manager_client.get('/api/monitoring/charts/order-trend/')
        assert response.status_code in (401, 403)

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
    def test_requires_superuser(self, manager_client):
        response = manager_client.get('/api/monitoring/charts/operator-activity/')
        assert response.status_code in (401, 403)

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
