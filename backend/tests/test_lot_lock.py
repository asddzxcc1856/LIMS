"""Tests for the lot-lock + duplicate-experiment rules + per-type recipes."""
import pytest
from rest_framework.exceptions import ValidationError

from equipments.models import EquipmentType, Recipe
from orders import services
from orders.models import Order

from tests.factories import (
    ExperimentFactory,
    OrderFactory,
    UserFactory,
    WaferLotFactory,
)


@pytest.mark.unit
class TestLotLock:
    def test_active_lot_blocks_new_order(self, db, employee, department):
        # Arrange — first order is still IN_PROGRESS on this lot
        exp = ExperimentFactory(name='ExpA', department=department)
        lot = WaferLotFactory(fab=employee.department.fab)
        OrderFactory(
            user=employee, experiment=exp, lot=lot, department=department,
            status=Order.Status.IN_PROGRESS,
        )
        exp2 = ExperimentFactory(name='ExpB', department=department)
        # Act / Assert
        with pytest.raises(ValidationError, match='locked'):
            services.create_order(user=employee, experiment=exp2, lot=lot)

    def test_waiting_lot_also_blocks(self, db, employee, department):
        exp = ExperimentFactory(name='ExpC', department=department)
        lot = WaferLotFactory(fab=employee.department.fab)
        OrderFactory(
            user=employee, experiment=exp, lot=lot, department=department,
            status=Order.Status.WAITING,
        )
        exp2 = ExperimentFactory(name='ExpD', department=department)
        with pytest.raises(ValidationError, match='locked'):
            services.create_order(user=employee, experiment=exp2, lot=lot)

    def test_done_lot_can_be_reused_for_a_different_experiment(
        self, db, employee, department,
    ):
        # Arrange — old order is DONE so lock lifts; new experiment differs
        exp_old = ExperimentFactory(name='ExpOld', department=department)
        exp_new = ExperimentFactory(name='ExpNew', department=department)
        lot = WaferLotFactory(fab=employee.department.fab)
        OrderFactory(
            user=employee, experiment=exp_old, lot=lot, department=department,
            status=Order.Status.DONE,
        )
        # Act — should succeed because lock is gone and experiment is new
        order = services.create_order(user=employee, experiment=exp_new, lot=lot)
        assert order.status == Order.Status.WAITING
        assert order.lot_id == lot.code

    def test_rejected_lot_can_be_reused(self, db, employee, department):
        exp = ExperimentFactory(name='ExpRej', department=department)
        lot = WaferLotFactory(fab=employee.department.fab)
        OrderFactory(
            user=employee, experiment=exp, lot=lot, department=department,
            status=Order.Status.REJECTED,
        )
        # Same experiment is allowed after a rejection (the wafer never ran)
        order = services.create_order(user=employee, experiment=exp, lot=lot)
        assert order.status == Order.Status.WAITING


@pytest.mark.unit
class TestDuplicateExperiment:
    def test_done_experiment_on_same_lot_is_rejected(
        self, db, employee, department,
    ):
        exp = ExperimentFactory(name='ExpDup', department=department)
        lot = WaferLotFactory(fab=employee.department.fab)
        # Mark first order as DONE on this lot+exp
        OrderFactory(
            user=employee, experiment=exp, lot=lot, department=department,
            status=Order.Status.DONE,
        )
        with pytest.raises(ValidationError, match='already been completed'):
            services.create_order(user=employee, experiment=exp, lot=lot)

    def test_different_experiment_on_same_lot_is_fine(
        self, db, employee, department,
    ):
        exp_a = ExperimentFactory(name='ExpAA', department=department)
        exp_b = ExperimentFactory(name='ExpBB', department=department)
        lot = WaferLotFactory(fab=employee.department.fab)
        OrderFactory(
            user=employee, experiment=exp_a, lot=lot, department=department,
            status=Order.Status.DONE,
        )
        # Different experiment — allowed
        order = services.create_order(user=employee, experiment=exp_b, lot=lot)
        assert order.experiment_id == exp_b.id


@pytest.mark.integration
class TestRecipeSeed:
    """The seed migration provisions 5+ recipes per EquipmentType so the
    dispatch UI never falls back to a single bare default."""

    def test_every_equipment_type_has_at_least_five_recipes(self, db):
        deficient = []
        for et in EquipmentType.objects.all():
            count = Recipe.objects.filter(equipment_type=et, is_active=True).count()
            if count < 5:
                deficient.append((et.name, count))
        assert not deficient, f'Equipment types missing recipes: {deficient}'

    def test_recipes_have_real_parameter_dicts(self, db):
        recipes = Recipe.objects.filter(is_active=True)
        assert recipes.count() >= 5
        # spot-check: parameters are dicts with at least one knob each
        for recipe in recipes:
            assert isinstance(recipe.parameters, dict), (
                f'Recipe {recipe.name} parameters not a dict: {recipe.parameters}'
            )
            assert len(recipe.parameters) >= 1, (
                f'Recipe {recipe.name} has no parameters'
            )


@pytest.mark.integration
class TestWaferLotEndpointAnnotations:
    def test_lot_endpoint_marks_active_lot_as_locked(
        self, db, employee_client, employee, department,
    ):
        exp = ExperimentFactory(name='ExpAnnotate', department=department)
        lot = WaferLotFactory(fab=employee.department.fab)
        OrderFactory(
            user=employee, experiment=exp, lot=lot, department=department,
            status=Order.Status.IN_PROGRESS,
        )
        # Act
        response = employee_client.get('/api/users/wafer-lots/')
        # Assert
        assert response.status_code == 200
        rows = response.data
        target = next((r for r in rows if r['code'] == lot.code), None)
        assert target is not None
        assert target['is_locked'] is True
        assert target['active_order_no'] is not None

    def test_lot_endpoint_lists_completed_experiments(
        self, db, employee_client, employee, department,
    ):
        exp = ExperimentFactory(name='ExpHist', department=department)
        lot = WaferLotFactory(fab=employee.department.fab)
        OrderFactory(
            user=employee, experiment=exp, lot=lot, department=department,
            status=Order.Status.DONE,
        )
        response = employee_client.get('/api/users/wafer-lots/')
        assert response.status_code == 200
        target = next((r for r in response.data if r['code'] == lot.code), None)
        assert target is not None
        names = {row['experiment_name'] for row in target['experiments_done']}
        assert 'ExpHist' in names
        assert target['is_locked'] is False


@pytest.mark.integration
class TestOrderCreateApiSurfacesLockError:
    def test_locked_lot_returns_400_with_helpful_detail(
        self, db, employee_client, employee, department,
    ):
        from equipments.models import Experiment
        from users.models import WaferLot
        exp = Experiment.objects.create(name='ApiExpLock', department=department)
        lot = WaferLot.objects.create(code='LOT-API-LOCK', fab=employee.department.fab)
        OrderFactory(
            user=employee, experiment=exp, lot=lot, department=department,
            status=Order.Status.IN_PROGRESS,
        )
        exp2 = Experiment.objects.create(name='ApiExpLock2', department=department)
        # Act
        response = employee_client.post(
            '/api/orders/create/',
            {
                'experiment': str(exp2.id),
                'lot_id': lot.code,
                'requirements': 'test',
            },
            format='json',
        )
        # Assert
        assert response.status_code == 400
        # The custom exception handler nests field errors under "fields"
        msg = response.data.get('fields', response.data)
        assert 'lot_id' in msg or 'locked' in str(response.data)
