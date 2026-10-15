import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('animals', '0003_animalevent_animal_count'),
        ('farms', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Animal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tag_number', models.CharField(max_length=30)),
                ('name', models.CharField(blank=True, max_length=100)),
                ('sex', models.CharField(choices=[('urgochi', "Urg'ochi"), ('erkak', 'Erkak')], default='urgochi', max_length=10)),
                ('birth_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('faol', 'Faol'), ('sotilgan', 'Sotilgan'), ('olgan', "O'lgan")], default='faol', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('farm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='animals', to='farms.farm')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='animals', to='animals.animalgroup')),
                ('mother', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='calves', to='animals.animal')),
            ],
            options={
                'verbose_name': 'Hayvon kartochkasi',
                'verbose_name_plural': 'Hayvon kartochkalari',
                'ordering': ['tag_number'],
            },
        ),
        migrations.AddConstraint(
            model_name='animal',
            constraint=models.UniqueConstraint(fields=('farm', 'tag_number'), name='unique_animal_tag_per_farm'),
        ),
        migrations.AddField(
            model_name='animalevent',
            name='animal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='events', to='animals.animal'),
        ),
        migrations.CreateModel(
            name='WeightRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('weight_kg', models.DecimalField(decimal_places=1, max_digits=7)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('animal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='weights', to='animals.animal')),
                ('recorded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recorded_weights', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='weightrecord',
            constraint=models.UniqueConstraint(fields=('animal', 'date'), name='unique_weight_per_animal_day'),
        ),
        migrations.CreateModel(
            name='MilkRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('session', models.CharField(choices=[('kun', 'Butun kun'), ('ertalab', 'Ertalab'), ('kechqurun', 'Kechqurun')], default='kun', max_length=10)),
                ('liters', models.DecimalField(decimal_places=1, max_digits=6)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('animal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='milk_records', to='animals.animal')),
                ('recorded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recorded_milk', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='milkrecord',
            constraint=models.UniqueConstraint(fields=('animal', 'date', 'session'), name='unique_milk_per_animal_session'),
        ),
    ]
