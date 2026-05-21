"""Recipe coverage:

* admin CRUD via /api/admin/recipes/
* lab-scoped GET via /api/equipments/recipes/
* attachment to an OrderStage during approve_and_schedule_stage
* validation: equipment_type mismatch + deactivated recipe + missing equipment
"""
import pytest
from freezegun import freeze_time
from rest_framework.exceptions import ValidationError

from equipments.models import Recipe
from orders import services
from orders.models import OrderStage

from tests.factories import (
    EquipmentFactory,
    EquipmentTypeFactory,
    OrderStageFactory,
    RecipeFactory,
)


@pytest.mark.integration
class TestAdminRecipeCRUD:
    def test_superuser_can_create_recipe(self, superuser_client, equipment_type):
        # Act
        response = superuser_client.post(
            '/api/admin/recipes/',
            {
                'name': 'SEM-Std-100kV',
                'equipment_type': str(equipment_type.id),
                'version': 1,
                'parameters': {'temp': 250, 'time_sec': 600},
                'is_active': True,
            },
            format='json',
        )
        # Assert
        assert response.status_code == 201, response.data
        assert response.data['name'] == 'SEM-Std-100kV'
        assert response.data['parameters'] == {'temp': 250, 'time_sec': 600}
        # created_by is auto-set from the request user
        assert response.data['created_by_username'] is not None

    def test_non_superuser_cannot_list_admin_recipes(self, manager_client):
        response = manager_client.get('/api/admin/recipes/')
        assert response.status_code in (401, 403)

    def test_search_by_name(self, superuser_client, equipment_type):
        RecipeFactory(name='SEM-Std-100kV', equipment_type=equipment_type)
        RecipeFactory(name='AFM-Tap-A', equipment_type=equipment_type)
        # Act
        response = superuser_client.get('/api/admin/recipes/?search=SEM')
        # Assert
        names = {row['name'] for row in response.data['results']}
        assert 'SEM-Std-100kV' in names
        assert 'AFM-Tap-A' not in names

    def test_parameters_must_be_object(self, superuser_client, equipment_type):
        response = superuser_client.post(
            '/api/admin/recipes/',
            {
                'name': 'bad-params',
                'equipment_type': str(equipment_type.id),
                'parameters': 'not-a-dict',
            },
            format='json',
        )
        assert response.status_code == 400
        # custom exception handler nests field errors under "fields"
        assert 'parameters' in response.data.get('fields', response.data)

    def test_duplicate_name_type_version_is_rejected(self, superuser_client, equipment_type):
        RecipeFactory(name='dup', equipment_type=equipment_type, version=1)
        response = superuser_client.post(
            '/api/admin/recipes/',
            {
                'name': 'dup',
                'equipment_type': str(equipment_type.id),
                'version': 1,
                'parameters': {},
            },
            format='json',
        )
        assert response.status_code == 400


@pytest.mark.integration
class TestLabScopedRecipeList:
    """The lab-facing endpoint hides recipes that don't apply to the caller's lab."""

    def test_requester_gets_empty_list(self, employee_client):
        RecipeFactory()
        response = employee_client.get('/api/equipments/recipes/')
        assert response.status_code == 200
        # Endpoint disables pagination (the dispatch dialog reads the
        # full list client-side); the response is therefore a raw list.
        assert response.data == []

    def test_manager_sees_only_in_lab_recipes(self, manager_client, department, lab_manager):
        # Arrange — one recipe whose equipment type has a unit in this lab,
        # one whose equipment type lives in some other lab.
        in_lab_type = EquipmentTypeFactory(name='InLabType')
        out_lab_type = EquipmentTypeFactory(name='OutLabType')
        EquipmentFactory(equipment_type=in_lab_type, department=department)
        EquipmentFactory(equipment_type=out_lab_type)  # different dept
        in_lab_recipe = RecipeFactory(name='in-lab', equipment_type=in_lab_type)
        RecipeFactory(name='out-lab', equipment_type=out_lab_type)
        # Act
        response = manager_client.get('/api/equipments/recipes/')
        # Assert
        names = {row['name'] for row in response.data}
        assert 'in-lab' in names
        assert 'out-lab' not in names
        assert str(in_lab_recipe.id) in {row['id'] for row in response.data}

    def test_inactive_recipes_filtered_by_default(self, manager_client, department):
        eq_type = EquipmentTypeFactory()
        EquipmentFactory(equipment_type=eq_type, department=department)
        RecipeFactory(name='active', equipment_type=eq_type, is_active=True)
        RecipeFactory(name='retired', equipment_type=eq_type, is_active=False)
        # Act
        response = manager_client.get('/api/equipments/recipes/')
        # Assert
        names = {row['name'] for row in response.data}
        assert names == {'active'}

    def test_filter_by_equipment_type(self, manager_client, department):
        wanted_type = EquipmentTypeFactory()
        other_type = EquipmentTypeFactory()
        EquipmentFactory(equipment_type=wanted_type, department=department)
        EquipmentFactory(equipment_type=other_type, department=department)
        RecipeFactory(name='wanted', equipment_type=wanted_type)
        RecipeFactory(name='other', equipment_type=other_type)
        # Act
        response = manager_client.get(
            f'/api/equipments/recipes/?equipment_type={wanted_type.id}',
        )
        # Assert
        names = {row['name'] for row in response.data}
        assert names == {'wanted'}


@pytest.mark.unit
class TestApproveStageWithRecipe:
    @freeze_time('2026-05-01 10:00:00')
    def test_attaches_recipe_to_stage(self, db, order, department, equipment_type, mocker):
        # Arrange — set up a stage waiting for approval and the equipment +
        # recipe the manager will pick.
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type)
        stage = OrderStageFactory(
            order=order,
            department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )

        # Patch allocate to plant the equipment on the stage exactly like the
        # real scheduler does — we're testing the recipe path, not allocation.
        def fake_allocate(stg, equipment_id=None):
            stg.equipment = eq
            stg.save(update_fields=['equipment'])
        mocker.patch(
            'scheduling.services.allocate_equipments_for_stage',
            side_effect=fake_allocate,
        )

        # Act
        services.approve_and_schedule_stage(
            stage,
            schedule_start='2026-05-02T10:00:00Z',
            schedule_end='2026-05-02T12:00:00Z',
            equipment=str(eq.id),
            recipe=str(recipe.id),
        )

        # Assert
        stage.refresh_from_db()
        assert stage.recipe_id == recipe.id

    @freeze_time('2026-05-01 10:00:00')
    def test_recipe_without_equipment_is_rejected(
        self, db, order, department, equipment_type,
    ):
        # Arrange
        recipe = RecipeFactory(equipment_type=equipment_type)
        stage = OrderStageFactory(
            order=order,
            department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        # Act / Assert — picking a recipe with no machine makes no sense
        with pytest.raises(ValidationError, match='machine'):
            services.approve_and_schedule_stage(
                stage,
                schedule_start='2026-05-02T10:00:00Z',
                schedule_end='2026-05-02T12:00:00Z',
                recipe=str(recipe.id),
            )

    @freeze_time('2026-05-01 10:00:00')
    def test_mismatched_equipment_type_is_rejected(
        self, db, order, department, equipment_type, mocker,
    ):
        # Arrange — recipe for type A, equipment of type B
        other_type = EquipmentTypeFactory(name='OtherType')
        eq = EquipmentFactory(equipment_type=other_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )

        def fake_allocate(stg, equipment_id=None):
            stg.equipment = eq
            stg.save(update_fields=['equipment'])
        mocker.patch(
            'scheduling.services.allocate_equipments_for_stage',
            side_effect=fake_allocate,
        )

        # Act / Assert
        with pytest.raises(ValidationError, match='Recipe'):
            services.approve_and_schedule_stage(
                stage,
                schedule_start='2026-05-02T10:00:00Z',
                schedule_end='2026-05-02T12:00:00Z',
                equipment=str(eq.id),
                recipe=str(recipe.id),
            )

    @freeze_time('2026-05-01 10:00:00')
    def test_deactivated_recipe_is_rejected(
        self, db, order, department, equipment_type, mocker,
    ):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, is_active=False)
        stage = OrderStageFactory(
            order=order, department=department,
            equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )

        def fake_allocate(stg, equipment_id=None):
            stg.equipment = eq
            stg.save(update_fields=['equipment'])
        mocker.patch(
            'scheduling.services.allocate_equipments_for_stage',
            side_effect=fake_allocate,
        )

        with pytest.raises(ValidationError, match='deactivated'):
            services.approve_and_schedule_stage(
                stage,
                schedule_start='2026-05-02T10:00:00Z',
                schedule_end='2026-05-02T12:00:00Z',
                equipment=str(eq.id),
                recipe=str(recipe.id),
            )
