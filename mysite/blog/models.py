from django.db import models

class User(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=150, blank=True, null=True)
    full_name = models.CharField(max_length=250, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Event(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    avg_service_minutes = models.PositiveIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class QueueEntry(models.Model):
    STATUS_CHOICES = (
        ('waiting', 'Waiting'),
        ('called', 'Called'),
        ('cancelled', 'Cancelled'),
        ('served', 'Served'),
    )
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='entries')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='queue_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    called_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
