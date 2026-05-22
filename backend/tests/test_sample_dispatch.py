"""Per-sample dispatch chain — each sub-LOT runs its own
派工 → 設定參數 → 指派 → 上貨 → 下貨 lifecycle on potentially
different machines + recipes + operators.
"""
import datetime as _dt

import pytest
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.exceptions import ValidationError

from orders import services
from orders.models import OrderStage, Sample

from tests.factories import (
    EquipmentFactory,
    OrderStageFactory,
    RecipeFactory,
)


# approved_order fixture moved to /backend/conftest.py so test_samples.py
# can use it too without redefinition.


@pytest.mark.unit
class TestPerSampleDispatch:
    @freeze_time('2026-05-20 10:00:00')
    def test_two_samples_dispatched_to_different_machines(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        # Arrange — split into two sub-LOTs
        services.split_order(
            approved_order,
            splits=[
                {'sub_code': 'A', 'wafer_count': 3},
                {'sub_code': 'B', 'wafer_count': 2},
            ],
            operator=lab_member,
        )
        eq1 = EquipmentFactory(equipment_type=equipment_type, department=department)
        eq2 = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe1 = RecipeFactory(equipment_type=equipment_type, parameters={'temp_C': 250})
        recipe2 = RecipeFactory(equipment_type=equipment_type, parameters={'temp_C': 300})
        sample_a = approved_order.samples.get(sub_code='A')
        sample_b = approved_order.samples.get(sub_code='B')

        from tests.factories import LabDispatcherFactory
        dispatcher = LabDispatcherFactory(department=department)

        # Act — dispatch each sample independently
        services.dispatch_sample(
            sample_a, operator=dispatcher,
            equipment=str(eq1.id), recipe=str(recipe1.id),
            schedule_start='2026-05-21T10:00:00Z',
            schedule_end='2026-05-21T11:00:00Z',
        )
        services.dispatch_sample(
            sample_b, operator=dispatcher,
            equipment=str(eq2.id), recipe=str(recipe2.id),
            schedule_start='2026-05-21T11:00:00Z',
            schedule_end='2026-05-21T12:00:00Z',
        )
        # Assert — each sample on its own machine/recipe
        sample_a.refresh_from_db()
        sample_b.refresh_from_db()
        assert sample_a.equipment_id == eq1.id
        assert sample_a.recipe_id == recipe1.id
        assert sample_a.status == Sample.Status.DISPATCHED
        assert sample_b.equipment_id == eq2.id
        assert sample_b.recipe_id == recipe2.id
        assert sample_b.status == Sample.Status.DISPATCHED

    @freeze_time('2026-05-20 10:00:00')
    def test_full_chain_per_sample(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        # Arrange — one sample, one approved stage
        services.split_order(
            approved_order,
            splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(
            equipment_type=equipment_type, parameters={'temp_C': 250, 'time_sec': 600},
        )
        sample = approved_order.samples.get(sub_code='A')

        # Act — rotate operators across the chain so the rotation rule
        # (各司其職) is honoured. ``lab_member`` (fixture = coord) created
        # the Sample via split; we conjure specialised teammates for
        # dispatch / params / operator.
        from tests.factories import (
            LabDispatcherFactory, LabEngineerFactory, LabOperatorFactory,
        )
        dispatcher = LabDispatcherFactory(department=department)
        param_setter = LabEngineerFactory(department=department)
        executor = LabOperatorFactory(department=department)

        services.dispatch_sample(
            sample, operator=dispatcher,
            equipment=str(eq.id), recipe=str(recipe.id),
            schedule_start='2026-05-21T09:00:00Z',
            schedule_end='2026-05-21T10:00:00Z',
        )
        services.set_sample_parameters(
            sample, operator=param_setter,
            parameter_overrides={'temp_C': 260},
            auto_assign=False,
        )
        # Assign picks a 4th lab_member that hasn't touched any upstream
        # step — required by the rotation rule.
        services.assign_sample(sample, operator=param_setter, assignee=executor)

        sample.refresh_from_db()
        assert sample.status == Sample.Status.READY

        with freeze_time('2026-05-21 09:30:00'):
            services.load_sample(sample, operator=executor)
            sample.refresh_from_db()
            assert sample.status == Sample.Status.RUNNING
            assert sample.loaded_by_id == executor.id

            services.complete_sample(sample, operator=executor)
            sample.refresh_from_db()
            assert sample.status == Sample.Status.DONE
            assert sample.completed_by_id == executor.id

    def test_assign_blocks_self_and_upstream_operators(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        # Arrange — split + dispatch + params done by lab_member (= the
        # sample's created_by, dispatched_by, parameters_set_by). Any
        # attempt to assign back to lab_member must fail per rotation rule.
        services.split_order(
            approved_order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        sample = approved_order.samples.get(sub_code='A')
        from tests.factories import (
            LabDispatcherFactory, LabEngineerFactory, LabOperatorFactory,
        )
        # Each step uses a different specialty per the gate; the rotation
        # rule on top of that forbids re-using ANY upstream user as the
        # assignee (independent of specialty).
        dispatcher = LabDispatcherFactory(department=department)
        engineer = LabEngineerFactory(department=department)
        upstream_operator = LabOperatorFactory(department=department)
        with freeze_time('2026-05-20 10:00:00'):
            services.dispatch_sample(
                sample, operator=dispatcher,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )
            services.set_sample_parameters(
                sample, operator=engineer, parameter_overrides={},
                auto_assign=False,
            )

            # Force the rotation by manually re-using the dispatcher as a
            # would-be assignee (he's both upstream AND wrong specialty).
            with pytest.raises(ValidationError, match='上游|職位'):
                services.assign_sample(
                    sample, operator=upstream_operator, assignee=dispatcher,
                )
            # Self-assign rejected.
            with pytest.raises(ValidationError, match='不能指派給自己'):
                services.assign_sample(
                    sample, operator=upstream_operator, assignee=upstream_operator,
                )
            # Assigning to a fresh operator → OK.
            executor = LabOperatorFactory(department=department)
            services.assign_sample(
                sample, operator=engineer, assignee=executor,
            )
            sample.refresh_from_db()
            assert sample.assignee_id == executor.id

    def test_assignee_must_be_lab_member(
        self, db, approved_order, department, equipment_type,
        lab_member, lab_manager,
    ):
        services.split_order(
            approved_order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        sample = approved_order.samples.get(sub_code='A')
        from tests.factories import (
            LabDispatcherFactory, LabEngineerFactory, LabOperatorFactory,
        )
        dispatcher = LabDispatcherFactory(department=department)
        engineer = LabEngineerFactory(department=department)
        with freeze_time('2026-05-20 10:00:00'):
            services.dispatch_sample(
                sample, operator=dispatcher,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )
            services.set_sample_parameters(
                sample, operator=engineer, parameter_overrides={},
                auto_assign=False,
            )
            another_member = LabOperatorFactory(department=department)
            with pytest.raises(ValidationError, match='不可為主管'):
                services.assign_sample(
                    sample, operator=another_member, assignee=lab_manager,
                )

    def test_recipe_must_match_equipment_type(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        services.split_order(
            approved_order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        from tests.factories import EquipmentTypeFactory, LabDispatcherFactory
        other_type = EquipmentTypeFactory(name='OtherType')
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe_wrong = RecipeFactory(equipment_type=other_type, parameters={})
        sample = approved_order.samples.get(sub_code='A')
        dispatcher = LabDispatcherFactory(department=department)
        with freeze_time('2026-05-20 10:00:00'):
            with pytest.raises(ValidationError, match='不符'):
                services.dispatch_sample(
                    sample, operator=dispatcher,
                    equipment=str(eq.id), recipe=str(recipe_wrong.id),
                    schedule_start='2026-05-21T09:00:00Z',
                    schedule_end='2026-05-21T10:00:00Z',
                )

    def test_specialty_gate_split(
        self, db, approved_order, department,
    ):
        from tests.factories import (
            LabDispatcherFactory, LabEngineerFactory, LabOperatorFactory,
        )
        # Wrong specialty for split → ValidationError mentioning 分貨.
        wrong = LabDispatcherFactory(department=department)
        with pytest.raises(ValidationError, match='分貨'):
            services.split_order(
                approved_order,
                splits=[{'sub_code': 'A', 'wafer_count': 1}],
                operator=wrong,
            )
        # Engineer also wrong.
        wrong2 = LabEngineerFactory(department=department)
        with pytest.raises(ValidationError, match='分貨'):
            services.split_order(
                approved_order,
                splits=[{'sub_code': 'A', 'wafer_count': 1}],
                operator=wrong2,
            )
        # Operator also wrong.
        wrong3 = LabOperatorFactory(department=department)
        with pytest.raises(ValidationError, match='分貨'):
            services.split_order(
                approved_order,
                splits=[{'sub_code': 'A', 'wafer_count': 1}],
                operator=wrong3,
            )

    def test_specialty_gate_dispatch(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        services.split_order(
            approved_order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        sample = approved_order.samples.get(sub_code='A')
        from tests.factories import LabEngineerFactory
        wrong = LabEngineerFactory(department=department)
        with pytest.raises(ValidationError, match='派工'):
            services.dispatch_sample(
                sample, operator=wrong,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )

    def test_auto_pick_assignee_only_operator_specialty(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        """``set_sample_parameters`` should auto-assign an operator —
        never a coord / dispatcher / engineer — even when the operator
        pool is initially empty."""
        services.split_order(
            approved_order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        sample = approved_order.samples.get(sub_code='A')
        from tests.factories import (
            LabDispatcherFactory, LabEngineerFactory, LabOperatorFactory,
        )
        dispatcher = LabDispatcherFactory(department=department)
        engineer = LabEngineerFactory(department=department)
        operator_a = LabOperatorFactory(department=department)
        operator_b = LabOperatorFactory(department=department)

        with freeze_time('2026-05-20 10:00:00'):
            services.dispatch_sample(
                sample, operator=dispatcher,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )
            services.set_sample_parameters(
                sample, operator=engineer, parameter_overrides={},
                # auto_assign defaults to True
            )
        sample.refresh_from_db()
        assert sample.status == Sample.Status.READY
        assert sample.assignee_id in {operator_a.id, operator_b.id}
        # Sanity — assignee really is an operator-specialty user.
        assert sample.assignee.lab_specialty == 'operator'

    def test_parameter_overrides_validated_against_recipe_keys(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        services.split_order(
            approved_order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={'temp_C': 250})
        sample = approved_order.samples.get(sub_code='A')
        from tests.factories import LabDispatcherFactory, LabEngineerFactory
        dispatcher = LabDispatcherFactory(department=department)
        engineer = LabEngineerFactory(department=department)
        with freeze_time('2026-05-20 10:00:00'):
            services.dispatch_sample(
                sample, operator=dispatcher,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )
            with pytest.raises(ValidationError, match='不在 Recipe'):
                services.set_sample_parameters(
                    sample, operator=engineer,
                    parameter_overrides={'fake_knob': 1},
                )


@pytest.mark.unit
class TestDispatchScheduleConflict:
    """The dispatch service has to refuse a schedule that collides with
    an existing booking on the same equipment so two sub-LOTs can't be
    queued onto a machine at the same time."""

    def _seed_two_samples(self, approved_order, lab_member):
        services.split_order(
            approved_order,
            splits=[
                {'sub_code': 'A', 'wafer_count': 1},
                {'sub_code': 'B', 'wafer_count': 1},
            ],
            operator=lab_member,
        )
        return (
            approved_order.samples.get(sub_code='A'),
            approved_order.samples.get(sub_code='B'),
        )

    @freeze_time('2026-05-20 10:00:00')
    def test_second_dispatch_overlapping_window_rejected(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        from tests.factories import LabDispatcherFactory
        dispatcher = LabDispatcherFactory(department=department)
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        a, b = self._seed_two_samples(approved_order, lab_member)

        # A grabs 09:00–10:00 — booking created.
        services.dispatch_sample(
            a, operator=dispatcher,
            equipment=str(eq.id), recipe=str(recipe.id),
            schedule_start='2026-05-21T09:00:00Z',
            schedule_end='2026-05-21T10:00:00Z',
        )
        # B tries the same machine at 09:30–10:30 — must be blocked.
        with pytest.raises(ValidationError, match='已被訂單'):
            services.dispatch_sample(
                b, operator=dispatcher,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:30:00Z',
                schedule_end='2026-05-21T10:30:00Z',
            )
        # The B sample stays in WAITING — no half-applied state.
        b.refresh_from_db()
        assert b.status == Sample.Status.WAITING

    @freeze_time('2026-05-20 10:00:00')
    def test_back_to_back_windows_allowed(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        from tests.factories import LabDispatcherFactory
        dispatcher = LabDispatcherFactory(department=department)
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        a, b = self._seed_two_samples(approved_order, lab_member)

        services.dispatch_sample(
            a, operator=dispatcher,
            equipment=str(eq.id), recipe=str(recipe.id),
            schedule_start='2026-05-21T09:00:00Z',
            schedule_end='2026-05-21T10:00:00Z',
        )
        # B picks the slot that starts exactly when A ends — no overlap.
        services.dispatch_sample(
            b, operator=dispatcher,
            equipment=str(eq.id), recipe=str(recipe.id),
            schedule_start='2026-05-21T10:00:00Z',
            schedule_end='2026-05-21T11:00:00Z',
        )
        b.refresh_from_db()
        assert b.status == Sample.Status.DISPATCHED

    @freeze_time('2026-05-20 10:00:00')
    def test_different_machine_no_conflict(
        self, db, approved_order, department, equipment_type, lab_member,
    ):
        from tests.factories import LabDispatcherFactory
        dispatcher = LabDispatcherFactory(department=department)
        eq1 = EquipmentFactory(equipment_type=equipment_type, department=department)
        eq2 = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        a, b = self._seed_two_samples(approved_order, lab_member)

        services.dispatch_sample(
            a, operator=dispatcher,
            equipment=str(eq1.id), recipe=str(recipe.id),
            schedule_start='2026-05-21T09:00:00Z',
            schedule_end='2026-05-21T10:00:00Z',
        )
        # Same window but a different machine — fine.
        services.dispatch_sample(
            b, operator=dispatcher,
            equipment=str(eq2.id), recipe=str(recipe.id),
            schedule_start='2026-05-21T09:00:00Z',
            schedule_end='2026-05-21T10:00:00Z',
        )
        b.refresh_from_db()
        assert b.status == Sample.Status.DISPATCHED


@pytest.mark.integration
class TestSampleEndpoints:
    def test_dispatch_forbidden_for_manager(
        self, db, manager_client, approved_order, department, equipment_type, lab_member,
    ):
        services.split_order(
            approved_order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        sample = approved_order.samples.get(sub_code='A')
        response = manager_client.post(
            f'/api/orders/samples/{sample.id}/dispatch/',
            {}, format='json',
        )
        assert response.status_code == 403

    def test_lab_member_can_list_samples(
        self, db, member_client, approved_order, department, equipment_type, lab_member,
    ):
        services.split_order(
            approved_order, splits=[
                {'sub_code': 'A', 'wafer_count': 1},
                {'sub_code': 'B', 'wafer_count': 1},
            ],
            operator=lab_member,
        )
        response = member_client.get('/api/orders/samples/')
        assert response.status_code == 200
        sub_codes = {row['sub_code'] for row in response.data}
        assert {'A', 'B'} <= sub_codes

    def test_filter_by_status(
        self, db, member_client, approved_order, department, equipment_type, lab_member,
    ):
        services.split_order(
            approved_order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        # Initially waiting
        response = member_client.get('/api/orders/samples/?status=waiting')
        rows = response.data
        assert any(r['sub_code'] == 'A' for r in rows)

    def test_load_requires_assigned_user(
        self, db, member_client, approved_order, department, equipment_type, lab_member,
    ):
        services.split_order(
            approved_order, splits=[{'sub_code': 'A', 'wafer_count': 1}],
            operator=lab_member,
        )
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe = RecipeFactory(equipment_type=equipment_type, parameters={})
        sample = approved_order.samples.get(sub_code='A')
        # Conjure properly-specialised teammates so each gate is happy.
        from tests.factories import (
            LabDispatcherFactory, LabOperatorFactory,
        )
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        dispatcher = LabDispatcherFactory(department=department)
        assignee = LabOperatorFactory(department=department)
        with freeze_time('2026-05-20 10:00:00'):
            services.dispatch_sample(
                sample, operator=dispatcher,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )
            from tests.factories import LabEngineerFactory
            engineer = LabEngineerFactory(department=department)
            services.set_sample_parameters(
                sample, operator=engineer, parameter_overrides={},
                auto_assign=False,
            )
            services.assign_sample(sample, operator=engineer, assignee=assignee)

            # Yet another member tries to load → 403 (only `assignee` can)
            other_member = LabOperatorFactory(department=department)
            with freeze_time('2026-05-21 09:30:00'):
                # Issue the JWT INSIDE the frozen window so its iat is
                # consistent with simplejwt's clock check.
                client = APIClient()
                client.credentials(
                    HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(other_member).access_token}',
                )
                response = client.post(f'/api/orders/samples/{sample.id}/load/', {}, format='json')
                assert response.status_code == 403
