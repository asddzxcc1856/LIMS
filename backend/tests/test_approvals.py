"""Tests for the independent sign-off flow (簽核系統).

Coverage:
* sign_off_stage records an Approval row without changing stage status
* approve_and_schedule_stage writes a paired Approval row
* reject_order writes a rejection Approval row + flips stage to REJECTED
* /stages/<id>/approvals/ list visible to requester / member; write gated to manager
* admin CRUD on /api/admin/approvals/
"""
import pytest
from freezegun import freeze_time
from rest_framework.exceptions import ValidationError

from orders import services
from orders.models import Approval, Order, OrderStage

from tests.factories import (
    EquipmentFactory,
    OrderFactory,
    OrderStageFactory,
    RecipeFactory,
    UserFactory,
)


@pytest.mark.unit
class TestSignOffStage:
    def test_signoff_creates_approval_row(self, db, order, department, equipment_type, lab_manager):
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        # Act
        approval = services.sign_off_stage(
            stage, actor=lab_manager, comment='Looks good, schedule later.',
        )
        # Assert — stage stays WAITING; approval row exists
        stage.refresh_from_db()
        assert stage.status == OrderStage.Status.WAITING
        assert approval.decision == Approval.Decision.APPROVED
        assert approval.actor_id == lab_manager.id
        assert approval.comment.startswith('Looks good')

    def test_signoff_blocked_when_stage_not_waiting(
        self, db, order, department, equipment_type, lab_manager,
    ):
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.IN_PROGRESS,
        )
        with pytest.raises(ValidationError, match='Cannot sign off'):
            services.sign_off_stage(stage, actor=lab_manager)


@pytest.mark.unit
class TestApproveAndScheduleWritesApproval:
    @freeze_time('2026-05-01 10:00:00')
    def test_writes_approved_audit_row(
        self, db, order, department, equipment_type, lab_manager, mocker,
    ):
        mocker.patch('scheduling.services.allocate_equipments_for_stage', return_value=None)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        # Act
        services.approve_and_schedule_stage(
            stage,
            schedule_start='2026-05-02T10:00:00Z',
            schedule_end='2026-05-02T12:00:00Z',
            actor=lab_manager,
            comment='Approved with weekly schedule slot.',
        )
        # Assert
        approvals = stage.approvals.all()
        assert approvals.count() == 1
        assert approvals.first().decision == Approval.Decision.APPROVED
        assert approvals.first().actor_id == lab_manager.id


@pytest.mark.unit
class TestRejectWritesApproval:
    def test_rejection_creates_rejected_row_and_flips_stage(
        self, db, employee, department, equipment_type, lab_manager,
    ):
        # Arrange — order in WAITING with one waiting stage
        from equipments.models import Experiment
        experiment = Experiment.objects.create(name='ApprovalReject', department=department)
        order = services.create_order(user=employee, experiment=experiment)
        # Act
        services.reject_order(order, rejection_reason='out of scope', actor=lab_manager)
        # Assert
        order.refresh_from_db()
        assert order.status == Order.Status.REJECTED
        stage = order.stages.first()
        assert stage.status == OrderStage.Status.REJECTED
        approvals = stage.approvals.all()
        assert approvals.count() == 1
        assert approvals.first().decision == Approval.Decision.REJECTED
        assert approvals.first().comment == 'out of scope'


@pytest.mark.integration
class TestApprovalsAPI:
    def test_manager_can_signoff_via_endpoint(
        self, db, manager_client, order, department, equipment_type, lab_manager,
    ):
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        # Act — manager fixture belongs to `department` so same-lab guard passes
        response = manager_client.post(
            f'/api/orders/stages/{stage.id}/approvals/',
            {'decision': 'approved', 'comment': 'looks good'},
            format='json',
        )
        # Assert
        assert response.status_code == 201, response.data
        assert response.data['decision'] == 'approved'
        stage.refresh_from_db()
        # signoff alone does not move stage out of WAITING
        assert stage.status == OrderStage.Status.WAITING

    def test_requester_cannot_signoff(
        self, db, employee_client, employee, equipment_type,
    ):
        order = OrderFactory(user=employee, department=employee.department)
        stage = OrderStageFactory(
            order=order, department=employee.department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        response = employee_client.post(
            f'/api/orders/stages/{stage.id}/approvals/',
            {'decision': 'approved'},
            format='json',
        )
        assert response.status_code == 403

    def test_requester_can_read_own_approvals(
        self, db, employee_client, employee, equipment_type, lab_manager,
    ):
        order = OrderFactory(user=employee, department=employee.department)
        stage = OrderStageFactory(
            order=order, department=employee.department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        services.sign_off_stage(stage, actor=lab_manager, comment='ok')
        # Act
        response = employee_client.get(f'/api/orders/stages/{stage.id}/approvals/')
        # Assert
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['decision'] == 'approved'

    def test_other_lab_member_gets_404(
        self, db, api_client, fab, department, equipment_type,
    ):
        from tests.factories import DepartmentFactory
        other_dept = DepartmentFactory(fab=fab)
        outsider = UserFactory(department=other_dept, role='lab_member')
        order = OrderFactory(department=department)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        from rest_framework_simplejwt.tokens import RefreshToken
        api_client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(outsider).access_token}',
        )
        response = api_client.get(f'/api/orders/stages/{stage.id}/approvals/')
        assert response.status_code == 404

    def test_post_with_reject_decision_is_rejected(
        self, db, manager_client, order, department, equipment_type,
    ):
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        response = manager_client.post(
            f'/api/orders/stages/{stage.id}/approvals/',
            {'decision': 'rejected', 'comment': 'nope'},
            format='json',
        )
        # Reject must go through /review/ — endpoint is signoff-only
        assert response.status_code == 400


@pytest.mark.integration
class TestAdminApprovalCRUD:
    def test_admin_lists_approvals(
        self, db, superuser_client, order, department, equipment_type, lab_manager,
    ):
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        services.sign_off_stage(stage, actor=lab_manager, comment='audit')
        response = superuser_client.get('/api/admin/approvals/')
        assert response.status_code == 200
        assert response.data['count'] >= 1

    def test_non_admin_blocked(self, manager_client):
        response = manager_client.get('/api/admin/approvals/')
        assert response.status_code in (401, 403)
