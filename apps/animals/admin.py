from django.contrib import admin
from .models import AnimalType, AnimalGroup, AnimalEvent

admin.site.register(AnimalType)
admin.site.register(AnimalGroup)
admin.site.register(AnimalEvent)
