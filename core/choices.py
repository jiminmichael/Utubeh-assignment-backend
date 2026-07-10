from django.db import models


class AssetStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    ASSIGNED = "assigned", "Assigned"
    MAINTENANCE = "maintenance", "Under Maintenance"
    LOST = "lost", "Lost / Stolen"
    DISPOSED = "disposed", "Disposed"
    RETIRED = "retired", "Retired"


class AssetCategory(models.TextChoices):
    LAPTOP = "laptop", "Laptop"
    DESKTOP = "desktop", "Desktop"
    MONITOR = "monitor", "Monitor"
    KEYBOARD = "keyboard", "Keyboard"
    MOUSE = "mouse", "Mouse"
    PRINTER = "printer", "Printer"
    SCANNER = "scanner", "Scanner"
    SERVER = "server", "Server"
    NETWORK = "network", "Network Equipment"
    PHONE = "phone", "Phone"
    TABLET = "tablet", "Tablet"
    SOFTWARE = "software", "Software License"
    ACCESSORY = "accessory", "Accessory"
    OTHER = "other", "Other"


class AssetCondition(models.TextChoices):
    NEW = "new", "New"
    GOOD = "good", "Good"
    FAIR = "fair", "Fair"
    DAMAGED = "damaged", "Damaged"
    NEEDS_REPAIR = "needs_repair", "Needs Repair"
    RETIRED = "retired", "Retired"


class AssignmentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RETURNED = "returned", "Returned"
    OVERDUE = "overdue", "Overdue"
    LOST = "lost", "Lost"


class MaintenanceStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    ON_HOLD = "on_hold", "On Hold"


class MaintenancePriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class MaintenanceType(models.TextChoices):
    PREVENTIVE = "preventive", "Preventive"
    CORRECTIVE = "corrective", "Corrective"
    EMERGENCY = "emergency", "Emergency"
    SCHEDULED = "scheduled", "Scheduled"


class NotificationType(models.TextChoices):
    ASSIGNMENT = "assignment", "Assignment"
    MAINTENANCE = "maintenance", "Maintenance"
    WARRANTY = "warranty", "Warranty Expiry"
    OVERDUE = "overdue", "Overdue Return"
    SYSTEM = "system", "System Notification"
    REPORT = "report", "Report Ready"


class NotificationPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class ReportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ReportType(models.TextChoices):
    ASSET_INVENTORY = "asset_inventory", "Asset Inventory"
    ASSIGNMENT_HISTORY = "assignment_history", "Assignment History"
    MAINTENANCE_LOG = "maintenance_log", "Maintenance Log"
    DEPRECIATION = "depreciation", "Depreciation Report"
    CUSTOM = "custom", "Custom Report"


class ActivityAction(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    ASSIGN = "assign", "Assign"
    RETURN = "return", "Return"
    MAINTENANCE_REQUEST = "maintenance_request", "Maintenance Request"
    MAINTENANCE_COMPLETE = "maintenance_complete", "Maintenance Complete"
    LOGIN = "login", "Login"
    LOGOUT = "logout", "Logout"
    EXPORT = "export", "Export"
    OTHER = "other", "Other"
