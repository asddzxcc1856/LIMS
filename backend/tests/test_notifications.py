"""Tests for the alert pipeline:
* notify() persists rows + opt-in email channel
* business events generate Notification rows (sign-off, receive, reject, …)
* Equipment status change to maintenance fans out CRITICAL alerts
* /api/monitoring/notifications/ list/summary/mark-read API
"""
import pytest

from equipments.models import Equipment
from monitoring.models import Notification
from monitoring.services import notify, notify_many
from orders import services

from tests.factories import (
    EquipmentFactory,
    LabManagerFactory,
    OrderFactory,
    OrderStageFactory,
    UserFactory,
)


@pytest.mark.unit
class TestNotifyService:
    def test_persists_a_row(self, db, employee):
        n = notify(employee, title='hi', body='hi body')
        assert isinstance(n, Notification)
        assert n.recipient_id == employee.id
        assert n.level == Notification.Level.INFO
        assert Notification.objects.count() == 1

    def test_returns_none_for_missing_recipient(self, db):
        assert notify(None, title='x') is None
        assert Notification.objects.count() == 0

    def test_resolves_user_by_pk(self, db, employee):
        n = notify(str(employee.id), title='hi')
        assert n.recipient_id == employee.id

    def test_notify_many_handles_iterable(self, db, employee, lab_member):
        rows = notify_many([employee, lab_member], title='hi')
        assert len(rows) == 2
        assert Notification.objects.count() == 2


@pytest.mark.integration
class TestBusinessEventFanout:
    def test_signoff_writes_requester_notification(
        self, db, order, department, equipment_type, lab_manager,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status='waiting',
        )
        services.sign_off_stage(stage, actor=lab_manager, comment='ok')
        n = Notification.objects.filter(
            recipient=order.user, kind=Notification.Kind.ORDER_SIGNED_OFF,
        ).first()
        assert n is not None
        assert n.related_order_id == order.id

    def test_reject_writes_warning_for_requester(
        self, db, employee, department, equipment_type, lab_manager,
    ):
        from equipments.models import Experiment
        exp = Experiment.objects.create(name='RejectNotif', department=department)
        order = services.create_order(user=employee, experiment=exp)
        services.reject_order(order, rejection_reason='nope', actor=lab_manager)

        n = Notification.objects.filter(
            recipient=order.user, kind=Notification.Kind.ORDER_REJECTED,
        ).first()
        assert n is not None
        assert n.level == Notification.Level.WARNING
        assert 'nope' in n.body

    def test_receive_writes_notification(
        self, db, employee, department, equipment_type, lab_member,
    ):
        order = OrderFactory(user=employee, department=department)
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status='waiting',
        )
        services.receive_stage(stage, operator=lab_member)
        n = Notification.objects.filter(
            recipient=employee, kind=Notification.Kind.ORDER_RECEIVED,
        ).first()
        assert n is not None


@pytest.mark.integration
class TestEquipmentAlertSignal:
    def test_alert_when_status_goes_to_maintenance(
        self, db, department, equipment_type,
    ):
        manager = LabManagerFactory(department=department)
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        # baseline — creation itself shouldn't emit any alert
        Notification.objects.all().delete()
        # Act — flip status to MAINTENANCE
        eq.status = Equipment.Status.MAINTENANCE
        eq.save()
        # Assert — manager of that department gets a CRITICAL row
        alerts = Notification.objects.filter(
            recipient=manager,
            kind=Notification.Kind.EQUIPMENT_ALERT,
        )
        assert alerts.count() == 1
        assert alerts.first().level == Notification.Level.CRITICAL
        assert alerts.first().related_equipment_id == eq.id

    def test_no_alert_for_normal_transitions(
        self, db, department, equipment_type,
    ):
        manager = LabManagerFactory(department=department)
        eq = EquipmentFactory(
            equipment_type=equipment_type, department=department,
            status=Equipment.Status.AVAILABLE,
        )
        Notification.objects.all().delete()
        # available → occupied → available is normal operation
        eq.status = Equipment.Status.OCCUPIED
        eq.save()
        eq.status = Equipment.Status.AVAILABLE
        eq.save()
        assert Notification.objects.filter(
            recipient=manager, kind=Notification.Kind.EQUIPMENT_ALERT,
        ).count() == 0


@pytest.mark.integration
class TestNotificationAPI:
    def test_list_returns_only_own_rows(self, db, employee_client, employee):
        notify(employee, title='mine')
        other = UserFactory()
        notify(other, title='theirs')
        response = employee_client.get('/api/monitoring/notifications/')
        assert response.status_code == 200
        rows = response.data.get('results') or response.data
        titles = {r['title'] for r in rows}
        assert 'mine' in titles
        assert 'theirs' not in titles

    def test_unread_only_filter(self, db, employee_client, employee):
        n1 = notify(employee, title='read')
        n2 = notify(employee, title='unread')
        n1.is_read = True
        n1.save()
        response = employee_client.get(
            '/api/monitoring/notifications/?unread_only=true',
        )
        rows = response.data.get('results') or response.data
        titles = {r['title'] for r in rows}
        assert titles == {'unread'}

    def test_mark_read(self, db, employee_client, employee):
        n = notify(employee, title='ping')
        response = employee_client.post(
            f'/api/monitoring/notifications/{n.id}/mark-read/',
        )
        assert response.status_code == 200
        n.refresh_from_db()
        assert n.is_read is True
        assert n.read_at is not None

    def test_mark_all_read(self, db, employee_client, employee):
        for _ in range(3):
            notify(employee, title='ping')
        response = employee_client.post(
            '/api/monitoring/notifications/mark-all-read/',
        )
        assert response.status_code == 200
        assert response.data['updated'] == 3
        assert (
            Notification.objects.filter(recipient=employee, is_read=False).count() == 0
        )

    def test_summary(self, db, employee_client, employee):
        notify(employee, title='a')
        notify(employee, title='crit', level=Notification.Level.CRITICAL)
        response = employee_client.get('/api/monitoring/notifications/summary/')
        assert response.status_code == 200
        assert response.data['unread'] == 2
        assert response.data['critical_unread'] == 1

    def test_other_user_cannot_mark_read(self, db, api_client, employee):
        n = notify(employee, title='leak')
        outsider = UserFactory()
        from rest_framework_simplejwt.tokens import RefreshToken
        api_client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(outsider).access_token}',
        )
        response = api_client.post(
            f'/api/monitoring/notifications/{n.id}/mark-read/',
        )
        assert response.status_code == 404
