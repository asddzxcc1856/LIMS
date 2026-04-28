"""
Management command to seed FAB experiment and equipment data.
Usage: python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from equipments.models import Experiment, EquipmentType, Equipment, ExperimentRequiredEquipment


# ── Mapping table from the FAB spec ────────────────────────────────────────
SEED = [
    {
        'experiment': '光阻塗布與顯影參數優化',
        'equipment_type': '軌道式塗布顯影機 (Track System)',
        'quantity': 1,
        'equipment_codes': ['TRACK-001', 'TRACK-002'],
    },
    {
        'experiment': 'EUV 曝光能量校準',
        'equipment_type': '極紫外光曝光機 (EUV Scanner)',
        'quantity': 1,
        'equipment_codes': ['EUV-001', 'EUV-002'],
    },
    {
        'experiment': '關鍵尺寸 CD-SEM 量測',
        'equipment_type': '掃描電子顯微鏡 (CD-SEM)',
        'quantity': 2,
        'equipment_codes': ['CDSEM-001', 'CDSEM-002', 'CDSEM-003'],
    },
    {
        'experiment': '原子層沉積厚度分析',
        'equipment_type': '原子層沉積系統 (ALD)',
        'quantity': 1,
        'equipment_codes': ['ALD-001', 'ALD-002'],
    },
    {
        'experiment': '電漿刻蝕選擇比測試',
        'equipment_type': '乾式刻蝕機 (Dry Etcher)',
        'quantity': 1,
        'equipment_codes': ['ETCH-001', 'ETCH-002'],
    },
    {
        'experiment': '化學機械平坦化評估',
        'equipment_type': '研磨拋光機 (CMP Polisher)',
        'quantity': 1,
        'equipment_codes': ['CMP-001', 'CMP-002'],
    },
    {
        'experiment': '晶圓電性參數抽樣 (WAT)',
        'equipment_type': '自動探針台 (Auto Prober)',
        'quantity': 2,
        'equipment_codes': ['PROBE-001', 'PROBE-002', 'PROBE-003'],
    },
    {
        'experiment': '缺陷自動化檢測分類',
        'equipment_type': '光學缺陷檢查儀 (Inspect Tool)',
        'quantity': 1,
        'equipment_codes': ['INSP-001', 'INSP-002'],
    },
]


class Command(BaseCommand):
    help = 'Seed FAB experiment and equipment data'

    def handle(self, *args, **options):
        created_types = 0
        created_exps = 0
        created_eqs = 0
        created_reqs = 0

        for entry in SEED:
            # Equipment type
            eq_type, c = EquipmentType.objects.get_or_create(name=entry['equipment_type'])
            if c:
                created_types += 1

            # Equipment units
            for code in entry['equipment_codes']:
                _, c = Equipment.objects.get_or_create(
                    code=code,
                    defaults={'equipment_type': eq_type, 'status': Equipment.Status.AVAILABLE},
                )
                if c:
                    created_eqs += 1

            # Experiment
            exp, c = Experiment.objects.get_or_create(name=entry['experiment'])
            if c:
                created_exps += 1

            # Mapping
            _, c = ExperimentRequiredEquipment.objects.get_or_create(
                experiment=exp,
                equipment_type=eq_type,
                defaults={'quantity': entry['quantity']},
            )
            if c:
                created_reqs += 1

        self.stdout.write(self.style.SUCCESS(
            f'Seeded: {created_types} types, {created_eqs} equipments, '
            f'{created_exps} experiments, {created_reqs} requirements'
        ))
