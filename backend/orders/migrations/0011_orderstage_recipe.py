# Hand-written: attach Recipe FK to OrderStage.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0010_order_lot_fk'),
        ('equipments', '0006_recipe'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderstage',
            name='recipe',
            field=models.ForeignKey(
                blank=True,
                help_text='Recipe used on the picked equipment for this stage.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stages',
                to='equipments.recipe',
            ),
        ),
    ]
