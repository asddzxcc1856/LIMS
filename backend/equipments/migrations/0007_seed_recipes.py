"""Seed five (or more) recipes for every EquipmentType.

Recipe.parameters captures a realistic-looking knob set per equipment
family so the dispatch UI lets the manager pick between *meaningful*
variants instead of a single bare default. Numbers are illustrative — a
real fab would version-control these via process engineering. Idempotent
via get_or_create on (name, equipment_type, version).
"""
from django.db import migrations


RECIPES = {
    # ── Photolithography ─────────────────────────────────────────────────
    'EUV Scanner': [
        ('Standard-13.5nm', 1, {
            'wavelength_nm': 13.5, 'dose_mJ_cm2': 30, 'focus_offset_nm': 0,
            'scan_speed': 'normal',
        }, '主流量產 recipe — 標準曝光劑量。'),
        ('HighRes-13.5nm', 1, {
            'wavelength_nm': 13.5, 'dose_mJ_cm2': 40, 'focus_offset_nm': 0,
            'scan_speed': 'slow', 'pellicle': True,
        }, '高解析度高劑量配方,適合最緊 CD 結構。'),
        ('Test-LowDose', 1, {
            'wavelength_nm': 13.5, 'dose_mJ_cm2': 20, 'focus_offset_nm': 0,
            'scan_speed': 'fast',
        }, '低劑量驗證測試,僅用於小批驗證。'),
        ('Dev-FocusOffset', 1, {
            'wavelength_nm': 13.5, 'dose_mJ_cm2': 35, 'focus_offset_nm': 5,
            'scan_speed': 'normal',
        }, '焦深微調 recipe,Dev 階段 process window 量測。'),
        ('Production-BatchMode', 1, {
            'wavelength_nm': 13.5, 'dose_mJ_cm2': 32, 'focus_offset_nm': 0,
            'scan_speed': 'normal', 'batch_mode': True,
        }, '量產長時間連跑 recipe,啟用 batch mode 提高吞吐。'),
    ],
    'Track System': [
        ('StdCoat-PR1', 1, {
            'resist': 'PR-1', 'spin_rpm': 3000, 'bake_temp_C': 110,
            'bake_time_s': 60, 'edge_bead_rem': True,
        }, '標準光阻塗佈 recipe。'),
        ('ThickResist-PR2', 1, {
            'resist': 'PR-2', 'spin_rpm': 1500, 'bake_temp_C': 120,
            'bake_time_s': 90, 'edge_bead_rem': True,
        }, '厚膜光阻配方,適合深溝結構。'),
        ('ThinResist-Hi-RPM', 1, {
            'resist': 'PR-1', 'spin_rpm': 4500, 'bake_temp_C': 100,
            'bake_time_s': 45, 'edge_bead_rem': True,
        }, '薄膜光阻高轉速配方。'),
        ('AntiReflect-BARC', 1, {
            'resist': 'BARC-A', 'spin_rpm': 2500, 'bake_temp_C': 170,
            'bake_time_s': 60, 'edge_bead_rem': False,
        }, '底層抗反射塗佈。'),
        ('DevSpin-Strip', 1, {
            'resist': 'Strip', 'spin_rpm': 2000, 'bake_temp_C': 80,
            'bake_time_s': 30, 'edge_bead_rem': False,
        }, '光阻去除後沖洗 recipe。'),
    ],
    # ── Thin Film & Etch ─────────────────────────────────────────────────
    'ALD': [
        ('HfO2-Standard', 1, {
            'material': 'HfO2', 'temp_C': 250, 'cycles': 100,
            'pressure_Torr': 1.0, 'precursor': 'TEMAH+H2O',
        }, '高介電質 HfO2 標準鍍膜。'),
        ('HfO2-LowTemp', 1, {
            'material': 'HfO2', 'temp_C': 200, 'cycles': 150,
            'pressure_Torr': 0.8, 'precursor': 'TEMAH+H2O',
        }, '低溫 HfO2 配方,適合溫敏結構。'),
        ('Al2O3-Standard', 1, {
            'material': 'Al2O3', 'temp_C': 200, 'cycles': 80,
            'pressure_Torr': 1.0, 'precursor': 'TMA+H2O',
        }, '鋁氧化物標準配方。'),
        ('TiN-DiffusionBarrier', 1, {
            'material': 'TiN', 'temp_C': 350, 'cycles': 60,
            'pressure_Torr': 1.2, 'precursor': 'TDMAT+NH3',
        }, '擴散障壁層 TiN 鍍膜。'),
        ('SiO2-Capping', 1, {
            'material': 'SiO2', 'temp_C': 280, 'cycles': 120,
            'pressure_Torr': 1.0, 'precursor': 'BDEAS+O3',
        }, 'SiO2 封蓋層 ALD 沉積。'),
    ],
    'PVD Sputter': [
        ('Cu-SeedLayer', 1, {
            'material': 'Cu', 'power_kW': 5.0, 'ar_flow_sccm': 30,
            'time_s': 120, 'target_thickness_nm': 50,
        }, '銅 seed 層 PVD 標準配方。'),
        ('TaN-Barrier', 1, {
            'material': 'TaN', 'power_kW': 6.0, 'ar_flow_sccm': 25,
            'n2_flow_sccm': 5, 'time_s': 60,
        }, '鉭氮化物障壁層。'),
        ('Ti-Underlayer', 1, {
            'material': 'Ti', 'power_kW': 4.5, 'ar_flow_sccm': 35,
            'time_s': 90, 'target_thickness_nm': 20,
        }, '鈦底層配方。'),
        ('Al-Cap', 1, {
            'material': 'Al', 'power_kW': 5.5, 'ar_flow_sccm': 30,
            'time_s': 180, 'target_thickness_nm': 200,
        }, '鋁封蓋層 PVD。'),
        ('W-LongRun', 1, {
            'material': 'W', 'power_kW': 7.0, 'ar_flow_sccm': 28,
            'time_s': 300, 'target_thickness_nm': 300,
        }, '鎢長時間沉積配方。'),
    ],
    'Furnace': [
        ('Anneal-N2-Std', 1, {
            'gas': 'N2', 'temp_C': 800, 'time_min': 30,
            'ramp_rate_C_per_min': 10,
        }, 'N2 環境標準退火。'),
        ('Anneal-Oxide', 1, {
            'gas': 'O2/H2O', 'temp_C': 1000, 'time_min': 60,
            'ramp_rate_C_per_min': 8,
        }, '熱氧化層生長 recipe。'),
        ('Anneal-LowTemp', 1, {
            'gas': 'N2', 'temp_C': 400, 'time_min': 120,
            'ramp_rate_C_per_min': 5,
        }, '低溫長時間退火,適合金屬界面修復。'),
        ('RTA-Spike', 1, {
            'gas': 'Ar', 'temp_C': 1050, 'time_min': 0.5,
            'ramp_rate_C_per_min': 100, 'mode': 'RTA',
        }, '快速尖峰退火 RTA。'),
        ('DriveIn-Dopant', 1, {
            'gas': 'N2', 'temp_C': 950, 'time_min': 45,
            'ramp_rate_C_per_min': 8,
        }, '摻雜物 drive-in 擴散。'),
    ],
    'Dry Etcher': [
        ('PolySi-Std', 1, {
            'gas': 'Cl2/HBr', 'power_W': 600, 'pressure_mTorr': 10, 'time_s': 60,
        }, '多晶矽乾蝕刻標準配方。'),
        ('Oxide-Anisotropic', 1, {
            'gas': 'CF4/CHF3', 'power_W': 800, 'pressure_mTorr': 20, 'time_s': 90,
        }, '氧化物異向性蝕刻。'),
        ('Metal-Etch', 1, {
            'gas': 'Cl2/BCl3', 'power_W': 700, 'pressure_mTorr': 8, 'time_s': 75,
        }, '金屬層乾蝕刻 recipe。'),
        ('LightPolish', 1, {
            'gas': 'Ar/O2', 'power_W': 400, 'pressure_mTorr': 30, 'time_s': 30,
        }, '輕度物理蝕刻 / 表面平整。'),
        ('DeepTrench-Bosch', 1, {
            'gas': 'SF6/C4F8', 'power_W': 1000, 'pressure_mTorr': 15,
            'time_s': 300, 'mode': 'Bosch',
        }, '深溝蝕刻 Bosch 循環 recipe。'),
    ],
    'CMP Polisher': [
        ('Cu-Polish', 1, {
            'slurry': 'Cu-SLR-A', 'pressure_psi': 4, 'time_min': 2, 'table_rpm': 75,
        }, '銅製程 CMP 標準配方。'),
        ('Oxide-Polish', 1, {
            'slurry': 'SiO2-SLR-B', 'pressure_psi': 3, 'time_min': 3, 'table_rpm': 65,
        }, '氧化物層 CMP recipe。'),
        ('Tungsten-Polish', 1, {
            'slurry': 'W-SLR-C', 'pressure_psi': 5, 'time_min': 1.5, 'table_rpm': 80,
        }, '鎢層 CMP 配方。'),
        ('Buff-Step', 1, {
            'slurry': 'DI-water', 'pressure_psi': 1, 'time_min': 1, 'table_rpm': 50,
        }, '純水緩衝步驟,清除殘留 slurry。'),
        ('EndpointDetect-Cu', 1, {
            'slurry': 'Cu-SLR-A', 'pressure_psi': 4, 'time_min': 2,
            'table_rpm': 75, 'endpoint_detect': True,
        }, '銅 CMP 配自動 endpoint 偵測。'),
    ],
    'Wet Bench': [
        ('SC1-Clean', 1, {
            'chem': 'NH4OH+H2O2+H2O', 'temp_C': 70, 'time_min': 10, 'ratio': '1:1:5',
        }, '有機物去除 SC1 清洗。'),
        ('SC2-Clean', 1, {
            'chem': 'HCl+H2O2+H2O', 'temp_C': 70, 'time_min': 10, 'ratio': '1:1:6',
        }, '金屬離子去除 SC2 清洗。'),
        ('Piranha-Strip', 1, {
            'chem': 'H2SO4+H2O2', 'temp_C': 120, 'time_min': 15, 'ratio': '3:1',
        }, '光阻全去 Piranha recipe。'),
        ('BOE-Strip', 1, {
            'chem': 'BOE 6:1', 'temp_C': 25, 'time_min': 3, 'ratio': '6:1',
        }, 'BOE 緩衝氧化物蝕刻液。'),
        ('HF-DiluteDip', 1, {
            'chem': 'HF 100:1', 'temp_C': 25, 'time_min': 1, 'ratio': '100:1',
        }, '稀 HF 浸沾,快速去自然氧化層。'),
    ],
    'Ion Implanter': [
        ('B-LowDose', 1, {
            'ion': 'B+', 'energy_keV': 30, 'dose_per_cm2': 1e13, 'tilt_deg': 7,
        }, '硼低劑量 channel 摻雜。'),
        ('B-HighDose', 1, {
            'ion': 'B+', 'energy_keV': 60, 'dose_per_cm2': 5e15, 'tilt_deg': 0,
        }, '硼高劑量 source/drain 摻雜。'),
        ('P-Drain', 1, {
            'ion': 'P+', 'energy_keV': 80, 'dose_per_cm2': 3e15, 'tilt_deg': 7,
        }, 'NMOS drain 磷摻雜配方。'),
        ('As-Source', 1, {
            'ion': 'As+', 'energy_keV': 40, 'dose_per_cm2': 2e15, 'tilt_deg': 0,
        }, 'NMOS source 砷摻雜。'),
        ('BF2-Channel', 1, {
            'ion': 'BF2+', 'energy_keV': 20, 'dose_per_cm2': 8e13, 'tilt_deg': 7,
        }, 'BF2 淺接面 channel 摻雜。'),
    ],
    # ── Metrology & Inspection ───────────────────────────────────────────
    'CD-SEM': [
        ('Std-1kV', 1, {
            'accel_kV': 1.0, 'probe_current_pA': 4, 'magnification': 50000,
            'scan_speed': 'med',
        }, '主流量產量測 recipe。'),
        ('HighRes-0.3kV', 1, {
            'accel_kV': 0.3, 'probe_current_pA': 2, 'magnification': 200000,
            'scan_speed': 'slow',
        }, '高解析度低能量,適合 EUV 結構量測。'),
        ('LongRun-Map', 1, {
            'accel_kV': 1.0, 'probe_current_pA': 8, 'magnification': 30000,
            'scan_speed': 'fast', 'map_mode': True,
        }, '大面積映射量測,快速掃描。'),
        ('LineWidth-EdgeAlgo', 1, {
            'accel_kV': 0.5, 'probe_current_pA': 4, 'magnification': 100000,
            'scan_speed': 'med', 'edge_algo': 'LE',
        }, '線寬量測 LE 邊緣演算法。'),
        ('DenseArray-Compensate', 1, {
            'accel_kV': 0.8, 'probe_current_pA': 2, 'magnification': 80000,
            'scan_speed': 'med', 'charge_compensate': True,
        }, '密集結構量測,啟用充電補償。'),
    ],
    'Inspect Tool': [
        ('BF-Std', 1, {
            'mode': 'Bright-Field', 'pixel_size_nm': 30,
            'sens': 'med', 'threshold': 0.7,
        }, '明視野標準缺陷檢測。'),
        ('DF-Std', 1, {
            'mode': 'Dark-Field', 'pixel_size_nm': 30,
            'sens': 'med', 'threshold': 0.6,
        }, '暗視野標準檢測,適合粒子缺陷。'),
        ('HighSens-Scan', 1, {
            'mode': 'Bright-Field', 'pixel_size_nm': 15,
            'sens': 'high', 'threshold': 0.85,
        }, '高靈敏度掃描,微小缺陷檢出。'),
        ('FastSurvey', 1, {
            'mode': 'Bright-Field', 'pixel_size_nm': 50,
            'sens': 'low', 'threshold': 0.5,
        }, '快速巡檢 recipe,粗篩用。'),
        ('DefectReview-SEM', 1, {
            'mode': 'SEM-Review', 'pixel_size_nm': 5,
            'sens': 'high', 'threshold': 0.9, 'review_mode': True,
        }, 'SEM 缺陷複檢 recipe。'),
    ],
    'Auto Prober': [
        ('WaferFinal-Std', 1, {
            'test_plan': 'WaferFinal-A', 'site_count': 200,
            'touchdown_force_g': 5, 'contact_resistance_max_ohm': 0.5,
        }, '晶圓 Final Test 標準計畫。'),
        ('E-Test', 1, {
            'test_plan': 'E-Test', 'site_count': 50,
            'touchdown_force_g': 3, 'contact_resistance_max_ohm': 0.2,
        }, 'PCM 電性測試。'),
        ('Reliability-BurnIn', 1, {
            'test_plan': 'Burn-In', 'site_count': 100,
            'touchdown_force_g': 4, 'contact_resistance_max_ohm': 0.3,
            'temp_C': 125,
        }, '高溫 Burn-In 可靠度測試。'),
        ('Diode-Char', 1, {
            'test_plan': 'Diode-IV', 'site_count': 80,
            'touchdown_force_g': 3, 'contact_resistance_max_ohm': 0.4,
        }, '二極體 I-V 特性量測。'),
        ('LongSoak-Stability', 1, {
            'test_plan': 'Stability-LR', 'site_count': 150,
            'touchdown_force_g': 5, 'contact_resistance_max_ohm': 0.5,
            'soak_time_min': 30,
        }, '長時間 soak 穩定度測試。'),
    ],
}


def forwards(apps, schema_editor):
    EquipmentType = apps.get_model('equipments', 'EquipmentType')
    Recipe = apps.get_model('equipments', 'Recipe')

    for type_name, recipes in RECIPES.items():
        et = EquipmentType.objects.filter(name=type_name).first()
        if et is None:
            # An older deployment without this type — skip silently rather
            # than crashing the whole migration. The bookkeeping cost of
            # back-filling missing types belongs in the equipment-catalog
            # migration, not here.
            continue
        for name, version, params, remark in recipes:
            Recipe.objects.get_or_create(
                name=name,
                equipment_type=et,
                version=version,
                defaults={
                    'parameters': params,
                    'remark': remark,
                    'is_active': True,
                },
            )


def reverse(apps, schema_editor):
    """Best-effort rollback: drop the recipes we created, leave manually-
    added ones alone."""
    Recipe = apps.get_model('equipments', 'Recipe')
    for type_name, recipes in RECIPES.items():
        for name, version, *_ in recipes:
            Recipe.objects.filter(
                name=name,
                version=version,
                equipment_type__name=type_name,
            ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('equipments', '0006_recipe'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
