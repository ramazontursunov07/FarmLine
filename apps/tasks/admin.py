from django.contrib import admin
from .models import RecurringTask, Task

admin.site.register(Task)
admin.site.register(RecurringTask)
