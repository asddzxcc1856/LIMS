"""Top up every Recipe.parameters dict so the process-engineer dialog
always has a full set of knobs to tune.

Production fabs ship a richer parameter sheet per recipe than the demo
seed captured; this command idempotently fills in equipment-type-aware
extras so no machine looks "empty" from the engineer's perspective.
The command never removes existing keys, only adds missing ones.

    python manage.py enrich_recipe_parameters          # apply
    python manage.py enrich_recipe_parameters --dry-run  # report only
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from equipments.models import EquipmentType, Recipe


# Per equipment-type fallback knob list. Each entry is (key, value)
# — the value goes into Recipe.parameters when the key is absent.
# Designed so every recipe ends up with at least 5 distinct knobs in
# the engineer's tuning UI.
EXTRA_KNOBS = {
    # ── Photolithography ────────────────────────────────────────────
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
    # ── Thin Film & Etch ────────────────────────────────────────────
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
    # ── Metrology & Inspection ──────────────────────────────────────
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

# Minimum knobs every recipe must end up with. The command keeps adding
# entries from EXTRA_KNOBS until the recipe's parameter dict reaches
# this size (or we run out of fallback knobs for that type, whichever
# comes first).
MIN_KNOBS_PER_RECIPE = 5


class Command(BaseCommand):
    help = 'Top up Recipe.parameters so every recipe has at least 5 knobs.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report changes without saving.')
        parser.add_argument('--min', type=int, default=MIN_KNOBS_PER_RECIPE,
                            help=f'Minimum knob count per recipe (default '
                                 f'{MIN_KNOBS_PER_RECIPE}).')

    def handle(self, *args, **options):
        dry = options['dry_run']
        min_knobs = max(1, options['min'])
        updated = 0
        skipped = 0
        created_recipes = 0
        with transaction.atomic():
            # Step 1 — guarantee every EquipmentType has ≥ 1 recipe so
            # the dispatch dropdown never shows an empty pick list. This
            # catches admin-created types that weren't in the seed list.
            for et in EquipmentType.objects.all():
                if not Recipe.objects.filter(equipment_type=et).exists():
                    fallback_params = {key: val for key, val in EXTRA_KNOBS.get(et.name, [])}
                    if not fallback_params:
                        fallback_params = {'operator_note': ''}
                    self.stdout.write(
                        f'  {et.name:18} | (no recipes) → creating fallback '
                        f'"Default-{et.name}" with {len(fallback_params)} knobs'
                    )
                    if not dry:
                        Recipe.objects.create(
                            name=f'Default-{et.name}',
                            equipment_type=et,
                            version=1,
                            parameters=fallback_params,
                            remark='Auto-generated fallback recipe — edit via admin to '
                                   'customize for this equipment type.',
                            is_active=True,
                        )
                    created_recipes += 1

            # Step 2 — top up existing recipes to the min-knob floor.
            for recipe in Recipe.objects.select_related('equipment_type').all():
                et_name = recipe.equipment_type.name
                extras = EXTRA_KNOBS.get(et_name, [])
                params = dict(recipe.parameters or {})
                before = len(params)
                # Top up until we hit min_knobs or run out of extras.
                for key, default in extras:
                    if len(params) >= min_knobs:
                        break
                    if key not in params:
                        params[key] = default
                # Last-ditch safety net for custom types not in EXTRA_KNOBS.
                if not params:
                    params = {'operator_note': ''}
                if len(params) > before:
                    self.stdout.write(
                        f'  {et_name:18} | {recipe.name:35} '
                        f'{before} → {len(params)} knobs'
                    )
                    if not dry:
                        recipe.parameters = params
                        recipe.save(update_fields=['parameters'])
                    updated += 1
                else:
                    skipped += 1

        verb = 'Would update' if dry else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'\n{verb} {updated} recipes, created {created_recipes} fallback recipes '
            f'({skipped} already had ≥ {min_knobs} knobs).'
        ))
