from django.contrib import admin
from .models import Attendance, Farm, SalaryPayment, Worker

admin.site.register(Farm)
admin.site.register(Worker)
admin.site.register(Attendance)
admin.site.register(SalaryPayment)
