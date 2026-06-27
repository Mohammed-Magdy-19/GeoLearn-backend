from rest_framework import serializers
from apps.courses.models import Course, Module, Lesson, Summary, MetadataEntry, SpatialDataEntry

class AdminLessonSerializer(serializers.ModelSerializer):
    duration_display = serializers.SerializerMethodField()
    has_video = serializers.BooleanField(read_only=True)
    lesson_file_url = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            "id",
            "module",
            "title",
            "description",
            "order_index",
            "duration_seconds",
            "duration_display",
            "is_free_preview",
            "has_video",
            "secure_video_id",
            "lesson_file",
            "lesson_file_url",
            "created_at",
        ]
        read_only_fields = ["id", "duration_display", "has_video", "created_at"]

    def get_duration_display(self, obj: Lesson) -> str:
        minutes, seconds = divmod(obj.duration_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def get_lesson_file_url(self, obj: Lesson) -> str | None:
        if obj.lesson_file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.lesson_file.url)
        return None

class AdminModuleSerializer(serializers.ModelSerializer):
    lessons = AdminLessonSerializer(many=True, read_only=True)
    lesson_count = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            "id",
            "course",
            "title",
            "description",
            "order_index",
            "lesson_count",
            "lessons",
            "created_at",
        ]
        read_only_fields = ["id", "lesson_count", "lessons", "created_at"]

    def get_lesson_count(self, obj: Module) -> int:
        return obj.lessons.count()

class AdminCourseSerializer(serializers.ModelSerializer):
    module_count = serializers.SerializerMethodField()
    lesson_count = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "thumbnail",
            "thumbnail_url",
            "cover_image",
            "cover_image_url",
            "price_egp",
            "is_published",
            "module_count",
            "lesson_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "thumbnail_url", "cover_image_url", "module_count", "lesson_count", "created_at", "updated_at"]

    def get_module_count(self, obj: Course) -> int:
        return obj.modules.count()

    def get_lesson_count(self, obj: Course) -> int:
        return Lesson.objects.filter(module__course=obj).count()

    def get_thumbnail_url(self, obj: Course) -> str | None:
        if obj.thumbnail:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
        return None

    def get_cover_image_url(self, obj: Course) -> str | None:
        if obj.cover_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.cover_image.url)
        return None

class AdminCourseDetailSerializer(AdminCourseSerializer):
    modules = AdminModuleSerializer(many=True, read_only=True)

    class Meta(AdminCourseSerializer.Meta):
        fields = AdminCourseSerializer.Meta.fields + ["modules"]


class AdminSummarySerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = Summary
        fields = [
            "id",
            "title",
            "description",
            "file",
            "file_url",
            "file_name",
            "file_size_display",
            "source",
            "source_url",
            "subject",
            "is_published",
            "download_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "file_url", "file_name", "file_size_display",
            "download_count",
            "created_at", "updated_at",
        ]

    def get_file_url(self, obj: Summary) -> str | None:
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None

    def get_file_name(self, obj: Summary) -> str:
        return obj.file_name

    def get_file_size_display(self, obj: Summary) -> str:
        size = obj.file_size_bytes
        if size == 0:
            return "0 B"
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"


class _FileFieldsMixin:
    """Shared file-related method fields."""

    def get_file_url(self, obj) -> str | None:
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None

    def get_file_name(self, obj) -> str:
        return obj.file_name

    def get_file_size_display(self, obj) -> str:
        size = obj.file_size_bytes
        if size == 0:
            return "0 B"
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"


class AdminMetadataSerializer(_FileFieldsMixin, serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = MetadataEntry
        fields = [
            "id", "title", "description", "category",
            "source", "source_url",
            "file", "file_url", "file_name", "file_size_display",
            "is_published", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "file_url", "file_name", "file_size_display",
            "created_at", "updated_at",
        ]


class AdminSpatialDataSerializer(_FileFieldsMixin, serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()
    data_type_display = serializers.SerializerMethodField()

    class Meta:
        model = SpatialDataEntry
        fields = [
            "id", "title", "description",
            "latitude", "longitude", "data_type", "data_type_display",
            "category", "source", "source_url",
            "file", "file_url", "file_name", "file_size_display",
            "geojson_data", "is_published",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "file_url", "file_name", "file_size_display",
            "data_type_display", "created_at", "updated_at",
        ]

    def get_data_type_display(self, obj: SpatialDataEntry) -> str:
        return obj.get_data_type_display()
