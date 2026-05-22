"""
users/serializers.py
Serializers for authentication and user management.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import FAB, Department, WaferLot

User = get_user_model()


class FABSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAB
        fields = ['id', 'fab_name']


class DepartmentSerializer(serializers.ModelSerializer):
    fab_name = serializers.CharField(source='fab.fab_name', read_only=True)

    class Meta:
        model = Department
        fields = ['id', 'fab', 'fab_name', 'name']


class WaferLotSerializer(serializers.ModelSerializer):
    """Wafer-lot row + per-lot lock / history annotations.

    The submission UI uses these flags to:
    * grey out lots that already have an active order (``is_locked``)
    * show the requester which experiments are already done so they
      don't accidentally re-submit (``experiments_done``).

    The annotations are computed in :class:`WaferLotListView.get_queryset`
    by walking the lot's reverse FK; the serializer only needs to expose
    the resulting fields.
    """

    fab_name = serializers.CharField(source='fab.fab_name', read_only=True)
    is_locked = serializers.SerializerMethodField()
    active_order_no = serializers.SerializerMethodField()
    experiments_done = serializers.SerializerMethodField()

    class Meta:
        model = WaferLot
        # ``code`` is the primary key — there is no auto-generated ``id``
        # column on this model. Listing 'id' here would crash with
        # ImproperlyConfigured("Field name 'id' is not valid").
        fields = [
            'code', 'fab', 'fab_name', 'notes', 'created_at',
            'is_locked', 'active_order_no', 'experiments_done',
        ]
        read_only_fields = ['created_at', 'is_locked', 'active_order_no', 'experiments_done']

    def _active_order(self, obj):
        # Pulled from the prefetched ``orders`` list when present, else a
        # focused query against the in-memory annotation. Avoid touching
        # related managers on every row to keep the list endpoint cheap.
        for o in getattr(obj, '_prefetched_objects_cache', {}).get('orders', []):
            if o.status in ('waiting', 'in_progress'):
                return o
        return None

    def get_is_locked(self, obj):
        return self._active_order(obj) is not None

    def get_active_order_no(self, obj):
        active = self._active_order(obj)
        return active.order_no if active else None

    def get_experiments_done(self, obj):
        rows = []
        cache = getattr(obj, '_prefetched_objects_cache', {}).get('orders', [])
        for o in cache:
            if o.status != 'done':
                continue
            exp = o.experiment
            rows.append({
                'experiment_id': str(exp.id) if exp else None,
                'experiment_name': exp.name if exp else None,
                'order_no': o.order_no,
                'completed_at': o.ended_at.isoformat() if o.ended_at else None,
            })
        return rows


class UserSerializer(serializers.ModelSerializer):
    department_name = serializers.ReadOnlyField()


    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'name', 'role',
            'department', 'department_name', 'status',
            'lab_specialty', 'joined_at',
        ]
        read_only_fields = ['id', 'joined_at']


class UserProfileSerializer(serializers.ModelSerializer):
    """Read-only serializer for the currently logged-in user."""
    department_name = serializers.CharField(source='department.name', read_only=True)
    fab_name = serializers.CharField(source='department.fab.fab_name', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'department', 'department_name', 'fab_name',
            'status', 'lab_specialty', 'joined_at',
        ]
