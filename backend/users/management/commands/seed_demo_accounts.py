"""One-shot helper to provision (and report) the demo account roster.

The schema already auto-seeds the standard demo org via migration 0003,
but it does so silently — operators bringing up a fresh stack often ask
"OK, which accounts exist and what are their passwords?". This command
answers both questions:

* Idempotent re-run of the seed logic so any missing roles get added.
* Prints a Markdown-ready table of usernames, roles, departments and the
  default password sourced from ``LIMS_DEMO_PASSWORD`` /
  ``LIMS_ADMIN_PASSWORD`` env vars.

Usage::

    docker compose exec backend python manage.py seed_demo_accounts
    docker compose exec backend python manage.py seed_demo_accounts --list-only
"""
from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


# Real-world wafer-fab job titles per lab — each 4-person lab maps to the
# canonical WIP-coordinator → Production-controller → Process-engineer →
# Tool-operator hand-off seen in production fabs (TSMC / Intel / Micron
# all share roughly this split).
#
# Each tuple: (username, role, dept_name, first_name_zh, role_label).
# - ``first_name_zh`` populates ``User.first_name`` so the assignee
#   dropdown and audit columns show a human-readable job title.
# - ``role_label`` is the description column in the seed report — it
#   also includes the English term so foreign engineers can correlate.
def _derive_specialty(role, label):
    """Map the role_label string to a User.LabSpecialty value.

    Only lab_member rows carry a meaningful specialty; everything else
    (requesters, managers, sysadmins) gets ``none`` so the field doesn't
    accidentally grant workflow rights to non-lab-members.
    """
    if role != 'lab_member':
        return 'none'
    if '分貨' in label:
        return 'coord'
    if '派工' in label:
        return 'dispatcher'
    if '設定參數' in label:
        return 'engineer'
    if '機台執行' in label:
        return 'operator'
    return 'none'


DEMO_ORG = [
    # ── Factory user (R&D engineer who submits the request) ──────────────
    ('testuser',            'regular_employee', 'Photolithography Lab',
     '廠區研發送樣工程師', 'R&D Engineer (Request Submitter)'),

    # ── Photo / 光刻實驗室 ─────────────────────────────────────────────────
    # Real-world structure: Lab Manager + Lot Coordinator + Bay Captain
    # (production controller) + Litho Process Engineer + Equipment Operator
    ('Lab_Mgr_Photo',       'lab_manager',      'Photolithography Lab',
     '光刻實驗室主管', 'Litho Lab Supervisor — 簽核 / 駁回'),
    ('Lab_Mem_Photo_001',   'lab_member',       'Photolithography Lab',
     '光刻 WIP 協調員', 'Litho Lot Coordinator — 分貨'),
    ('Lab_Mem_Photo_002',   'lab_member',       'Photolithography Lab',
     '光刻派工排班員', 'Litho Bay Captain / Dispatcher — 派工'),
    ('Lab_Mem_Photo_003',   'lab_member',       'Photolithography Lab',
     '光刻製程工程師', 'Litho Process Engineer — 設定參數'),
    ('Lab_Mem_Photo_004',   'lab_member',       'Photolithography Lab',
     '光刻設備操作員 A', 'Stepper / Track Operator — 機台執行'),
    ('Lab_Mem_Photo_005',   'lab_member',       'Photolithography Lab',
     '光刻設備操作員 B', 'Stepper / Track Operator — 機台執行'),
    ('Lab_Mem_Photo_006',   'lab_member',       'Photolithography Lab',
     '光刻設備操作員 C', 'Stepper / Track Operator — 機台執行'),

    # ── Thin Film & Etch / 薄膜蝕刻實驗室 ──────────────────────────────────
    # Real-world structure: ALD / PVD / CVD / Dry Etch / CMP all under one
    # process-engineering team in most fabs; we mirror that with one
    # process engineer + one tool operator.
    ('Lab_Mgr_Process',     'lab_manager',      'Thin Film & Etch Lab',
     '薄膜蝕刻實驗室主管', 'Thin Film & Etch Lab Supervisor — 簽核 / 駁回'),
    ('Lab_Mem_Process_001', 'lab_member',       'Thin Film & Etch Lab',
     '薄膜蝕刻 WIP 協調員', 'Process Lot Coordinator — 分貨'),
    ('Lab_Mem_Process_002', 'lab_member',       'Thin Film & Etch Lab',
     '薄膜蝕刻派工排班員', 'Process Dispatcher — 派工'),
    ('Lab_Mem_Process_003', 'lab_member',       'Thin Film & Etch Lab',
     'CVD / PVD / Etch 製程工程師', 'Thin Film & Etch Process Engineer — 設定參數'),
    ('Lab_Mem_Process_004', 'lab_member',       'Thin Film & Etch Lab',
     '薄膜蝕刻設備操作員 A', 'Etch / Deposition Tool Operator — 機台執行'),
    ('Lab_Mem_Process_005', 'lab_member',       'Thin Film & Etch Lab',
     '薄膜蝕刻設備操作員 B', 'Etch / Deposition Tool Operator — 機台執行'),
    ('Lab_Mem_Process_006', 'lab_member',       'Thin Film & Etch Lab',
     '薄膜蝕刻設備操作員 C', 'Etch / Deposition Tool Operator — 機台執行'),

    # ── Metrology & Inspection / 量測檢測實驗室 ───────────────────────────
    # CD-SEM, Defect Inspection, Auto Prober都歸這個 lab；recipe engineer 對
    # 應的是真實 fab 的 "metrology recipe owner"。
    ('Lab_Mgr_QC',          'lab_manager',      'Metrology & Inspection Lab',
     '量測檢測實驗室主管', 'Metrology Lab Supervisor — 簽核 / 駁回'),
    ('Lab_Mem_QC_001',      'lab_member',       'Metrology & Inspection Lab',
     '量測 WIP 協調員', 'Metrology Lot Coordinator — 分貨'),
    ('Lab_Mem_QC_002',      'lab_member',       'Metrology & Inspection Lab',
     '量測派工排班員', 'Metrology Dispatcher — 派工'),
    ('Lab_Mem_QC_003',      'lab_member',       'Metrology & Inspection Lab',
     'CD-SEM 量測工程師', 'Metrology Recipe Engineer (CD-SEM / Inspect) — 設定參數'),
    ('Lab_Mem_QC_004',      'lab_member',       'Metrology & Inspection Lab',
     '量測設備操作員 A', 'Metrology Tool Operator (CD-SEM / Defect Inspect) — 機台執行'),
    ('Lab_Mem_QC_005',      'lab_member',       'Metrology & Inspection Lab',
     '量測設備操作員 B', 'Metrology Tool Operator (CD-SEM / Defect Inspect) — 機台執行'),
    ('Lab_Mem_QC_006',      'lab_member',       'Metrology & Inspection Lab',
     '量測設備操作員 C', 'Metrology Tool Operator (CD-SEM / Defect Inspect) — 機台執行'),

    # ── Sysadmin ─────────────────────────────────────────────────────────
    ('admin',               'superuser',        None,
     '系統管理員', 'System Administrator (Full Access)'),
]


class Command(BaseCommand):
    help = 'Provision / report the canonical demo accounts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list-only', action='store_true',
            help='Skip provisioning; just print the existing roster.',
        )
        parser.add_argument(
            '--force-reseed', action='store_true',
            help='Re-run the demo-org seed even if accounts already exist.',
        )

    def handle(self, *args, **options):
        # By default we ALWAYS try to reseed because the underlying logic
        # is a no-op when rows already exist — the only cost is one extra
        # `exists()` query per row. ``--list-only`` skips even that.
        if not options['list_only']:
            self._reseed()
        self._print_report()

    # ── re-seed -----------------------------------------------------------

    def _reseed(self):
        """Create every account in DEMO_ORG that isn't already present.

        Used to defer to ``users.migrations.0003_create_demo_org`` but
        that migration only knows about a single lab_member per dept;
        with the rotation rule (各司其職) in place we need 4 members
        each so split / dispatch / params / assign can hand off
        between different people. Seeding direct from the canonical
        DEMO_ORG list keeps the migration history immutable while
        adding the extra members on demand.
        """
        from django.contrib.auth.hashers import make_password
        from users.models import Department, FAB

        demo_password = os.environ.get('LIMS_DEMO_PASSWORD') or 'Lims@2026!Init'
        admin_password = (
            os.environ.get('LIMS_ADMIN_PASSWORD') or 'Lims@2026!Init'
        )
        demo_hash = make_password(demo_password)
        admin_hash = make_password(admin_password)

        # Ensure the FAB + departments exist; pick the first FAB on file
        # so this works even after fab renames. Fall back to the demo
        # default name when no fab exists yet.
        fab = FAB.objects.order_by('fab_name').first()
        if fab is None:
            fab = FAB.objects.create(fab_name='FAB12A')

        created = 0
        renamed = 0
        for username, role, dept_name, first_name_zh, label in DEMO_ORG:
            dept = None
            if dept_name:
                dept, _ = Department.objects.get_or_create(fab=fab, name=dept_name)

            specialty = _derive_specialty(role, label)

            existing = User.objects.filter(username=username).first()
            if existing is None:
                User.objects.create(
                    username=username,
                    email=f'{username.lower()}@lims.local',
                    first_name=first_name_zh,
                    last_name='',
                    role=role,
                    status='active',
                    department=dept,
                    lab_specialty=specialty,
                    is_active=True,
                    is_staff=(role == 'superuser'),
                    is_superuser=(role == 'superuser'),
                    password=admin_hash if role == 'superuser' else demo_hash,
                )
                created += 1
                continue

            # Idempotent display-name + specialty refresh — keeps existing
            # demo accounts in lockstep with the DEMO_ORG table without
            # forcing a password / role / department change. Only
            # touches first_name + last_name + lab_specialty; everything
            # else (incl. password) is preserved.
            dirty = []
            if existing.first_name != first_name_zh:
                existing.first_name = first_name_zh
                dirty.append('first_name')
            if existing.last_name != '':
                existing.last_name = ''
                dirty.append('last_name')
            if existing.lab_specialty != specialty:
                existing.lab_specialty = specialty
                dirty.append('lab_specialty')
            if dirty:
                existing.save(update_fields=dirty)
                renamed += 1

        self.stdout.write(self.style.SUCCESS(
            f'Demo org reseed done — {created} created, {renamed} renamed '
            f'(idempotent; passwords / roles untouched).',
        ))

    # ── report -----------------------------------------------------------

    def _print_report(self):
        demo_password = os.environ.get('LIMS_DEMO_PASSWORD') or 'Lims@2026!Init'
        admin_password = (
            os.environ.get('LIMS_ADMIN_PASSWORD') or 'Lims@2026!Init'
        )

        # Resolve which accounts are actually present so we don't lie when
        # the env wasn't gated on (SEED_DEMO_DATA defaulting to True keeps
        # this rare, but better safe).
        present = set(User.objects.values_list('username', flat=True))

        rows = []
        for username, role, dept, first_name_zh, label in DEMO_ORG:
            password = admin_password if role == 'superuser' else demo_password
            status = '✓' if username in present else '✗ MISSING'
            rows.append((status, username, role, dept or '—', first_name_zh, label, password))

        col = ('Status', 'Username', 'Role', 'Department', '職稱', 'Role description', 'Password')
        widths = [max(len(str(r[i])) for r in (rows + [col])) for i in range(len(col))]

        def emit(row):
            self.stdout.write(' | '.join(
                str(c).ljust(widths[i]) for i, c in enumerate(row)
            ))

        emit(col)
        emit(tuple('-' * w for w in widths))
        for row in rows:
            emit(row)

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'These passwords are demo defaults — rotate them in production '
            'via `python manage.py changepassword <user>`.',
        ))
