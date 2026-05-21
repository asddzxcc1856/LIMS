"""Backfill English variants for the seed catalogue.

Maps the zh-TW ``name`` of every seeded Experiment, EquipmentType and
Recipe to its English equivalent. Skips rows whose ``name_en`` is
already populated (e.g. admin manually translated something) so a
re-run is idempotent. Manually-added rows that aren't in these maps
are left untouched — they keep falling back to ``name``.
"""
from django.db import migrations


# ── EquipmentType: zh-TW name → English name ────────────────────────────
EQUIPMENT_TYPE_EN = {
    'EUV Scanner': 'EUV Scanner',
    'Track System': 'Track System',
    'ALD': 'ALD',
    'PVD Sputter': 'PVD Sputter',
    'Furnace': 'Furnace',
    'Dry Etcher': 'Dry Etcher',
    'CMP Polisher': 'CMP Polisher',
    'Wet Bench': 'Wet Bench',
    'Ion Implanter': 'Ion Implanter',
    'CD-SEM': 'CD-SEM',
    'Inspect Tool': 'Defect Inspector',
    'Auto Prober': 'Auto Prober',
}


# ── Experiment: zh-TW name → (English name, English remark) ─────────────
EXPERIMENT_EN = {
    'Full Litho & Metrology Process': (
        'Full Litho & Metrology Process',
        'Lithography flow: photoresist coat → EUV exposure → CD-SEM line-width metrology.',
    ),
    'Surface Planarization & Inspect': (
        'Surface Planarization & Inspect',
        'CMP wafer planarization followed by optical surface inspection.',
    ),
    'Ion Implant + Anneal': (
        'Ion Implant + Anneal',
        'Dopant implantation followed by furnace anneal to activate dopants.',
    ),
    'Metal Deposition + Etch': (
        'Metal Deposition + Etch',
        'PVD metal stack deposition followed by dry-etch patterning.',
    ),
    'Wafer Acceptance Test': (
        'Wafer Acceptance Test',
        'Auto-prober electrical test on the finished wafer.',
    ),
}


# ── Recipe: (equipment_type_name, recipe_name) → (English name, English remark)
# Mirrors the seed table in 0007_seed_recipes.py.
RECIPE_EN = {
    ('EUV Scanner', 'Standard-13.5nm'):
        ('Standard-13.5nm', 'Mainstream production recipe — standard exposure dose.'),
    ('EUV Scanner', 'HighRes-13.5nm'):
        ('HighRes-13.5nm', 'High-resolution / high-dose recipe for tight CD structures.'),
    ('EUV Scanner', 'Test-LowDose'):
        ('Test-LowDose', 'Low-dose validation recipe for small dev batches.'),
    ('EUV Scanner', 'Dev-FocusOffset'):
        ('Dev-FocusOffset', 'Focus-offset tuning for dev-stage process window mapping.'),
    ('EUV Scanner', 'Production-BatchMode'):
        ('Production-BatchMode', 'Long-run production recipe with batch mode enabled for throughput.'),

    ('Track System', 'StdCoat-PR1'):
        ('StdCoat-PR1', 'Standard photoresist coat recipe.'),
    ('Track System', 'ThickResist-PR2'):
        ('ThickResist-PR2', 'Thick-resist recipe for deep-trench structures.'),
    ('Track System', 'ThinResist-Hi-RPM'):
        ('ThinResist-Hi-RPM', 'Thin-film high-RPM coat recipe.'),
    ('Track System', 'AntiReflect-BARC'):
        ('AntiReflect-BARC', 'Bottom anti-reflective coating layer.'),
    ('Track System', 'DevSpin-Strip'):
        ('DevSpin-Strip', 'Post-strip rinse recipe.'),

    ('ALD', 'HfO2-Standard'):
        ('HfO2-Standard', 'High-k HfO2 standard deposition.'),
    ('ALD', 'HfO2-LowTemp'):
        ('HfO2-LowTemp', 'Low-temp HfO2 for temperature-sensitive structures.'),
    ('ALD', 'Al2O3-Standard'):
        ('Al2O3-Standard', 'Aluminium oxide standard recipe.'),
    ('ALD', 'TiN-DiffusionBarrier'):
        ('TiN-DiffusionBarrier', 'TiN diffusion-barrier ALD.'),
    ('ALD', 'SiO2-Capping'):
        ('SiO2-Capping', 'SiO2 capping-layer ALD deposition.'),

    ('PVD Sputter', 'Cu-SeedLayer'):
        ('Cu-SeedLayer', 'Copper seed-layer PVD standard.'),
    ('PVD Sputter', 'TaN-Barrier'):
        ('TaN-Barrier', 'TaN diffusion barrier.'),
    ('PVD Sputter', 'Ti-Underlayer'):
        ('Ti-Underlayer', 'Ti underlayer recipe.'),
    ('PVD Sputter', 'Al-Cap'):
        ('Al-Cap', 'Aluminium capping PVD.'),
    ('PVD Sputter', 'W-LongRun'):
        ('W-LongRun', 'Tungsten long-deposition recipe.'),

    ('Furnace', 'Anneal-N2-Std'):
        ('Anneal-N2-Std', 'Standard N2-ambient anneal.'),
    ('Furnace', 'Anneal-Oxide'):
        ('Anneal-Oxide', 'Thermal oxide growth recipe.'),
    ('Furnace', 'Anneal-LowTemp'):
        ('Anneal-LowTemp', 'Low-temp long-time anneal for metal-interface repair.'),
    ('Furnace', 'RTA-Spike'):
        ('RTA-Spike', 'Rapid thermal anneal spike.'),
    ('Furnace', 'DriveIn-Dopant'):
        ('DriveIn-Dopant', 'Dopant drive-in diffusion.'),

    ('Dry Etcher', 'PolySi-Std'):
        ('PolySi-Std', 'Poly-Si dry-etch standard recipe.'),
    ('Dry Etcher', 'Oxide-Anisotropic'):
        ('Oxide-Anisotropic', 'Anisotropic oxide etch.'),
    ('Dry Etcher', 'Metal-Etch'):
        ('Metal-Etch', 'Metal layer dry-etch.'),
    ('Dry Etcher', 'LightPolish'):
        ('LightPolish', 'Light physical etch / surface planarization.'),
    ('Dry Etcher', 'DeepTrench-Bosch'):
        ('DeepTrench-Bosch', 'Deep-trench Bosch cycle recipe.'),

    ('CMP Polisher', 'Cu-Polish'):
        ('Cu-Polish', 'Cu-process CMP standard recipe.'),
    ('CMP Polisher', 'Oxide-Polish'):
        ('Oxide-Polish', 'Oxide layer CMP recipe.'),
    ('CMP Polisher', 'Tungsten-Polish'):
        ('Tungsten-Polish', 'W layer CMP recipe.'),
    ('CMP Polisher', 'Buff-Step'):
        ('Buff-Step', 'DI-water buff step to clear residual slurry.'),
    ('CMP Polisher', 'EndpointDetect-Cu'):
        ('EndpointDetect-Cu', 'Cu CMP with automatic endpoint detection.'),

    ('Wet Bench', 'SC1-Clean'):
        ('SC1-Clean', 'Organic-removal SC1 clean.'),
    ('Wet Bench', 'SC2-Clean'):
        ('SC2-Clean', 'Metal-ion removal SC2 clean.'),
    ('Wet Bench', 'Piranha-Strip'):
        ('Piranha-Strip', 'Photoresist strip via Piranha.'),
    ('Wet Bench', 'BOE-Strip'):
        ('BOE-Strip', 'Buffered oxide etch (BOE).'),
    ('Wet Bench', 'HF-DiluteDip'):
        ('HF-DiluteDip', 'Diluted HF dip to clear native oxide.'),

    ('Ion Implanter', 'B-LowDose'):
        ('B-LowDose', 'Boron low-dose channel implant.'),
    ('Ion Implanter', 'B-HighDose'):
        ('B-HighDose', 'Boron high-dose source/drain implant.'),
    ('Ion Implanter', 'P-Drain'):
        ('P-Drain', 'NMOS drain phosphorus implant.'),
    ('Ion Implanter', 'As-Source'):
        ('As-Source', 'NMOS source arsenic implant.'),
    ('Ion Implanter', 'BF2-Channel'):
        ('BF2-Channel', 'BF2 shallow junction channel implant.'),

    ('CD-SEM', 'Std-1kV'):
        ('Std-1kV', 'Mainstream production CD measurement.'),
    ('CD-SEM', 'HighRes-0.3kV'):
        ('HighRes-0.3kV', 'High-resolution low-energy recipe for EUV structures.'),
    ('CD-SEM', 'LongRun-Map'):
        ('LongRun-Map', 'Wide-area mapping recipe with fast scan.'),
    ('CD-SEM', 'LineWidth-EdgeAlgo'):
        ('LineWidth-EdgeAlgo', 'Line-width metrology with LE edge algorithm.'),
    ('CD-SEM', 'DenseArray-Compensate'):
        ('DenseArray-Compensate', 'Dense-structure metrology with charge compensation.'),

    ('Inspect Tool', 'BF-Std'):
        ('BF-Std', 'Bright-field standard defect inspection.'),
    ('Inspect Tool', 'DF-Std'):
        ('DF-Std', 'Dark-field standard inspection for particle defects.'),
    ('Inspect Tool', 'HighSens-Scan'):
        ('HighSens-Scan', 'High-sensitivity scan for tiny-defect capture.'),
    ('Inspect Tool', 'FastSurvey'):
        ('FastSurvey', 'Fast survey recipe for coarse screening.'),
    ('Inspect Tool', 'DefectReview-SEM'):
        ('DefectReview-SEM', 'SEM defect-review recipe.'),

    ('Auto Prober', 'WaferFinal-Std'):
        ('WaferFinal-Std', 'Wafer final-test standard plan.'),
    ('Auto Prober', 'E-Test'):
        ('E-Test', 'PCM electrical test.'),
    ('Auto Prober', 'Reliability-BurnIn'):
        ('Reliability-BurnIn', 'High-temp burn-in reliability test.'),
    ('Auto Prober', 'Diode-Char'):
        ('Diode-Char', 'Diode I-V characterization.'),
    ('Auto Prober', 'LongSoak-Stability'):
        ('LongSoak-Stability', 'Long-soak stability test.'),
}


def forwards(apps, schema_editor):
    EquipmentType = apps.get_model('equipments', 'EquipmentType')
    Experiment = apps.get_model('equipments', 'Experiment')
    Recipe = apps.get_model('equipments', 'Recipe')

    for zh_name, en_name in EQUIPMENT_TYPE_EN.items():
        et = EquipmentType.objects.filter(name=zh_name).first()
        if et and not et.name_en:
            et.name_en = en_name
            et.save(update_fields=['name_en'])

    for zh_name, (en_name, en_remark) in EXPERIMENT_EN.items():
        exp = Experiment.objects.filter(name=zh_name).first()
        if exp is None:
            continue
        dirty = []
        if not exp.name_en:
            exp.name_en = en_name
            dirty.append('name_en')
        if not exp.remark_en:
            exp.remark_en = en_remark
            dirty.append('remark_en')
        if dirty:
            exp.save(update_fields=dirty)

    for (type_name, recipe_name), (en_name, en_remark) in RECIPE_EN.items():
        recipe = Recipe.objects.filter(
            equipment_type__name=type_name, name=recipe_name,
        ).first()
        if recipe is None:
            continue
        dirty = []
        if not recipe.name_en:
            recipe.name_en = en_name
            dirty.append('name_en')
        if not recipe.remark_en:
            recipe.remark_en = en_remark
            dirty.append('remark_en')
        if dirty:
            recipe.save(update_fields=dirty)


def reverse(apps, schema_editor):
    """Wipe seeded English variants — preserves anything the admin
    manually typed via the admin UI."""
    EquipmentType = apps.get_model('equipments', 'EquipmentType')
    Experiment = apps.get_model('equipments', 'Experiment')
    Recipe = apps.get_model('equipments', 'Recipe')

    for zh_name, en_name in EQUIPMENT_TYPE_EN.items():
        EquipmentType.objects.filter(name=zh_name, name_en=en_name).update(name_en='')
    for zh_name, (en_name, en_remark) in EXPERIMENT_EN.items():
        Experiment.objects.filter(
            name=zh_name, name_en=en_name,
        ).update(name_en='', remark_en='')
    for (type_name, recipe_name), (en_name, en_remark) in RECIPE_EN.items():
        Recipe.objects.filter(
            equipment_type__name=type_name, name=recipe_name, name_en=en_name,
        ).update(name_en='', remark_en='')


class Migration(migrations.Migration):

    dependencies = [
        ('equipments', '0008_equipmenttype_name_en_experiment_name_en_and_more'),
        ('equipments', '0007_seed_recipes'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
