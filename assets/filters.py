import django_filters
from django.db.models import Q

from .models import Asset


class AssetFilter(django_filters.FilterSet):
    asset_id = django_filters.NumberFilter(field_name="id", lookup_expr="exact")
    assigned_user = django_filters.CharFilter(method="filter_assigned_user")
    assigned_user_id = django_filters.NumberFilter(field_name="assignments__assigned_to_id", lookup_expr="exact")
    device_type = django_filters.CharFilter(field_name="category", lookup_expr="exact")
    min_purchase_cost = django_filters.NumberFilter(field_name="purchase_cost", lookup_expr="gte")
    max_purchase_cost = django_filters.NumberFilter(field_name="purchase_cost", lookup_expr="lte")
    purchased_after = django_filters.DateFilter(field_name="purchase_date", lookup_expr="gte")
    purchased_before = django_filters.DateFilter(field_name="purchase_date", lookup_expr="lte")
    warranty_expiring_before = django_filters.DateFilter(field_name="warranty_expiry", lookup_expr="lte")
    warranty_expiring_after = django_filters.DateFilter(field_name="warranty_expiry", lookup_expr="gte")

    class Meta:
        model = Asset
        fields = {
            "asset_tag": ["exact", "icontains"],
            "serial_number": ["exact", "icontains"],
            "barcode": ["exact", "icontains"],
            "category": ["exact"],
            "subcategory": ["exact", "icontains"],
            "manufacturer": ["exact", "icontains"],
            "model": ["exact", "icontains"],
            "status": ["exact"],
            "condition": ["exact"],
            "location": ["exact", "icontains"],
            "vendor_name": ["exact", "icontains"],
            "is_active": ["exact"],
        }

    def filter_assigned_user(self, queryset, name, value):
        return queryset.filter(
            Q(assignments__assigned_to__username__icontains=value)
            | Q(assignments__assigned_to__email__icontains=value)
            | Q(assignments__assigned_to__first_name__icontains=value)
            | Q(assignments__assigned_to__last_name__icontains=value)
        ).distinct()
