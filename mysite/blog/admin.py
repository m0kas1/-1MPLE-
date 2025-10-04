from django.contrib import admin
from .models import Event, User, QueueEntry

admin.site.register(Event)
admin.site.register(User)
admin.site.register(QueueEntry)

