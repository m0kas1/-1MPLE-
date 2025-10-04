from rest_framework import serializers
from .models import Event, QueueEntry, User

class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ['id', 'name', 'description']

class QueueEntrySerializer(serializers.ModelSerializer):
    user_telegram = serializers.IntegerField(source='user.telegram_id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = QueueEntry
        fields = ['id', 'event', 'user', 'user_telegram', 'username', 'status', 'created_at', 'called_at', 'served_at']
        read_only_fields = ['id', 'created_at', 'called_at', 'served_at']
