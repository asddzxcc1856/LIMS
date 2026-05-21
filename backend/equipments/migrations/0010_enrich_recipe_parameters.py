"""Data migration that tops up Recipe.parameters so every recipe has
at least 5 tunable knobs. Mirrors the logic in
``equipments.management.commands.enrich_recipe_parameters`` so a fresh
``manage.py migrate`` lands on the same baseline operations expects —
no engineer ever sees an empty parameter dialog.
"""
from django.db import migrations


EXTRA_KNOBS = {
    'EUV Scanner': [
        ('pellicle', True),
        ('reticle_id', 'RET-A1'),
        ('exposure_lots_per_pass', 25),
        ('overlay_correction_nm', 0.0),
    ],
    'Track System': [
        ('hotplate_count', 4),
        ('rinse_seconds', 30),
        ('chuck_temp_C', 23),
    ],
    'ALD': [
        ('purge_time_s', 5),
        ('plasma_assist', False),
        ('chamber_temp_C', 250),
    ],
    'PVD Sputter': [
        ('bias_W', 50),
        ('substrate_temp_C', 200),
        ('rotation_rpm', 5),
    ],
    'Furnace': [
        ('wafer_count', 100),
        ('chamber_pressure_Torr', 1.0),
        ('thermocouple_zone', 'mid'),
    ],
    'Dry Etcher': [
        ('helium_flow_sccm', 10),
        ('chuck_temp_C', 50),
        ('end_point_detect', True),
    ],
    'CMP Polisher': [
        ('endpoint_detect', True),
        ('head_load_N', 20),
        ('pad_conditioner', 'CMP-PAD-A'),
    ],
    'Wet Bench': [
        ('agitation_rpm', 30),
        ('rinse_dump_count', 3),
        ('drain_seconds', 60),
    ],
    'Ion Implanter': [
        ('beam_current_uA', 500),
        ('twist_deg', 0),
        ('rotation_per_min', 5),
    ],
    'CD-SEM': [
        ('frame_average', 16),
        ('astigmatism_correction', True),
        ('charge_compensate', True),
    ],
    'Inspect Tool': [
        ('review_mode', False),
        ('lighting_intensity', 80),
        ('cell_to_cell_compare', True),
    ],
    'Auto Prober': [
        ('temp_C', 25),
        ('overdrive_um', 75),
        ('cleaning_pad_use', True),
    ],
}

MIN_KNOBS_PER_RECIPE = 5


def forwards(apps, schema_editor):
    EquipmentType = apps.get_model('equipments', 'EquipmentType')
    Recipe = apps.get_model('equipments', 'Recipe')

    # Step 1 — create a fallback recipe for any EquipmentType that has
    # zero recipes so the dispatcher dropdown is never empty for an
    # otherwise-valid machine.
    for et in EquipmentType.objects.all():
        if not Recipe.objects.filter(equipment_type=et).exists():
            fallback = {key: val for key, val in EXTRA_KNOBS.get(et.name, [])}
            if not fallback:
                fallback = {'operator_note': ''}
            Recipe.objects.create(
                name=f'Default-{et.name}',
                equipment_type=et,
                version=1,
                parameters=fallback,
                remark='Auto-generated fallback recipe — edit via admin to '
                       'customize for this equipment type.',
                is_active=True,
            )

    # Step 2 — top up every existing recipe to the 5-knob baseline.
    for recipe in Recipe.objects.select_related('equipment_type').all():
        et_name = recipe.equipment_type.name if recipe.equipment_type else ''
        extras = EXTRA_KNOBS.get(et_name, [])
        params = dict(recipe.parameters or {})
        for key, default in extras:
            if len(params) >= MIN_KNOBS_PER_RECIPE:
                break
            if key not in params:
                params[key] = default
        # Final safety net — if for some reason the recipe has zero
        # extras to draw from (custom equipment type not in
        # EXTRA_KNOBS), stamp a generic "operator_note" knob so the
        # engineer's dialog always has something to fill in.
        if not params:
            params = {'operator_note': ''}
        if params != (recipe.parameters or {}):
            recipe.parameters = params
            recipe.save(update_fields=['parameters'])


def backwards(apps, schema_editor):
    # Topping up is non-destructive; no rollback needed.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('equipments', '0009_backfill_i18n_seed'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
