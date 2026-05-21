"""Tests for the 分貨系統 (WIP split) Sample model + endpoints."""
import pytest
from rest_framework.exceptions import ValidationError

from orders import services
from orders.models import OrderStage, Sample
from scheduling.models import StageEvent

from tests.factories import (
    EquipmentTypeFactory,
    OrderFactory,
    OrderStageFactory,
    UserFactory,
)


def _seed_approved_stage(order, department, equipment_type=None, **kwargs):
    """split_order's precondition (req 3) needs an approved or active stage
    on the order. Tests use this helper so every spec exercising the split
    path satisfies the gating rule without rewriting fixtures."""
    return OrderStageFactory(
        order=order, department=department,
        equipment_type=equipment_type or EquipmentTypeFactory(),
        status=OrderStage.Status.APPROVED,
        **kwargs,
    )


@pytest.mark.unit
class TestSplitOrderService:
    def test_creates_samples(self, db, order, department, equipment_type, lab_member):
        _seed_approved_stage(order, department, equipment_type)
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

    def test_rejects_split_before_signoff(self, db, order, lab_member):
        # No APPROVED stage exists — split must refuse (req 3).
        with pytest.raises(ValidationError, match='signed off'):
            services.split_order(
                order,
                splits=[{'sub_code': 'A', 'wafer_count': 1}],
                operator=lab_member,
            )

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
        # Split now writes a typed SPLIT event instead of the catch-all
        # NOTE so the activity timeline doesn't mislabel the action.
        events = stage.events.filter(event_type=StageEvent.EventType.SPLIT)
        assert events.exists()
        assert '分貨' in events.first().notes

    def test_empty_splits_rejected(self, db, order, department, equipment_type, lab_member):
        _seed_approved_stage(order, department, equipment_type)
        with pytest.raises(ValidationError, match='At least one split'):
            services.split_order(order, splits=[], operator=lab_member)

    def test_duplicate_sub_code_in_payload_rejected(
        self, db, order, department, equipment_type, lab_member,
    ):
        _seed_approved_stage(order, department, equipment_type)
        with pytest.raises(ValidationError, match='Duplicate sub_code'):
            services.split_order(
                order,
                splits=[
                    {'sub_code': 'A', 'wafer_count': 1},
                    {'sub_code': 'A', 'wafer_count': 1},
                ],
                operator=lab_member,
            )

    def test_invalid_wafer_count_rejected(
        self, db, order, department, equipment_type, lab_member,
    ):
        _seed_approved_stage(order, department, equipment_type)
        with pytest.raises(ValidationError, match='wafer_count'):
            services.split_order(
                order,
                splits=[{'sub_code': 'A', 'wafer_count': 0}],
                operator=lab_member,
            )

    def test_re_split_with_parent(self, db, order, department, equipment_type, lab_member):
        _seed_approved_stage(order, department, equipment_type)
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
        self, db, order, department, equipment_type, lab_member,
    ):
        _seed_approved_stage(order, department, equipment_type)
        Sample.objects.create(order=order, sub_code='A', wafer_count=1)
        with pytest.raises(ValidationError, match='already used'):
            services.split_order(
                order,
                splits=[{'sub_code': 'A', 'wafer_count': 2}],
                operator=lab_member,
            )

    def test_wafer_cap_25_enforced(
        self, db, order, department, equipment_type, lab_member,
        settings,
    ):
        """Total above 25 → reject. Cap-specific tests re-enable the
        flag (conftest turns it off globally for the suite)."""
        settings.LIMS_ENFORCE_WAFER_CAP = True
        _seed_approved_stage(order, department, equipment_type)
        with pytest.raises(ValidationError, match='剛好 25 片'):
            services.split_order(
                order,
                splits=[
                    {'sub_code': 'A', 'wafer_count': 13},
                    {'sub_code': 'B', 'wafer_count': 13},
                ],
                operator=lab_member,
            )

    def test_wafer_cap_25_must_equal_not_below(
        self, db, order, department, equipment_type, lab_member,
        settings,
    ):
        """Total below 25 also rejected — the cap is hard equality."""
        settings.LIMS_ENFORCE_WAFER_CAP = True
        _seed_approved_stage(order, department, equipment_type)
        with pytest.raises(ValidationError, match='剛好 25 片'):
            services.split_order(
                order,
                splits=[{'sub_code': 'A', 'wafer_count': 10}],
                operator=lab_member,
            )

    def test_wafer_cap_25_counts_existing_samples(
        self, db, order, department, equipment_type, lab_member,
        settings,
    ):
        settings.LIMS_ENFORCE_WAFER_CAP = True
        _seed_approved_stage(order, department, equipment_type)
        Sample.objects.create(order=order, sub_code='A', wafer_count=20)
        with pytest.raises(ValidationError, match='剛好 25 片'):
            services.split_order(
                order,
                splits=[{'sub_code': 'B', 'wafer_count': 10}],
                operator=lab_member,
            )

    def test_manager_cannot_split(
        self, db, approved_order, department, lab_manager,
    ):
        """Manager has admin override on dispatch/params but NOT on
        split — that step is reserved for the WIP coordinator."""
        with pytest.raises(ValidationError, match='主管'):
            services.split_order(
                approved_order,
                splits=[{'sub_code': 'A', 'wafer_count': 1}],
                operator=lab_manager,
            )

    def test_wafer_cap_exactly_25_succeeds(
        self, db, order, department, equipment_type, lab_member,
        settings,
    ):
        settings.LIMS_ENFORCE_WAFER_CAP = True
        _seed_approved_stage(order, department, equipment_type)
        services.split_order(
            order,
            splits=[
                {'sub_code': 'A', 'wafer_count': 13},
                {'sub_code': 'B', 'wafer_count': 12},
            ],
            operator=lab_member,
        )
        assert order.samples.count() == 2


@pytest.mark.integration
class TestSampleAPI:
    def test_lab_member_can_split(
        self, db, member_client, lab_member, department, equipment_type,
    ):
        order = OrderFactory(department=department)
        _seed_approved_stage(order, department, equipment_type)
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
        self, db, employee_client, employee, equipment_type, lab_member,
    ):
        order = OrderFactory(user=employee, department=employee.department)
        _seed_approved_stage(order, employee.department, equipment_type)
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
        self, db, superuser_client, order, department, equipment_type, lab_member,
    ):
        _seed_approved_stage(order, department, equipment_type)
        services.split_order(
            order, splits=[{'sub_code': 'A', 'wafer_count': 1}], operator=lab_member,
        )
        response = superuser_client.get('/api/admin/samples/')
        assert response.status_code == 200
        assert response.data['count'] >= 1

    def test_non_admin_blocked(self, manager_client):
        response = manager_client.get('/api/admin/samples/')
        assert response.status_code in (401, 403)
