"""Role-aware /api/monitoring/my-stats/ endpoint.

Each role gets its own card set so the home dashboard shows whatever
that user needs to act on (vs the all-system numbers on the admin view).
"""
import pytest

from orders.models import OrderStage, Sample

from tests.factories import OrderFactory, OrderStageFactory


@pytest.mark.integration
class TestMyStatsEndpoint:
    def test_manager_sees_waiting_signoff_count(
        self, db, manager_client, department, equipment_type,
    ):
        # Two stages waiting for signoff in the manager's lab
        for _ in range(2):
            OrderStageFactory(
                order=OrderFactory(department=department),
                department=department,
                equipment_type=equipment_type,
                status=OrderStage.Status.WAITING,
            )
        # One in another lab — should be excluded
        from tests.factories import DepartmentFactory
        other_dept = DepartmentFactory(fab=department.fab)
        OrderStageFactory(
            order=OrderFactory(department=other_dept),
            department=other_dept,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )

        response = manager_client.get('/api/monitoring/my-stats/')
        assert response.status_code == 200
        assert response.data['role'] == 'lab_manager'
        cards = {c['key']: c['value'] for c in response.data['cards']}
        assert cards['waiting_signoff'] == 2

    def test_member_sees_specialty_scoped_card(
        self, db, api_client, department, equipment_type,
    ):
        """Each lab_member only sees the card matching their own
        specialty. A coordinator sees 待分貨; a dispatcher sees 待派工;
        an engineer sees 待設定參數; an operator sees their own queue.
        """
        from tests.factories import (
            LabCoordFactory, LabDispatcherFactory,
            LabEngineerFactory, LabOperatorFactory,
        )
        from rest_framework_simplejwt.tokens import RefreshToken

        order = OrderFactory(department=department)
        OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        Sample.objects.create(order=order, sub_code='A', wafer_count=1, status=Sample.Status.WAITING)
        Sample.objects.create(order=order, sub_code='B', wafer_count=1, status=Sample.Status.DISPATCHED)

        def _hit(user):
            client = api_client.__class__()
            client.credentials(
                HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}',
            )
            return client.get('/api/monitoring/my-stats/').data

        coord = LabCoordFactory(department=department)
        dispatcher = LabDispatcherFactory(department=department)
        engineer = LabEngineerFactory(department=department)
        operator = LabOperatorFactory(department=department)

        coord_keys = {c['key'] for c in _hit(coord)['cards']}
        dispatch_keys = {c['key'] for c in _hit(dispatcher)['cards']}
        engineer_keys = {c['key'] for c in _hit(engineer)['cards']}
        operator_keys = {c['key'] for c in _hit(operator)['cards']}

        assert coord_keys == {'to_split'}
        assert dispatch_keys == {'to_dispatch'}
        assert engineer_keys == {'to_params'}
        assert operator_keys == {'my_ready', 'my_running', 'my_done'}
        # The removed 待指派 card must not appear anywhere.
        assert 'to_assign' not in coord_keys | dispatch_keys | engineer_keys | operator_keys

    def test_employee_sees_own_order_breakdown(
        self, db, employee_client, employee, department,
    ):
        OrderFactory(user=employee, department=department, status='waiting')
        OrderFactory(user=employee, department=department, status='done')
        # Another requester's order — must NOT be counted
        from tests.factories import UserFactory
        other = UserFactory(department=department)
        OrderFactory(user=other, department=department, status='done')

        response = employee_client.get('/api/monitoring/my-stats/')
        assert response.status_code == 200
        assert response.data['role'] == 'regular_employee'
        cards = {c['key']: c['value'] for c in response.data['cards']}
        assert cards['waiting'] == 1
        assert cards['done'] == 1
