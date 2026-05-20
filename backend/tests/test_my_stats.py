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

    def test_member_sees_per_phase_counts(
        self, db, member_client, lab_member, department, equipment_type,
    ):
        order = OrderFactory(department=department)
        OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        # Three samples in different phases
        Sample.objects.create(order=order, sub_code='A', wafer_count=1, status=Sample.Status.WAITING)
        Sample.objects.create(order=order, sub_code='B', wafer_count=1, status=Sample.Status.DISPATCHED)
        Sample.objects.create(order=order, sub_code='C', wafer_count=1, status=Sample.Status.PARAMS_SET)
        # Assigned to me, ready to load
        Sample.objects.create(
            order=order, sub_code='D', wafer_count=1,
            status=Sample.Status.READY, assignee=lab_member,
        )

        response = member_client.get('/api/monitoring/my-stats/')
        assert response.status_code == 200
        assert response.data['role'] == 'lab_member'
        cards = {c['key']: c['value'] for c in response.data['cards']}
        assert cards['to_dispatch'] == 1
        assert cards['to_params'] == 1
        assert cards['to_assign'] == 1
        assert cards['my_ready'] == 1

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
