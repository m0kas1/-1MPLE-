# ---------------------- Django DRF example ----------------------
# Этот кусочек — пример на Django + Django REST Framework, чтобы принимать POST.
# Вставьте его в своё Django-приложение (models.py / serializers.py / views.py).

# models.py
# from django.db import models
#
# class Purchase(models.Model):
#     name = models.CharField(max_length=200)
#     product = models.CharField(max_length=200)
#     created_at = models.DateTimeField(auto_now_add=True)
#
#     def __str__(self):
#         return f"{self.name} — {self.product}"

# serializers.py
# from rest_framework import serializers
# from .models import Purchase
#
# class PurchaseSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Purchase
#         fields = ['id', 'name', 'product', 'created_at']

# views.py
# from rest_framework.decorators import api_view, permission_classes
# from rest_framework.permissions import AllowAny
# from rest_framework.response import Response
# from rest_framework import status
# from .serializers import PurchaseSerializer

# @api_view(['POST'])
# @permission_classes([AllowAny])  # для теста; на проде добавьте аутентификацию
# def create_purchase(request):
#     serializer = PurchaseSerializer(data=request.data)
#     if serializer.is_valid():
#         serializer.save()
#         return Response(serializer.data, status=status.HTTP_201_CREATED)
#     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Не забудьте добавить маршрут в urls.py
# path('api/purchases/', views.create_purchase),