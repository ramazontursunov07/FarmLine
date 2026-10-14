import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0003_transaction_animal_count'),
        ('inventory', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventorytransaction',
            name='amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='inventorytransaction',
            name='finance_transaction',
            field=models.OneToOneField(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='inventory_purchase', to='finance.transaction'),
        ),
    ]
