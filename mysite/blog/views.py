from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Event, User, QueueEntry
from . import queue_utils
from django.conf import settings
from django.utils import timezone
import redis

@api_view(['GET'])
@permission_classes([AllowAny])
def events_list(request):
    qs = Event.objects.all()
    data = [{"id": e.id, "name":e.name, "description":e.description, "avg_service_minutes": e.avg_service_minutes} for e in qs]
    return Response(data)

@api_view(['POST'])
@permission_classes([AllowAny])
def join_queue(request, event_id):
    # body: {"telegram_id": 123, "username":"...", "full_name":"..."}
    event = get_object_or_404(Event, id=event_id)
    tg = request.data.get("telegram_id")
    if not tg:
        return Response({"detail":"telegram_id required"}, status=400)

    user, _ = User.objects.get_or_create(telegram_id=int(tg), defaults={
        "username": request.data.get("username"),
        "full_name": request.data.get("full_name"),
    })

    # 1) push to redis
    try:
        pos = queue_utils.join_queue_redis(event_id=event.id, user_id=user.id)
    except redis.exceptions.ConnectionError:
        # fallback: create DB entry and compute pos by DB
        with transaction.atomic():
            entry, created = QueueEntry.objects.get_or_create(event=event, user=user, status='waiting')
            pos = QueueEntry.objects.filter(event=event, status='waiting', created_at__lte=entry.created_at).count()
        return Response({"position": pos, "entry_id": entry.id, "warning":"redis_unavailable_db_mode"}, status=201)
    except Exception as e:
        return Response({"detail": f"Redis error: {e}"}, status=500)

    # 2) create DB entry (or reuse waiting)
    try:
        with transaction.atomic():
            entry, created = QueueEntry.objects.get_or_create(event=event, user=user, status='waiting')
    except Exception as e:
        # rollback redis to avoid dangling
        try:
            queue_utils.leave_queue_redis(event.id, user.id)
        except Exception:
            pass
        return Response({"detail": f"DB error: {e}"}, status=500)

    # calculate ETA
    eta_minutes = queue_utils.estimate_wait_minutes(event.avg_service_minutes, pos)
    return Response({"position": pos, "eta_minutes": eta_minutes, "entry_id": entry.id}, status=201)

@api_view(['POST'])
@permission_classes([AllowAny])
def leave_queue(request, event_id):
    tg = request.data.get("telegram_id")
    if not tg:
        return Response({"detail":"telegram_id required"}, status=400)
    event = get_object_or_404(Event, id=event_id)
    user = get_object_or_404(User, telegram_id=int(tg))
    removed = queue_utils.leave_queue_redis(event.id, user.id)
    QueueEntry.objects.filter(event=event, user=user, status='waiting').update(status='cancelled')
    return Response({"removed": removed})

@api_view(['GET'])
@permission_classes([AllowAny])
def position(request, event_id):
    tg = request.query_params.get("telegram_id")
    if not tg:
        return Response({"detail":"telegram_id required as query param"}, status=400)
    event = get_object_or_404(Event, id=event_id)
    user = get_object_or_404(User, telegram_id=int(tg))
    pos = queue_utils.get_position_redis(event.id, user.id)
    if pos is None:
        return Response({"position": None, "status":"not_in_queue"})
    eta = queue_utils.estimate_wait_minutes(event.avg_service_minutes, pos)
    return Response({"position": pos, "eta_minutes": eta, "status":"waiting"})

@api_view(['POST'])
@permission_classes([AllowAny])  # в проде — ограничь доступ
def call_next(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    user_id = queue_utils.pop_next_redis(event.id)
    if user_id is None:
        return Response({"detail":"queue_empty"})
    # mark DB
    try:
        entry = QueueEntry.objects.filter(event=event, user_id=user_id, status='waiting').earliest('created_at')
        entry.status = 'called'
        entry.called_at = timezone.now()
        entry.save()
    except QueueEntry.DoesNotExist:
        entry = QueueEntry.objects.create(event=event, user_id=user_id, status='called', called_at=timezone.now())
    user = entry.user
    return Response({"called_user":{"telegram_id": user.telegram_id, "username": user.username}, "entry_id": entry.id})
