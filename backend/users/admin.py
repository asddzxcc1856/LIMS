from django.contrib import admin
from .models import FAB, Department, User


@admin.register(FAB)
class FABAdmin(admin.ModelAdmin):
    list_display = ['fab_name']


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'fab']


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'role', 'department', 'status', 'joined_at']
    list_filter = ['role', 'status']
