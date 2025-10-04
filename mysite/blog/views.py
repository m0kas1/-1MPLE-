from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.conf import settings
from .models import Event, User, QueueEntry
from .serializers import EventSerializer, QueueEntrySerializer
from . import queue_utils
from django.utils import timezone

BOT_HEADER = "X-BOT-SECRET"

@api_view(['GET'])
@permission_classes([AllowAny])
def events_list(request):
    qs = Event.objects.all()
    return Response(EventSerializer(qs, many=True).data)

@api_view(['POST'])
@permission_classes([AllowAny])
def join_queue(request, event_id):
    # optional header check
    expected = getattr(settings, "BOT_SECRET", None)
    if expected:
        if request.headers.get(BOT_HEADER) != expected:
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data
    tg = data.get('telegram_id')
    if not tg:
        return Response({"detail": "telegram_id required"}, status=400)

    event = get_object_or_404(Event, id=event_id)
    user, _ = User.objects.get_or_create(telegram_id=int(tg), defaults={
        "username": data.get("username"),
        "full_name": data.get("full_name"),
    })

    # Добавляем в Redis, затем создаём запись в БД; при ошибке — откатим Redis
    try:
        pos = queue_utils.join_queue_redis(event.id, user.id)
    except Exception as e:
        return Response({"detail": f"Redis error: {e}"}, status=500)

    try:
        with transaction.atomic():
            entry, created = QueueEntry.objects.get_or_create(
                event=event, user=user, status='waiting',
                defaults={}
            )
    except Exception as e:
        # компенсируем: удалим из Redis
        try:
            queue_utils.leave_queue_redis(event.id, user.id)
        except Exception:
            pass
        return Response({"detail": f"DB error: {e}"}, status=500)

    return Response({"position": pos, "entry_id": entry.id}, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
def leave_queue(request, event_id):
    expected = getattr(settings, "BOT_SECRET", None)
    if expected:
        if request.headers.get(BOT_HEADER) != expected:
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    tg = request.data.get('telegram_id')
    if not tg:
        return Response({"detail": "telegram_id required"}, status=400)

    event = get_object_or_404(Event, id=event_id)
    user = get_object_or_404(User, telegram_id=int(tg))

    removed = queue_utils.leave_queue_redis(event.id, user.id)
    QueueEntry.objects.filter(event=event, user=user, status='waiting').update(status='cancelled')

    return Response({"removed": removed})


@api_view(['GET'])
@permission_classes([AllowAny])
def position(request, event_id):
    tg = request.query_params.get('telegram_id')
    if not tg:
        return Response({"detail": "telegram_id required as query param"}, status=400)

    event = get_object_or_404(Event, id=event_id)
    user = get_object_or_404(User, telegram_id=int(tg))

    pos = queue_utils.get_position_redis(event.id, user.id)
    if pos is None:
        return Response({"position": None, "status": "not_in_queue"})
    return Response({"position": pos, "status": "waiting"})


@api_view(['POST'])
@permission_classes([AllowAny])
def call_next(request, event_id):
    expected = getattr(settings, "BOT_SECRET", None)
    if expected:
        if request.headers.get(BOT_HEADER) != expected:
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    event = get_object_or_404(Event, id=event_id)
    user_id = queue_utils.pop_next_redis(event.id)
    if user_id is None:
        return Response({"detail": "queue_empty"}, status=200)

    # обновляем в БД запись
    try:
        entry = QueueEntry.objects.filter(event=event, user_id=user_id, status='waiting').earliest('created_at')
        entry.status = 'called'
        entry.called_at = timezone.now()
        entry.save()
    except QueueEntry.DoesNotExist:
        # создаём запись called (если вдруг не было)
        entry = QueueEntry.objects.create(event=event, user_id=user_id, status='called', called_at=timezone.now())

    user = entry.user
    return Response({
        "called_user": {"telegram_id": user.telegram_id, "username": user.username, "full_name": user.full_name},
        "entry_id": entry.id
    })
