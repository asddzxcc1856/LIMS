"""Tests for the controlled parameter-override and signoff-required
flow added with the dispatch refactor (reqs 2 + 5)."""
import pytest
from freezegun import freeze_time
from rest_framework.exceptions import ValidationError

from orders import services
from orders.models import OrderStage

from tests.factories import (
    EquipmentFactory,
    OrderStageFactory,
    RecipeFactory,
)


@pytest.mark.unit
class TestSignoffRequiredForDispatch:
    @freeze_time('2026-05-01 10:00:00')
    def test_dispatch_on_waiting_stage_auto_records_signoff(
        self, db, order, department, equipment_type, lab_manager, mocker,
    ):
        mocker.patch('scheduling.services.allocate_equipments_for_stage', return_value=None)
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        services.approve_and_schedule_stage(
            stage,
            schedule_start='2026-05-02T10:00:00Z',
            schedule_end='2026-05-02T12:00:00Z',
            actor=lab_manager,
        )
        # Both signoff and dispatch rows land — necessary precondition
        # satisfied even when the combined button is used.
        assert stage.approvals.count() == 2

    @freeze_time('2026-05-01 10:00:00')
    def test_dispatch_on_approved_stage_skips_auto_signoff(
        self, db, order, department, equipment_type, lab_manager, mocker,
    ):
        mocker.patch('scheduling.services.allocate_equipments_for_stage', return_value=None)
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.WAITING,
        )
        services.sign_off_stage(stage, actor=lab_manager)
        stage.refresh_from_db()
        assert stage.status == OrderStage.Status.APPROVED
        # Act
        services.approve_and_schedule_stage(
            stage,
            schedule_start='2026-05-02T10:00:00Z',
            schedule_end='2026-05-02T12:00:00Z',
            actor=lab_manager,
        )
        # Only the dispatch row was added; the original sign-off stays.
        assert stage.approvals.count() == 2


@pytest.mark.unit
class TestParameterOverrides:
    @freeze_time('2026-05-01 10:00:00')
    def test_override_within_recipe_keys_is_persisted(
        self, db, order, department, equipment_type, lab_manager, mocker,
    ):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(
            equipment_type=equipment_type,
            parameters={'temp_C': 250, 'time_sec': 600, 'cycles': 100},
        )
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )

        def fake_allocate(stg, equipment_id=None):
            stg.equipment = eq
            stg.save(update_fields=['equipment'])
        mocker.patch(
            'scheduling.services.allocate_equipments_for_stage',
            side_effect=fake_allocate,
        )

        # Act — override two of the three knobs
        services.approve_and_schedule_stage(
            stage,
            schedule_start='2026-05-02T10:00:00Z',
            schedule_end='2026-05-02T12:00:00Z',
            equipment=str(eq.id),
            recipe=str(recipe.id),
            parameter_overrides={'temp_C': 260, 'cycles': 90},
            actor=lab_manager,
        )
        # Assert
        stage.refresh_from_db()
        assert stage.parameter_overrides == {'temp_C': 260, 'cycles': 90}

    @freeze_time('2026-05-01 10:00:00')
    def test_unknown_key_is_rejected(
        self, db, order, department, equipment_type, lab_manager, mocker,
    ):
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(
            equipment_type=equipment_type,
            parameters={'temp_C': 250, 'time_sec': 600},
        )
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )

        def fake_allocate(stg, equipment_id=None):
            stg.equipment = eq
            stg.save(update_fields=['equipment'])
        mocker.patch(
            'scheduling.services.allocate_equipments_for_stage',
            side_effect=fake_allocate,
        )

        # Act / Assert — fake_voltage is NOT in the recipe schema → reject
        with pytest.raises(ValidationError, match='not defined on recipe'):
            services.approve_and_schedule_stage(
                stage,
                schedule_start='2026-05-02T10:00:00Z',
                schedule_end='2026-05-02T12:00:00Z',
                equipment=str(eq.id),
                recipe=str(recipe.id),
                parameter_overrides={'fake_voltage': 5},
                actor=lab_manager,
            )

    @freeze_time('2026-05-01 10:00:00')
    def test_overrides_without_recipe_rejected(
        self, db, order, department, equipment_type, lab_manager, mocker,
    ):
        mocker.patch('scheduling.services.allocate_equipments_for_stage', return_value=None)
        stage = OrderStageFactory(
            order=order, department=department, equipment_type=equipment_type,
            status=OrderStage.Status.APPROVED,
        )
        with pytest.raises(ValidationError, match='without a Recipe'):
            services.approve_and_schedule_stage(
                stage,
                schedule_start='2026-05-02T10:00:00Z',
                schedule_end='2026-05-02T12:00:00Z',
                parameter_overrides={'temp_C': 999},
                actor=lab_manager,
            )


@pytest.mark.integration
class TestI18nSeed:
    def test_equipment_types_have_english_names(self, db):
        from equipments.models import EquipmentType
        missing = [
            et.name for et in EquipmentType.objects.all() if not et.name_en
        ]
        assert not missing, f'EquipmentType missing name_en: {missing}'

    def test_recipes_have_english_names(self, db):
        from equipments.models import Recipe
        # Seed recipes from 0007 are translated by 0009; tolerate test-only
        # recipes that bypassed seeds by checking the *seeded* names only.
        # We dynamically import via importlib because Python module names
        # cannot start with a digit (0009_backfill_i18n_seed).
        from importlib import import_module
        seed_mod = import_module('equipments.migrations.0009_backfill_i18n_seed')
        seeded_pairs = set(seed_mod.RECIPE_EN.keys())
        for r in Recipe.objects.select_related('equipment_type'):
            key = (r.equipment_type.name, r.name)
            if key in seeded_pairs:
                assert r.name_en, f'Seeded recipe {key} missing name_en'
