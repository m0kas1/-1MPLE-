# models.py
from django.db import models

class Purchase(models.Model):
    name = models.CharField(max_length=200)
    product = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} — {self.product}"
