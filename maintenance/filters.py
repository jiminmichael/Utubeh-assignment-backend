import django_filters
from django.db.models import Q

from .models import MaintenanceRecord


class MaintenanceFilter(django_filters.FilterSet):
    asset_id = django_filters.NumberFilter(field_name="asset_id", lookup_expr="exact")
    assigned_user = django_filters.CharFilter(method="filter_assigned_user")
    reported_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    reported_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")
    scheduled_after = django_filters.DateTimeFilter(field_name="scheduled_for", lookup_expr="gte")
    scheduled_before = django_filters.DateTimeFilter(field_name="scheduled_for", lookup_expr="lte")
    completed_after = django_filters.DateTimeFilter(field_name="completed_at", lookup_expr="gte")
    completed_before = django_filters.DateTimeFilter(field_name="completed_at", lookup_expr="lte")
    cost_min = django_filters.NumberFilter(field_name="cost", lookup_expr="gte")
    cost_max = django_filters.NumberFilter(field_name="cost", lookup_expr="lte")

    class Meta:
        model = MaintenanceRecord
        fields = {
            "status": ["exact"],
            "priority": ["exact"],
            "maintenance_type": ["exact"],
            "asset__asset_tag": ["exact", "icontains"],
            "asset__serial_number": ["exact", "icontains"],
            "asset__category": ["exact"],
            "asset__status": ["exact"],
            "assigned_to": ["exact"],
            "reported_by": ["exact"],
        }

    def filter_assigned_user(self, queryset, name, value):
        return queryset.filter(
            Q(assigned_to__username__icontains=value)
            | Q(assigned_to__email__icontains=value)
            | Q(assigned_to__first_name__icontains=value)
            | Q(assigned_to__last_name__icontains=value)
        )