from django.contrib import admin
from .models import Animal, AnimalType, AnimalGroup, AnimalEvent, MilkRecord, WeightRecord

admin.site.register(AnimalType)
admin.site.register(AnimalGroup)
admin.site.register(AnimalEvent)
admin.site.register(Animal)
admin.site.register(WeightRecord)
admin.site.register(MilkRecord)
