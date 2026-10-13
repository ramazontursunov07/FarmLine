from django.contrib import admin

from .models import PendingAction


@admin.register(PendingAction)
class PendingActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'created_at', 'resolved_at')
    list_filter = ('status',)
    readonly_fields = ('user', 'actions', 'status', 'created_at', 'resolved_at')
