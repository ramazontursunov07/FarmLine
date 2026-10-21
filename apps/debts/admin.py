from django.contrib import admin

from .models import Debt, DebtPayment, Party

admin.site.register(Party)
admin.site.register(Debt)
admin.site.register(DebtPayment)
