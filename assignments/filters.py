import django_filters
from django.db.models import Q

from .models import Assignment


class AssignmentFilter(django_filters.FilterSet):
    asset_id = django_filters.NumberFilter(field_name="asset_id", lookup_expr="exact")
    assigned_user = django_filters.CharFilter(method="filter_assigned_user")
    assigned_after = django_filters.DateTimeFilter(field_name="assigned_at", lookup_expr="gte")
    assigned_before = django_filters.DateTimeFilter(field_name="assigned_at", lookup_expr="lte")
    due_after = django_filters.DateTimeFilter(field_name="due_at", lookup_expr="gte")
    due_before = django_filters.DateTimeFilter(field_name="due_at", lookup_expr="lte")
    returned_after = django_filters.DateTimeFilter(field_name="returned_at", lookup_expr="gte")
    returned_before = django_filters.DateTimeFilter(field_name="returned_at", lookup_expr="lte")

    class Meta:
        model = Assignment
        fields = {
            "status": ["exact"],
            "department": ["exact", "icontains"],
            "expected_location": ["exact", "icontains"],
            "asset__asset_tag": ["exact", "icontains"],
            "asset__serial_number": ["exact", "icontains"],
            "asset__category": ["exact"],
            "asset__status": ["exact"],
            "assigned_to": ["exact"],
            "assigned_by": ["exact"],
        }

    def filter_assigned_user(self, queryset, name, value):
        return queryset.filter(
            Q(assigned_to__username__icontains=value)
            | Q(assigned_to__email__icontains=value)
            | Q(assigned_to__first_name__icontains=value)
            | Q(assigned_to__last_name__icontains=value)
        )
