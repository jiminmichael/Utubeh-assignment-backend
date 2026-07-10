from rest_framework import generics, status
from rest_framework.response import Response
from django.shortcuts import render
from rest_framework_csv.renderers import CSVRenderer

from activity_logs.models import ActivityLog


class ExportMixin:
    """
    A mixin that adds a CSV export action to a viewset.
    This is intended to be used with a view that has `get_export_serializer_class`.
    """
    renderer_classes = [CSVRenderer]

    def get_csv_filename(self):
        """Return the filename for the exported CSV."""
        return f"{self.queryset.model._meta.model_name}_export.csv"

    def get(self, request, *args, **kwargs):
        """Handle GET request to export data as CSV."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer_class = self.get_serializer_class()
        serializer = serializer_class(queryset, many=True, context={'request': request})

        headers = {
            'Content-Disposition': f'attachment; filename="{self.get_csv_filename()}"'
        }

        # Log the export action
        ActivityLog.log(
            actor=request.user,
            action=ActivityLog.ActivityAction.EXPORT,
            entity_type=self.queryset.model._meta.verbose_name_plural,
            message=f"Exported {queryset.count()} records from {self.queryset.model._meta.verbose_name_plural}.",
        )

        return Response(serializer.data, headers=headers, status=status.HTTP_200_OK)


class ExportListAPIView(generics.ListAPIView):
    """
    A generic ListAPIView that can be subclassed to provide an export endpoint.
    """
    pass # This is a placeholder for combining List and Export logic in the actual views.


class ExportAPIView(ExportMixin, generics.GenericAPIView):
    """
    A dedicated view for exporting data that reuses configuration from a list view.
    """
    def get_serializer_class(self):
        # Subclasses should override this to point to a specific serializer for export
        return self.serializer_class


# =============================================================================
#  Custom Error Views
# =============================================================================

def handler401(request, exception=None):
    return render(request, "error_401.html", status=401)


def handler403(request, exception=None):
    return render(request, "error_403.html", status=403)


def handler404(request, exception=None):
    return render(request, "error_404.html", status=404)


def handler500(request):
    return render(request, "error_500.html", status=500)