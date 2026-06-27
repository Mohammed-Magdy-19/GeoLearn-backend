from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class AdminUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "full_name",
            "username",
            "email",
            "is_staff",
            "is_superuser",
            "is_active",
            "date_joined",
            "last_login",
            "role",
        ]
        read_only_fields = ["id", "date_joined", "last_login", "role"]

    def get_role(self, obj) -> str:
        if obj.is_superuser:
            return "admin"
        elif obj.is_staff:
            return "instructor"
        return "student"
