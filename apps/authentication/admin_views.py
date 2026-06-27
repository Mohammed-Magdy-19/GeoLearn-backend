from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework.pagination import PageNumberPagination

from .admin_serializers import AdminUserSerializer

User = get_user_model()

class AdminUserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

class UserListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer
    pagination_class = AdminUserPagination

    def get_queryset(self):
        queryset = User.objects.all().order_by("-date_joined")
        
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(full_name__icontains=search) |
                Q(email__icontains=search)
            )
            
        role = self.request.query_params.get("role")
        if role and role != "all":
            if role == "admin":
                queryset = queryset.filter(is_superuser=True)
            elif role == "instructor":
                queryset = queryset.filter(is_staff=True, is_superuser=False)
            elif role == "student":
                queryset = queryset.filter(is_staff=False, is_superuser=False)
                
        is_active = self.request.query_params.get("is_active")
        if is_active and is_active != "all":
            active_val = is_active.lower() == "true"
            queryset = queryset.filter(is_active=active_val)
            
        return queryset

class UserDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer
    queryset = User.objects.all()

class UserUpdateRoleView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        is_staff = request.data.get("is_staff")
        is_superuser = request.data.get("is_superuser")
        
        if is_staff is not None:
            user.is_staff = bool(is_staff)
        if is_superuser is not None:
            user.is_superuser = bool(is_superuser)
            
        user.save()
        return Response(AdminUserSerializer(user).data)

class UserToggleActiveView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.is_active = not user.is_active
        user.save()
        return Response(AdminUserSerializer(user).data)
