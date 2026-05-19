"""Tests for the 分貨系統 (WIP split) Sample model + endpoints."""
import pytest
from rest_framework.exceptions import ValidationError

from orders import services
from orders.models import OrderStage, Sample
from scheduling.models import StageEvent

from tests.factories import (
    OrderFactory,
    OrderStageFactory,
    UserFactory,
)


@pytest.mark.unit
class TestSplitOrderService:
    def test_creates_samples(self, db, order, lab_member):
        result = services.split_order(
            order,
            splits=[
                {'sub_code': 'A', 'wafer_count': 3},
                {'sub_code': 'B', 'wafer_count': 2, 'notes': 'control'},
            ],
            operator=lab_member,
        )
        assert len(result) == 2
        assert order.samples.count() == 2
        b = order.samples.get(sub_code='B')
        assert b.wafer_count == 2
        assert b.notes == 'control'
        assert b.created_by_id == lab_member.id

    def test_writes_audit_event_for_active_stages(
        self, db, order, department, equipment_type, lab_member,
    ):
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.IN_PROGRESS, assignee=lab_member,
        )
        services.split_order(
            order,
            splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        events = stage.events.filter(event_type=StageEvent.EventType.NOTE)
        assert events.exists()
        assert 'Split into WIP groups' in events.first().notes

    def test_empty_splits_rejected(self, db, order, lab_member):
        with pytest.raises(ValidationError, match='At least one split'):
            services.split_order(order, splits=[], operator=lab_member)

    def test_duplicate_sub_code_in_payload_rejected(self, db, order, lab_member):
        with pytest.raises(ValidationError, match='Duplicate sub_code'):
            services.split_order(
                order,
                splits=[
                    {'sub_code': 'A', 'wafer_count': 1},
                    {'sub_code': 'A', 'wafer_count': 1},
                ],
                operator=lab_member,
            )

    def test_invalid_wafer_count_rejected(self, db, order, lab_member):
        with pytest.raises(ValidationError, match='wafer_count'):
            services.split_order(
                order,
                splits=[{'sub_code': 'A', 'wafer_count': 0}],
                operator=lab_member,
            )

    def test_re_split_with_parent(self, db, order, lab_member):
        [parent] = services.split_order(
            order,
            splits=[{'sub_code': 'A', 'wafer_count': 5}],
            operator=lab_member,
        )
        children = services.split_order(
            order,
            splits=[
                {'sub_code': 'A1', 'wafer_count': 2},
                {'sub_code': 'A2', 'wafer_count': 3},
            ],
            operator=lab_member,
            parent_sample=parent,
        )
        assert all(c.parent_sample_id == parent.id for c in children)

    def test_collision_with_existing_sample_rejected(
        self, db, order, lab_member,
    ):
        Sample.objects.create(order=order, sub_code='A', wafer_count=1)
        with pytest.raises(ValidationError, match='already used'):
            services.split_order(
                order,
                splits=[{'sub_code': 'A', 'wafer_count': 2}],
                operator=lab_member,
            )


@pytest.mark.integration
class TestSampleAPI:
    def test_lab_member_can_split(
        self, db, member_client, lab_member, department, equipment_type,
    ):
        order = OrderFactory(department=department)
        response = member_client.post(
            f'/api/orders/{order.id}/samples/',
            {'splits': [
                {'sub_code': 'A', 'wafer_count': 4},
                {'sub_code': 'B', 'wafer_count': 1, 'notes': 'control'},
            ]},
            format='json',
        )
        assert response.status_code == 201, response.data
        assert len(response.data) == 2
        sub_codes = {row['sub_code'] for row in response.data}
        assert sub_codes == {'A', 'B'}

    def test_requester_cannot_split(self, db, employee_client, employee):
        order = OrderFactory(user=employee, department=employee.department)
        response = employee_client.post(
            f'/api/orders/{order.id}/samples/',
            {'splits': [{'sub_code': 'A', 'wafer_count': 1}]},
            format='json',
        )
        assert response.status_code == 403

    def test_requester_can_read_own_samples(
        self, db, employee_client, employee, lab_member,
    ):
        order = OrderFactory(user=employee, department=employee.department)
        services.split_order(
            order,
            splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        response = employee_client.get(f'/api/orders/{order.id}/samples/')
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['sub_code'] == 'A'

    def test_out_of_lab_split_returns_404(
        self, db, api_client, fab, equipment_type,
    ):
        from tests.factories import DepartmentFactory, LabMemberFactory
        other_dept = DepartmentFactory(fab=fab)
        outsider = LabMemberFactory(department=other_dept)
        own_dept = DepartmentFactory(fab=fab)
        order = OrderFactory(department=own_dept)
        from rest_framework_simplejwt.tokens import RefreshToken
        api_client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(outsider).access_token}',
        )
        response = api_client.post(
            f'/api/orders/{order.id}/samples/',
            {'splits': [{'sub_code': 'A', 'wafer_count': 1}]},
            format='json',
        )
        # The outsider is a lab_member in the wrong lab — for_write filter
        # narrows to same lab, so this order is invisible (404).
        assert response.status_code == 404


@pytest.mark.integration
class TestAdminSampleCRUD:
    def test_admin_lists_samples(
        self, db, superuser_client, order, lab_member,
    ):
        services.split_order(
            order, splits=[{'sub_code': 'A', 'wafer_count': 1}], operator=lab_member,
        )
        response = superuser_client.get('/api/admin/samples/')
        assert response.status_code == 200
        assert response.data['count'] >= 1

    def test_non_admin_blocked(self, manager_client):
        response = manager_client.get('/api/admin/samples/')
        assert response.status_code in (401, 403)
