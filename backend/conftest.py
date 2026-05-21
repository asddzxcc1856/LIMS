"""Project-wide pytest fixtures.

Conventions:
    * Each fixture builds the smallest valid object via the per-app factory.
    * Authenticated clients are pre-baked for every role to keep tests AAA-clean.
"""
import pytest
from django.conf import settings
from rest_framework.test import APIClient

from tests.factories import (
    DepartmentFactory,
    EquipmentFactory,
    EquipmentTypeFactory,
    ExperimentFactory,
    FABFactory,
    OrderFactory,
    OrderStageFactory,
    SuperUserFactory,
    UserFactory,
)

# Test suite seeds tiny wafer counts to keep arrange blocks legible;
# the 25-wafer-per-order cap stays an opt-in flag for tests that
# explicitly want to exercise it (they re-enable via override_settings).
settings.LIMS_ENFORCE_WAFER_CAP = False


# ── Domain object fixtures ──────────────────────────────────────────────────

@pytest.fixture
def fab(db):
    return FABFactory()


@pytest.fixture
def department(db, fab):
    return DepartmentFactory(fab=fab)


@pytest.fixture
def employee(db, department):
    return UserFactory(department=department, role='regular_employee')


@pytest.fixture
def lab_manager(db, department):
    return UserFactory(department=department, role='lab_manager')


@pytest.fixture
def lab_member(db, department):
    # Default the generic ``lab_member`` fixture to a Coordinator since
    # the most common test action is 分貨 (split). Tests that drive
    # 派工 / 設定參數 / 指派 should pull from the dedicated fixtures
    # below — the workflow gate now enforces 各司其職.
    return UserFactory(
        department=department, role='lab_member',
        lab_specialty='coord',
    )


@pytest.fixture
def lab_dispatcher(db, department):
    return UserFactory(
        department=department, role='lab_member',
        lab_specialty='dispatcher',
    )


@pytest.fixture
def lab_engineer(db, department):
    return UserFactory(
        department=department, role='lab_member',
        lab_specialty='engineer',
    )


@pytest.fixture
def lab_operator(db, department):
    return UserFactory(
        department=department, role='lab_member',
        lab_specialty='operator',
    )


@pytest.fixture
def superuser(db):
    return SuperUserFactory()


@pytest.fixture
def equipment_type(db):
    return EquipmentTypeFactory()


@pytest.fixture
def equipment(db, equipment_type, department):
    return EquipmentFactory(equipment_type=equipment_type, department=department)


@pytest.fixture
def experiment(db, equipment_type):
    return ExperimentFactory.with_requirement(equipment_type=equipment_type)


@pytest.fixture
def order(db, employee, experiment, department):
    return OrderFactory(user=employee, experiment=experiment, department=department)


@pytest.fixture
def order_stage(db, order, department, equipment_type):
    return OrderStageFactory(
        order=order, department=department, equipment_type=equipment_type,
    )


@pytest.fixture
def approved_order(db, order, department, equipment_type):
    """Order with an APPROVED OrderStage — ready for split."""
    from orders.models import OrderStage
    OrderStageFactory(
        order=order, department=department, equipment_type=equipment_type,
        status=OrderStage.Status.APPROVED,
    )
    return order


# ── HTTP client fixtures ────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    """Unauthenticated DRF test client."""
    return APIClient()


def _auth(client, user):
    from rest_framework_simplejwt.tokens import RefreshToken
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
    return client


@pytest.fixture
def employee_client(api_client, employee):
    return _auth(api_client, employee)


@pytest.fixture
def manager_client(api_client, lab_manager):
    return _auth(api_client, lab_manager)


@pytest.fixture
def member_client(api_client, lab_member):
    return _auth(api_client, lab_member)


@pytest.fixture
def superuser_client(api_client, superuser):
    return _auth(api_client, superuser)
