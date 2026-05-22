# Hand-written: add Recipe table.
# Generated against equipments 0005_backfill_experiment_department.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('equipments', '0005_backfill_experiment_department'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Recipe',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('version', models.PositiveIntegerField(default=1)),
                ('parameters', models.JSONField(blank=True, default=dict)),
                ('remark', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'created_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='recipes_created',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'equipment_type',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='recipes',
                        to='equipments.equipmenttype',
                    ),
                ),
            ],
            options={
                'db_table': 'recipe',
                'ordering': ['equipment_type__name', 'name', '-version'],
                'unique_together': {('name', 'equipment_type', 'version')},
            },
        ),
    ]
