from django.urls import path

from .views import AssignmentDetailView, AssignmentListCreateView, AssignmentReturnView

app_name = "assignments"

urlpatterns = [
    path("", AssignmentListCreateView.as_view(), name="assignment-list-create"),
    path("<int:pk>/", AssignmentDetailView.as_view(), name="assignment-detail"),
    path("<int:pk>/return/", AssignmentReturnView.as_view(), name="assignment-return"),
]
