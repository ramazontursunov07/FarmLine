import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('farms', '0003_farm_latitude_farm_longitude'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Party',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind',
                 models.CharField(choices=[('mijoz', 'Mijoz'), ('taminotchi', 'Yetkazib beruvchi')], default='mijoz',
                                  max_length=12)),
                ('name', models.CharField(max_length=120)),
                ('phone', models.CharField(blank=True, max_length=30)),
                ('note', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('farm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='debt_parties',
                                           to='farms.farm')),
            ],
            options={
                'verbose_name': 'Qarz tomoni',
                'verbose_name_plural': 'Qarz tomonlari',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Debt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('date', models.DateField()),
                ('due_date', models.DateField(blank=True, null=True)),
                ('description', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('farm',
                 models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='debts', to='farms.farm')),
                ('party', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='debts',
                                            to='debts.party')),
                ('recorded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='recorded_debts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Qarz',
                'verbose_name_plural': 'Qarzlar',
                'ordering': ['-date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='DebtPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('date', models.DateField()),
                ('note', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('debt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments',
                                           to='debts.debt')),
                ('recorded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name='recorded_debt_payments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='party',
            constraint=models.UniqueConstraint(fields=('farm', 'kind', 'name'), name='unique_debt_party_per_farm_kind'),
        ),
    ]
