from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .admin_views import (
    StatsView,
    EnrollmentTrendsView,
    CoursePopularityView,
    AdminCourseViewSet,
    AdminModuleViewSet,
    AdminLessonViewSet,
    VideoUploadView,
    VideoDeleteView,
    AdminSummaryViewSet,
    AdminMetadataViewSet,
    AdminSpatialDataViewSet,
)
from apps.authentication.admin_views import (
    UserListView,
    UserDetailView,
    UserUpdateRoleView,
    UserToggleActiveView,
)

router = DefaultRouter()
router.register("courses", AdminCourseViewSet, basename="admin-course")
router.register("modules", AdminModuleViewSet, basename="admin-module")
router.register("lessons", AdminLessonViewSet, basename="admin-lesson")
router.register("summaries", AdminSummaryViewSet, basename="admin-summary")
router.register("metadata", AdminMetadataViewSet, basename="admin-metadata")
router.register("spatial-data", AdminSpatialDataViewSet, basename="admin-spatial-data")

urlpatterns = [
    # Router endpoints (courses/, modules/, lessons/, summaries/, metadata/, spatial-data/)
    path("", include(router.urls)),
    
    # Stats endpoints
    path("stats/", StatsView.as_view(), name="admin-stats"),
    path("stats/enrollment-trends/", EnrollmentTrendsView.as_view(), name="admin-stats-trends"),
    path("stats/course-popularity/", CoursePopularityView.as_view(), name="admin-stats-popularity"),
    
    # Video upload / delete
    path("videos/upload/", VideoUploadView.as_view(), name="admin-video-upload"),
    path("videos/<str:secure_video_id>/", VideoDeleteView.as_view(), name="admin-video-delete"),
    
    # User endpoints
    path("users/", UserListView.as_view(), name="admin-users-list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="admin-user-detail"),
    path("users/<int:pk>/role/", UserUpdateRoleView.as_view(), name="admin-user-role"),
    path("users/<int:pk>/toggle-active/", UserToggleActiveView.as_view(), name="admin-user-toggle-active"),
]
