from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import AssignmentFilter
from .models import Assignment
from .pagination import AssignmentPagination
from .permissions import AssignmentPermission
from .serializers import AssignmentListSerializer, AssignmentReturnSerializer, AssignmentSerializer


class AssignmentListCreateView(generics.ListCreateAPIView):
    queryset = Assignment.objects.select_related("asset", "assigned_to", "assigned_by", "created_by", "updated_by")
    permission_classes = [AssignmentPermission]
    pagination_class = AssignmentPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AssignmentFilter
    search_fields = [
        "asset__asset_tag",
        "asset__serial_number",
        "asset__name",
        "asset__manufacturer",
        "asset__model",
        "assigned_to__username",
        "assigned_to__email",
        "assigned_to__first_name",
        "assigned_to__last_name",
        "department",
        "expected_location",
        "notes",
    ]
    ordering_fields = [
        "assigned_at",
        "due_at",
        "returned_at",
        "status",
        "department",
        "asset__asset_tag",
        "assigned_to__username",
        "created_at",
        "updated_at",
    ]
    ordering = ["-assigned_at"]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return AssignmentListSerializer
        return AssignmentSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(
            assigned_by=self.request.user,
            created_by=self.request.user,
            updated_by=self.request.user,
        )


class AssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Assignment.objects.select_related("asset", "assigned_to", "assigned_by", "created_by", "updated_by")
    serializer_class = AssignmentSerializer
    permission_classes = [AssignmentPermission]
    http_method_names = ["get", "put", "patch", "delete", "head", "options"]

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()


class AssignmentReturnView(APIView):
    permission_classes = [AssignmentPermission]

    @transaction.atomic
    def post(self, request, pk):
        assignment = generics.get_object_or_404(
            Assignment.objects.select_related("asset", "assigned_to", "assigned_by"),
            pk=pk,
        )
        self.check_object_permissions(request, assignment)
        serializer = AssignmentReturnSerializer(
            data=request.data,
            context={"request": request, "assignment": assignment},
        )
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save()
        return Response(AssignmentSerializer(assignment, context={"request": request}).data, status=status.HTTP_200_OK)
