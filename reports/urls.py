from django.urls import path

from .views import (
    AssetsByDeviceTypeView,
    AssetsByLocationView,
    AssetSummaryView,
    AssignmentsByDepartmentView,
    DashboardSummaryView,
    LostDamagedAssetsView,
    MonthlyAssignmentStatsView,
    RepairReportView,
    WarrantyExpiryReportView,
)

app_name = "reports"

urlpatterns = [
    path("dashboard/", DashboardSummaryView.as_view(), name="dashboard"),
    # 1. Asset summary by status
    path("asset-summary/", AssetSummaryView.as_view(), name="asset-summary"),
    # 2. Warranty expiry report
    path("warranty-expiry/", WarrantyExpiryReportView.as_view(), name="warranty-expiry"),
    # 3. Repair/maintenance report
    path("repairs/", RepairReportView.as_view(), name="repair-report"),
    # 4. Lost & damaged assets
    path("lost-damaged/", LostDamagedAssetsView.as_view(), name="lost-damaged"),
    # 5. Assignments by department
    path("assignments-by-department/", AssignmentsByDepartmentView.as_view(), name="assignments-by-department"),
    # 6. Assets by location
    path("assets-by-location/", AssetsByLocationView.as_view(), name="assets-by-location"),
    # 7. Assets by device type
    path("assets-by-device-type/", AssetsByDeviceTypeView.as_view(), name="assets-by-device-type"),
    # 8. Monthly assignment statistics
    path("monthly-assignments/", MonthlyAssignmentStatsView.as_view(), name="monthly-assignments"),
]