from django.contrib import admin
from django.urls import path, include
from .views import create_purchase
urlpatterns = [
    path('api/purchases/', create_purchase),
]