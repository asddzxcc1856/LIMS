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


@pytest.fixture
def approved_order(db, order, department, equipment_type):
    """Order with an APPROVED OrderStage + lab dept set — ready for split."""
    OrderStageFactory(
        order=order, department=department, equipment_type=equipment_type,
        status=OrderStage.Status.APPROVED,
    )
    return order


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

        # Act — dispatch each sample independently
        services.dispatch_sample(
            sample_a, operator=lab_member,
            equipment=str(eq1.id), recipe=str(recipe1.id),
            schedule_start='2026-05-21T10:00:00Z',
            schedule_end='2026-05-21T11:00:00Z',
        )
        services.dispatch_sample(
            sample_b, operator=lab_member,
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
        # (各司其職) is honoured. ``lab_member`` creates the Sample via
        # split; we conjure 3 more members for dispatch / params / load.
        from tests.factories import LabMemberFactory
        dispatcher = LabMemberFactory(department=department)
        param_setter = LabMemberFactory(department=department)
        executor = LabMemberFactory(department=department)

        services.dispatch_sample(
            sample, operator=dispatcher,
            equipment=str(eq.id), recipe=str(recipe.id),
            schedule_start='2026-05-21T09:00:00Z',
            schedule_end='2026-05-21T10:00:00Z',
        )
        services.set_sample_parameters(
            sample, operator=param_setter,
            parameter_overrides={'temp_C': 260},
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
        with freeze_time('2026-05-20 10:00:00'):
            services.dispatch_sample(
                sample, operator=lab_member,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )
            services.set_sample_parameters(sample, operator=lab_member, parameter_overrides={})

            from tests.factories import LabMemberFactory
            another_member = LabMemberFactory(department=department)

            # 1) Assigning to lab_member (= upstream) → reject
            with pytest.raises(ValidationError, match='上游'):
                services.assign_sample(
                    sample, operator=another_member, assignee=lab_member,
                )
            # 2) Assigning to operator themselves → reject
            with pytest.raises(ValidationError, match='不能指派給自己'):
                services.assign_sample(
                    sample, operator=another_member, assignee=another_member,
                )
            # 3) Assigning to a fresh lab_member → OK
            executor = LabMemberFactory(department=department)
            services.assign_sample(
                sample, operator=another_member, assignee=executor,
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
        with freeze_time('2026-05-20 10:00:00'):
            services.dispatch_sample(
                sample, operator=lab_member,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )
            services.set_sample_parameters(
                sample, operator=lab_member, parameter_overrides={},
            )
            from tests.factories import LabMemberFactory
            another_member = LabMemberFactory(department=department)
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
        from tests.factories import EquipmentTypeFactory
        other_type = EquipmentTypeFactory(name='OtherType')
        eq = EquipmentFactory(equipment_type=equipment_type, department=department)
        recipe_wrong = RecipeFactory(equipment_type=other_type, parameters={})
        sample = approved_order.samples.get(sub_code='A')
        with freeze_time('2026-05-20 10:00:00'):
            with pytest.raises(ValidationError, match='不符'):
                services.dispatch_sample(
                    sample, operator=lab_member,
                    equipment=str(eq.id), recipe=str(recipe_wrong.id),
                    schedule_start='2026-05-21T09:00:00Z',
                    schedule_end='2026-05-21T10:00:00Z',
                )

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
        with freeze_time('2026-05-20 10:00:00'):
            services.dispatch_sample(
                sample, operator=lab_member,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )
            with pytest.raises(ValidationError, match='不在 Recipe'):
                services.set_sample_parameters(
                    sample, operator=lab_member,
                    parameter_overrides={'fake_knob': 1},
                )


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
        # Conjure two more members so the rotation rule is satisfied.
        from tests.factories import LabMemberFactory
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        dispatcher = LabMemberFactory(department=department)
        assignee = LabMemberFactory(department=department)
        with freeze_time('2026-05-20 10:00:00'):
            services.dispatch_sample(
                sample, operator=dispatcher,
                equipment=str(eq.id), recipe=str(recipe.id),
                schedule_start='2026-05-21T09:00:00Z',
                schedule_end='2026-05-21T10:00:00Z',
            )
            services.set_sample_parameters(sample, operator=dispatcher, parameter_overrides={})
            services.assign_sample(sample, operator=dispatcher, assignee=assignee)

            # Yet another member tries to load → 403 (only `assignee` can)
            other_member = LabMemberFactory(department=department)
            with freeze_time('2026-05-21 09:30:00'):
                # Issue the JWT INSIDE the frozen window so its iat is
                # consistent with simplejwt's clock check.
                client = APIClient()
                client.credentials(
                    HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(other_member).access_token}',
                )
                response = client.post(f'/api/orders/samples/{sample.id}/load/', {}, format='json')
                assert response.status_code == 403
