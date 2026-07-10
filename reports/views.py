from collections import OrderedDict
from datetime import timedelta

from django.db.models import Case, CharField, Count, F, Q, Sum, Value, When
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsViewerOrAbove
from activity_logs.models import ActivityLog
from assets.models import Asset, AuditableModel
from assignments.models import Assignment
from core.choices import AssetCondition, AssetStatus
from maintenance.models import MaintenanceRecord

from .serializers import (
    DashboardQuerySerializer,
    DaysQuerySerializer,
    MonthQuerySerializer,
    StatusQuerySerializer,
)


# =============================================================================
#  DASHBOARD SUMMARY (existing, enhanced)
# =============================================================================

class DashboardSummaryView(APIView):
    permission_classes = [IsViewerOrAbove]

    @extend_schema(
        summary="Dashboard metrics",
        description=(
            "Returns optimized dashboard counts, asset distributions, recent activities, "
            "and assignment/return trends using aggregate ORM queries."
        ),
        parameters=[
            OpenApiParameter("warranty_days", OpenApiTypes.INT, description="Days ahead for warranty expiry. Default: 30."),
            OpenApiParameter("trend_days", OpenApiTypes.INT, description="Days back for assignment trends. Default: 180."),
            OpenApiParameter("recent_limit", OpenApiTypes.INT, description="Number of recent activities. Default: 10."),
        ],
    )
    def get(self, request):
        params = DashboardQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        warranty_days = params.validated_data["warranty_days"]
        trend_days = params.validated_data["trend_days"]
        recent_limit = params.validated_data["recent_limit"]

        ActivityLog.log(
            actor=request.user,
            action=ActivityLog.ActivityAction.EXPORT, # Using EXPORT as a proxy for viewing a report
            entity_type="report",
            entity_repr="Dashboard Summary",
            message=f"Viewed dashboard summary report.",
        )

        today = timezone.localdate()
        warranty_until = today + timedelta(days=warranty_days)
        trend_start = timezone.now() - timedelta(days=trend_days)

        assets = Asset.objects.all()
        asset_counts = assets.aggregate(
            total_assets=Count("id"),
            available_assets=Count("id", filter=Q(status=AssetStatus.AVAILABLE)),
            assigned_assets=Count("id", filter=Q(status=AssetStatus.ASSIGNED)),
            devices_in_repair=Count("id", filter=Q(status=AssetStatus.MAINTENANCE)),
            lost_devices=Count("id", filter=Q(status=AssetStatus.LOST)),
            damaged_devices=Count(
                "id",
                filter=(
                    Q(condition=AssetCondition.DAMAGED)
                    | Q(condition=AssetCondition.NEEDS_REPAIR)
                    | Q(status=AssetStatus.MAINTENANCE)
                    | Q(description__icontains="damage")
                    | Q(description__icontains="damaged")
                    | Q(notes__icontains="damage")
                    | Q(notes__icontains="damaged")
                ),
            ),
            warranty_expiring_soon=Count(
                "id",
                filter=Q(warranty_expiry__gte=today, warranty_expiry__lte=warranty_until),
            ),
        )

        distribution_by_type = list(
            assets.values("category")
            .annotate(total=Count("id"))
            .order_by("category")
        )
        assets_by_location = list(
            assets.annotate(
                location_label=Case(
                    When(location="", then=Value("Unspecified")),
                    default=F("location"),
                    output_field=CharField(),
                )
            )
            .values("location_label")
            .annotate(total=Count("id"))
            .order_by("-total", "location_label")
        )

        recent_activities = list(
            ActivityLog.objects.select_related("actor")
            .order_by("-created_at")
            .values(
                "id",
                "action",
                "entity_type",
                "entity_id",
                "entity_repr",
                "message",
                "created_at",
                "actor_id",
                "actor__username",
                "actor__email",
            )[:recent_limit]
        )

        assignments_by_day = (
            Assignment.objects.filter(assigned_at__gte=trend_start)
            .annotate(period=TruncDate("assigned_at"))
            .values("period")
            .annotate(assigned=Count("id"))
            .order_by("period")
        )
        returns_by_day = (
            Assignment.objects.filter(returned_at__gte=trend_start)
            .annotate(period=TruncDate("returned_at"))
            .values("period")
            .annotate(returned=Count("id"))
            .order_by("period")
        )
        assignment_trends = self._merge_trends(assignments_by_day, returns_by_day)

        return Response(
            {
                "summary": asset_counts,
                "asset_distribution_by_type": distribution_by_type,
                "assets_by_location": [
                    {"location": item["location_label"], "total": item["total"]}
                    for item in assets_by_location
                ],
                "recent_activities": [
                    {
                        "id": item["id"],
                        "action": item["action"],
                        "entity_type": item["entity_type"],
                        "entity_id": item["entity_id"],
                        "entity_repr": item["entity_repr"],
                        "message": item["message"],
                        "created_at": item["created_at"],
                        "actor": {
                            "id": item["actor_id"],
                            "username": item["actor__username"],
                            "email": item["actor__email"],
                        }
                        if item["actor_id"]
                        else None,
                    }
                    for item in recent_activities
                ],
                "assignment_trends": assignment_trends,
                "meta": {
                    "warranty_days": warranty_days,
                    "trend_days": trend_days,
                    "recent_limit": recent_limit,
                },
            }
        )

    @staticmethod
    def _merge_trends(assignments_by_day, returns_by_day):
        trends = OrderedDict()

        for item in assignments_by_day:
            key = item["period"].isoformat()
            trends[key] = {"period": key, "assigned": item["assigned"], "returned": 0}

        for item in returns_by_day:
            key = item["period"].isoformat()
            trends.setdefault(key, {"period": key, "assigned": 0, "returned": 0})
            trends[key]["returned"] = item["returned"]

        return list(OrderedDict(sorted(trends.items())).values())


# =============================================================================
#  1. ASSET SUMMARY — assets grouped by status for Chart.js doughnut/pie
# =============================================================================

class AssetSummaryView(APIView):
    """
    Returns asset counts grouped by status.
    Optimized for Chart.js doughnut/pie chart: { labels: [...], datasets: [{ data: [...] }] }
    """

    permission_classes = [IsViewerOrAbove]

    @extend_schema(summary="Asset summary by status", tags=["Reports"])
    def get(self, request):
        status_counts = (
            Asset.objects.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )
        status_labels = {
            AssetStatus.AVAILABLE: "Available",
            AssetStatus.ASSIGNED: "Assigned",
            AssetStatus.MAINTENANCE: "Under Maintenance",
            AssetStatus.LOST: "Lost / Stolen",
            AssetStatus.DISPOSED: "Disposed",
            AssetStatus.RETIRED: "Retired",
        }

        labels = []
        data = []
        colors = {
            AssetStatus.AVAILABLE: "#34D399",
            AssetStatus.ASSIGNED: "#38BDF8",
            AssetStatus.MAINTENANCE: "#FBBF24",
            AssetStatus.LOST: "#F87171",
            AssetStatus.DISPOSED: "#9CA3AF",
            AssetStatus.RETIRED: "#6B7280",
        }
        background_colors = []

        status_map = {item["status"]: item["count"] for item in status_counts}
        for status_val in AssetStatus.values:
            labels.append(status_labels.get(status_val, status_val.title()))
            data.append(status_map.get(status_val, 0))
            background_colors.append(colors.get(status_val, "#9CA3AF"))

        total = sum(data)

        return Response(
            {
                "labels": labels,
                "datasets": [
                    {
                        "data": data,
                        "backgroundColor": background_colors,
                        "borderColor": "#0B0E14",
                        "borderWidth": 2,
                    }
                ],
                "total": total,
            }
        )


# =============================================================================
#  2. WARRANTY EXPIRY REPORT — assets with warranty expiring by month
# =============================================================================

class WarrantyExpiryReportView(APIView):
    """
    Returns warranty expiry counts grouped by month.
    Optimized for Chart.js bar chart: { labels: [month names], datasets: [{ data: [...] }] }
    """

    permission_classes = [IsViewerOrAbove]

    @extend_schema(
        summary="Warranty expiry report",
        tags=["Reports"],
        parameters=[
            OpenApiParameter("months", OpenApiTypes.INT, description="Months ahead to look. Default: 12."),
        ],
    )
    def get(self, request):
        params = MonthQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        months_ahead = params.validated_data["months"]

        today = timezone.localdate()
        expiry_limit = today + timedelta(days=months_ahead * 30)

        expired_count = Asset.objects.filter(warranty_expiry__lt=today).count()
        no_warranty_count = Asset.objects.filter(warranty_expiry__isnull=True).count()

        warranty_assets = Asset.objects.filter(
            warranty_expiry__gte=today,
            warranty_expiry__lte=expiry_limit,
        )

        monthly = (
            warranty_assets.annotate(
                month=TruncMonth("warranty_expiry"),
                month_label=Case(
                    When(
                        warranty_expiry__month=1, then=Value("Jan")
                    ),
                    When(
                        warranty_expiry__month=2, then=Value("Feb")
                    ),
                    When(
                        warranty_expiry__month=3, then=Value("Mar")
                    ),
                    When(
                        warranty_expiry__month=4, then=Value("Apr")
                    ),
                    When(
                        warranty_expiry__month=5, then=Value("May")
                    ),
                    When(
                        warranty_expiry__month=6, then=Value("Jun")
                    ),
                    When(
                        warranty_expiry__month=7, then=Value("Jul")
                    ),
                    When(
                        warranty_expiry__month=8, then=Value("Aug")
                    ),
                    When(
                        warranty_expiry__month=9, then=Value("Sep")
                    ),
                    When(
                        warranty_expiry__month=10, then=Value("Oct")
                    ),
                    When(
                        warranty_expiry__month=11, then=Value("Nov")
                    ),
                    When(
                        warranty_expiry__month=12, then=Value("Dec")
                    ),
                    output_field=CharField(),
                ),
            )
            .values("month", "month_label")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        labels = []
        data = []
        for item in monthly:
            labels.append(
                f"{item['month_label']} {item['month'].year}"
                if item["month"]
                else "Unknown"
            )
            data.append(item["count"])

        # Top 5 expiring soonest detail list
        expiring_soonest = list(
            Asset.objects.filter(
                warranty_expiry__gte=today,
                warranty_expiry__lte=expiry_limit,
            )
            .order_by("warranty_expiry")
            .values("name", "asset_tag", "serial_number", "warranty_expiry", "manufacturer", "model")[:5]
        )

        return Response(
            {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Warranty Expirations",
                        "data": data,
                        "backgroundColor": "rgba(251, 191, 36, 0.7)",
                        "borderColor": "#FBBF24",
                        "borderWidth": 2,
                        "borderRadius": 4,
                    }
                ],
                "summary": {
                    "total_assets_with_warranty": Asset.objects.exclude(
                        warranty_expiry__isnull=True
                    ).count(),
                    "expired": expired_count,
                    "no_warranty": no_warranty_count,
                    "expiring_in_range": sum(data),
                    "months_ahead": months_ahead,
                },
                "expiring_soonest": [
                    {
                        "name": item["name"],
                        "asset_tag": item["asset_tag"],
                        "serial_number": item["serial_number"],
                        "warranty_expiry": item["warranty_expiry"],
                        "manufacturer": item["manufacturer"],
                        "model": item["model"],
                    }
                    for item in expiring_soonest
                ],
            }
        )


# =============================================================================
#  3. REPAIR REPORT — maintenance records grouped by status and type
# =============================================================================

class RepairReportView(APIView):
    """
    Returns maintenance/repair statistics grouped by status and type.
    Optimized for Chart.js bar/doughnut charts.
    """

    permission_classes = [IsViewerOrAbove]

    @extend_schema(
        summary="Repair/maintenance report",
        tags=["Reports"],
        parameters=[
            OpenApiParameter("days", OpenApiTypes.INT, description="Days back. Default: 90."),
        ],
    )
    def get(self, request):
        params = DaysQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        days_back = params.validated_data["days"]
        since = timezone.now() - timedelta(days=days_back)

        # Status distribution (doughnut chart)
        status_counts = (
            MaintenanceRecord.objects.filter(created_at__gte=since)
            .values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )
        status_labels_map = {
            "open": "Open",
            "in_progress": "In Progress",
            "completed": "Completed",
            "cancelled": "Cancelled",
            "on_hold": "On Hold",
        }
        status_colors = {
            "open": "rgba(251, 191, 36, 0.8)",
            "in_progress": "rgba(56, 189, 248, 0.8)",
            "completed": "rgba(52, 211, 153, 0.8)",
            "cancelled": "rgba(156, 163, 175, 0.8)",
            "on_hold": "rgba(168, 85, 247, 0.8)",
        }
        status_data = {}
        for item in status_counts:
            status_data[item["status"]] = item["count"]

        status_labels = []
        status_dataset = []
        status_bg = []
        for s_val in ["open", "in_progress", "completed", "cancelled", "on_hold"]:
            status_labels.append(status_labels_map.get(s_val, s_val))
            status_dataset.append(status_data.get(s_val, 0))
            status_bg.append(status_colors.get(s_val, "rgba(156, 163, 175, 0.8)"))

        # Type distribution (bar chart)
        type_counts = (
            MaintenanceRecord.objects.filter(created_at__gte=since)
            .values("maintenance_type")
            .annotate(count=Count("id"))
            .order_by("maintenance_type")
        )
        type_labels_map = {
            "preventive": "Preventive",
            "corrective": "Corrective",
            "emergency": "Emergency",
            "scheduled": "Scheduled",
        }
        type_labels = []
        type_dataset = []
        for item in type_counts:
            type_labels.append(
                type_labels_map.get(item["maintenance_type"], item["maintenance_type"].title())
            )
            type_dataset.append(item["count"])

        # Priority distribution
        priority_counts = (
            MaintenanceRecord.objects.filter(created_at__gte=since)
            .values("priority")
            .annotate(count=Count("id"))
            .order_by("priority")
        )
        priority_order = ["critical", "high", "medium", "low"]
        priority_labels_map = {
            "critical": "Critical",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
        }
        priority_colors = {
            "critical": "#F87171",
            "high": "#FBBF24",
            "medium": "#38BDF8",
            "low": "#9CA3AF",
        }
        priority_map = {p["priority"]: p["count"] for p in priority_counts}
        priority_labels = []
        priority_dataset = []
        priority_bg = []
        for p in priority_order:
            priority_labels.append(priority_labels_map.get(p, p))
            priority_dataset.append(priority_map.get(p, 0))
            priority_bg.append(priority_colors.get(p, "#9CA3AF"))

        # Totals
        total_records = sum(status_dataset)
        total_cost = (
            MaintenanceRecord.objects.filter(created_at__gte=since)
            .aggregate(total=Count("id"), sum_cost=Sum("cost"))
        )

        return Response(
            {
                "by_status": {
                    "labels": status_labels,
                    "datasets": [
                        {
                            "data": status_dataset,
                            "backgroundColor": status_bg,
                            "borderWidth": 1,
                        }
                    ],
                },
                "by_type": {
                    "labels": type_labels,
                    "datasets": [
                        {
                            "label": "Maintenance by Type",
                            "data": type_dataset,
                            "backgroundColor": "rgba(56, 189, 248, 0.7)",
                            "borderColor": "#38BDF8",
                            "borderWidth": 2,
                        }
                    ],
                },
                "by_priority": {
                    "labels": priority_labels,
                    "datasets": [
                        {
                            "data": priority_dataset,
                            "backgroundColor": priority_bg,
                            "borderWidth": 1,
                        }
                    ],
                },
                "summary": {
                    "total_records": total_records,
                    "total_cost": float(total_cost.get("sum_cost") or 0),
                    "period_days": days_back,
                },
            }
        )


# =============================================================================
#  4. LOST & DAMAGED ASSETS REPORT
# =============================================================================

class LostDamagedAssetsView(APIView):
    """
    Returns counts and details of lost and damaged assets.
    Optimized for Chart.js visualization.
    """

    permission_classes = [IsViewerOrAbove]

    @extend_schema(summary="Lost and damaged assets", tags=["Reports"])
    def get(self, request):
        lost_assets = Asset.objects.filter(status=AssetStatus.LOST)
        damaged_assets = Asset.objects.filter(
            Q(condition=AssetCondition.DAMAGED)
            | Q(condition=AssetCondition.NEEDS_REPAIR)
        ).exclude(status=AssetStatus.LOST)

        condition_counts = (
            Asset.objects.values("condition")
            .annotate(count=Count("id"))
            .order_by("condition")
        )
        condition_labels_map = {
            AssetCondition.NEW: "New",
            AssetCondition.GOOD: "Good",
            AssetCondition.FAIR: "Fair",
            AssetCondition.DAMAGED: "Damaged",
            AssetCondition.NEEDS_REPAIR: "Needs Repair",
            AssetCondition.RETIRED: "Retired",
        }
        condition_colors = {
            AssetCondition.NEW: "#34D399",
            AssetCondition.GOOD: "#38BDF8",
            AssetCondition.FAIR: "#FBBF24",
            AssetCondition.DAMAGED: "#F87171",
            AssetCondition.NEEDS_REPAIR: "#FB923C",
            AssetCondition.RETIRED: "#9CA3AF",
        }
        cond_map = {c["condition"]: c["count"] for c in condition_counts}
        cond_labels = []
        cond_data = []
        cond_bg = []
        for c_val in AssetCondition.values:
            cond_labels.append(condition_labels_map.get(c_val, c_val.title()))
            cond_data.append(cond_map.get(c_val, 0))
            cond_bg.append(condition_colors.get(c_val, "#9CA3AF"))

        return Response(
            {
                "condition_distribution": {
                    "labels": cond_labels,
                    "datasets": [
                        {
                            "data": cond_data,
                            "backgroundColor": cond_bg,
                            "borderWidth": 1,
                        }
                    ],
                },
                "lost_assets": {
                    "count": lost_assets.count(),
                    "details": list(
                        lost_assets.values(
                            "id", "name", "asset_tag", "serial_number", "category", "location"
                        ).order_by("-updated_at")
                    ),
                },
                "damaged_assets": {
                    "count": damaged_assets.count(),
                    "details": list(
                        damaged_assets.values(
                            "id", "name", "asset_tag", "serial_number", "category", "condition", "location"
                        ).order_by("-updated_at")
                    ),
                },
                "summary": {
                    "total_lost": lost_assets.count(),
                    "total_damaged": damaged_assets.count(),
                    "total_affected": lost_assets.count() + damaged_assets.count(),
                },
            }
        )


# =============================================================================
#  5. ASSIGNMENTS BY DEPARTMENT — grouped by department for Chart.js bar chart
# =============================================================================

class AssignmentsByDepartmentView(APIView):
    """
    Returns assignment counts grouped by department.
    Optimized for Chart.js horizontal bar chart.
    """

    permission_classes = [IsViewerOrAbove]

    @extend_schema(
        summary="Assignments by department",
        tags=["Reports"],
        parameters=[
            OpenApiParameter("days", OpenApiTypes.INT, description="Days back. Default: 365."),
        ],
    )
    def get(self, request):
        params = DaysQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        days_back = params.validated_data["days"]
        since = timezone.now() - timedelta(days=days_back)

        # Total assignments by department
        dept_totals = (
            Assignment.objects.filter(assigned_at__gte=since)
            .values("department")
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        # Active assignments by department
        dept_active = (
            Assignment.objects.filter(assigned_at__gte=since, status="active")
            .values("department")
            .annotate(active=Count("id"))
            .order_by("department")
        )
        active_map = {d["department"]: d["active"] for d in dept_active}

        labels = []
        total_data = []
        active_data = []
        for item in dept_totals:
            dept = item["department"] if item["department"] else "Unspecified"
            labels.append(dept)
            total_data.append(item["total"])
            active_data.append(active_map.get(item["department"], 0))

        grand_total = sum(total_data)
        avg_per_dept = round(grand_total / len(total_data)) if total_data else 0

        return Response(
            {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Total Assignments",
                        "data": total_data,
                        "backgroundColor": "rgba(56, 189, 248, 0.7)",
                        "borderColor": "#38BDF8",
                        "borderWidth": 2,
                        "borderRadius": 4,
                    },
                    {
                        "label": "Active Assignments",
                        "data": active_data,
                        "backgroundColor": "rgba(52, 211, 153, 0.7)",
                        "borderColor": "#34D399",
                        "borderWidth": 2,
                        "borderRadius": 4,
                    },
                ],
                "summary": {
                    "total_assignments": grand_total,
                    "total_departments": len(labels),
                    "average_per_department": avg_per_dept,
                    "period_days": days_back,
                },
            }
        )


# =============================================================================
#  6. ASSETS BY LOCATION — grouped by location for Chart.js bar chart
# =============================================================================

class AssetsByLocationView(APIView):
    """
    Returns asset counts grouped by location.
    Optimized for Chart.js horizontal bar chart.
    """

    permission_classes = [IsViewerOrAbove]

    @extend_schema(summary="Assets by location", tags=["Reports"])
    def get(self, request):
        locations = (
            Asset.objects.annotate(
                location_label=Case(
                    When(location="", then=Value("Unspecified")),
                    default=F("location"),
                    output_field=CharField(),
                )
            )
            .values("location_label")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        labels = []
        data = []
        for item in locations:
            labels.append(item["location_label"])
            data.append(item["count"])

        total_assets = sum(data)

        # Generate colors based on value intensity
        colors = []
        max_count = max(data) if data else 1
        for val in data:
            intensity = 0.3 + (val / max_count) * 0.6
            colors.append(f"rgba(212, 162, 78, {intensity})")

        return Response(
            {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Assets by Location",
                        "data": data,
                        "backgroundColor": colors,
                        "borderColor": "#D4A24E",
                        "borderWidth": 2,
                        "borderRadius": 4,
                    }
                ],
                "summary": {
                    "total_assets": total_assets,
                    "total_locations": len(labels),
                    "top_location": labels[0] if labels else None,
                    "top_location_count": data[0] if data else 0,
                },
            }
        )


# =============================================================================
#  7. ASSETS BY DEVICE TYPE — grouped by category for Chart.js doughnut/pie
# =============================================================================

class AssetsByDeviceTypeView(APIView):
    """
    Returns asset counts grouped by device type (category).
    Optimized for Chart.js doughnut/pie chart.
    """

    permission_classes = [IsViewerOrAbove]

    @extend_schema(summary="Assets by device type", tags=["Reports"])
    def get(self, request):
        type_counts = (
            Asset.objects.values("category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        category_labels = dict(AssetCategory.choices)
        chart_colors = [
            "#38BDF8",
            "#34D399",
            "#FBBF24",
            "#F87171",
            "#A78BFA",
            "#F472B6",
            "#FB923C",
            "#2DD4BF",
            "#E879F9",
            "#60A5FA",
            "#F59E0B",
            "#10B981",
            "#6B7280",
            "#9CA3AF",
        ]

        labels = []
        data = []
        colors = []
        others_count = 0

        for i, item in enumerate(type_counts):
            label = category_labels.get(item["category"], item["category"].title())
            if i < 7:
                labels.append(label)
                data.append(item["count"])
                colors.append(chart_colors[i % len(chart_colors)])
            else:
                others_count += item["count"]

        if others_count > 0:
            labels.append("Others")
            data.append(others_count)
            colors.append("#9CA3AF")

        total = sum(data)

        return Response(
            {
                "labels": labels,
                "datasets": [
                    {
                        "data": data,
                        "backgroundColor": colors,
                        "borderColor": "#0B0E14",
                        "borderWidth": 2,
                    }
                ],
                "total": total,
                "category_details": list(type_counts),
            }
        )


# =============================================================================
#  8. MONTHLY ASSIGNMENT STATISTICS — monthly counts for Chart.js line chart
# =============================================================================

class MonthlyAssignmentStatsView(APIView):
    """
    Returns monthly assignment and return counts.
    Optimized for Chart.js line chart: { labels: [month/year], datasets: [{ data: [...] }] }
    """

    permission_classes = [IsViewerOrAbove]

    @extend_schema(
        summary="Monthly assignment statistics",
        tags=["Reports"],
        parameters=[
            OpenApiParameter("months", OpenApiTypes.INT, description="Months back. Default: 12."),
        ],
    )
    def get(self, request):
        params = MonthQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        months_back = params.validated_data["months"]
        since = timezone.now() - timedelta(days=months_back * 30)

        # Assignments grouped by month
        assignments_monthly = (
            Assignment.objects.filter(assigned_at__gte=since)
            .annotate(month=TruncMonth("assigned_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        # Returns grouped by month
        returns_monthly = (
            Assignment.objects.filter(returned_at__gte=since)
            .annotate(month=TruncMonth("returned_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        # Overdue counts by month
        overdue_monthly = (
            Assignment.objects.filter(
                status="active",
                due_at__gte=since,
                due_at__lt=timezone.now(),
            )
            .annotate(month=TruncMonth("due_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        # Merge all data by month
        assign_map = {m["month"].strftime("%Y-%m"): m["count"] for m in assignments_monthly if m["month"]}
        return_map = {m["month"].strftime("%Y-%m"): m["count"] for m in returns_monthly if m["month"]}
        overdue_map = {m["month"].strftime("%Y-%m"): m["count"] for m in overdue_monthly if m["month"]}

        # Build all months in range
        labels = []
        assigned_data = []
        returned_data = []
        overdue_data = []

        for i in range(months_back - 1, -1, -1):
            dt = timezone.now() - timedelta(days=30 * i)
            key = dt.strftime("%Y-%m")
            label = dt.strftime("%b %Y")
            labels.append(label)
            assigned_data.append(assign_map.get(key, 0))
            returned_data.append(return_map.get(key, 0))
            overdue_data.append(overdue_map.get(key, 0))

        # Active counts by status at the end of each month
        total_active = Assignment.objects.filter(status="active").count()
        total_returned = Assignment.objects.filter(status="returned").count()
        total_overdue = Assignment.objects.filter(status="active", due_at__lt=timezone.now()).count()

        return Response(
            {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Assignments",
                        "data": assigned_data,
                        "borderColor": "#38BDF8",
                        "backgroundColor": "rgba(56, 189, 248, 0.1)",
                        "borderWidth": 3,
                        "fill": True,
                        "tension": 0.3,
                        "pointRadius": 4,
                        "pointHoverRadius": 6,
                    },
                    {
                        "label": "Returns",
                        "data": returned_data,
                        "borderColor": "#34D399",
                        "backgroundColor": "rgba(52, 211, 153, 0.1)",
                        "borderWidth": 3,
                        "fill": True,
                        "tension": 0.3,
                        "pointRadius": 4,
                        "pointHoverRadius": 6,
                    },
                    {
                        "label": "Overdue",
                        "data": overdue_data,
                        "borderColor": "#F87171",
                        "backgroundColor": "rgba(248, 113, 113, 0.1)",
                        "borderWidth": 2,
                        "borderDash": [5, 5],
                        "fill": False,
                        "tension": 0.3,
                        "pointRadius": 3,
                        "pointHoverRadius": 5,
                    },
                ],
                "summary": {
                    "total_active": total_active,
                    "total_returned": total_returned,
                    "total_overdue": total_overdue,
                    "months_back": months_back,
                    "period": {
                        "start": labels[0] if labels else None,
                        "end": labels[-1] if labels else None,
                    },
                },
            }
        )