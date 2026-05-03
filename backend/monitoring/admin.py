from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action_type', 'http_method', 'path', 'status_code', 'duration_ms')
    list_filter = ('action_type', 'http_method', 'status_code')
    search_fields = ('path', 'user__username', 'ip_address')
    readonly_fields = tuple(f.name for f in ActivityLog._meta.fields)
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
