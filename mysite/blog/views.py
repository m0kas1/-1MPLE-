from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .stats_eta import estimate_service_time, eta_for_position
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Event, User, QueueEntry
from . import queue_utils
from django.conf import settings
import logging
from django.utils import timezone
import redis
from .serializers import QueueEntryLiteSerializer

@api_view(['GET'])
@permission_classes([AllowAny])
def events_list(request):
    qs = Event.objects.all()
    data = [{"id": e.id, "name":e.name, "description":e.description, "avg_service_minutes": e.avg_service_minutes} for e in qs]
    return Response(data)

@api_view(['GET'])
@permission_classes([AllowAny])
def user_entries(request, tg_id):
    """
    GET /api/users/<tg_id>/entries/
    Возвращает текущие (waiting/called) заявки пользователя, отсортированные по created_at.
    """
    user = get_object_or_404(User, telegram_id=int(tg_id))
    qs = QueueEntry.objects.filter(user=user).exclude(status__in=['cancelled','served','skipped']).order_by('created_at')
    serializer = QueueEntryLiteSerializer(qs, many=True)
    return Response(serializer.data)

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

logger = logging.getLogger(__name__)
MAX_SAMPLE = 50

@api_view(['GET'])
@permission_classes([AllowAny])
def position(request, event_id):
    tg = request.query_params.get("telegram_id")
    if not tg:
        return Response({"detail":"telegram_id required as query param"}, status=400)

    event = get_object_or_404(Event, id=event_id)
    user = get_object_or_404(User, telegram_id=int(tg))

    # 1) position
    try:
        pos = queue_utils.get_position_redis(event.id, user.id)
    except Exception as e:
        logger.exception("Redis error getting position")
        pos = None

    if pos is None:
        try:
            entry = QueueEntry.objects.filter(event=event, user=user, status='waiting').earliest('created_at')
            pos = QueueEntry.objects.filter(event=event, status='waiting', created_at__lte=entry.created_at).count()
        except QueueEntry.DoesNotExist:
            return Response({"position": None, "status": "not_in_queue"})

    try:
        pos_int = int(pos)
    except Exception:
        logger.warning("Position casting failed, pos=%r", pos)
        pos_int = 0

    # 2) collect durations (minutes)
    durations = []
    try:
        qs = QueueEntry.objects.filter(event=event, status='served').order_by('-served_at')[:MAX_SAMPLE]
        for e in qs:
            if getattr(e, "called_at", None) and getattr(e, "served_at", None):
                delta = (e.served_at - e.called_at).total_seconds() / 60.0
                if delta > 0:
                    durations.append(round(delta, 2))
    except Exception:
        logger.exception("Error collecting durations, proceeding with empty list")
        durations = []

    prior_M = float(getattr(event, "avg_service_minutes", 10.0) or 10.0)

    estimate = estimate_service_time(sample=durations, prior_M=prior_M, prior_n=3.0, min_samples_for_confidence=5)

    # GUARANTEE numeric per_person
    per_person = estimate.get("mean_est")
    if per_person is None:
        per_person = prior_M

    # Robust ETA calculation
    try:
        eta_mean = float(per_person) * max(1, pos_int)  # если pos==0 — умножаем на 1
    except Exception:
        logger.exception("ETA mean calc failed; fallback to prior")
        eta_mean = prior_M * max(1, pos_int)

    ci = estimate.get("ci") or (None, None)
    if ci[0] is None or ci[1] is None:
        # give conservative interval +/-30%
        ci_low = max(0.0, eta_mean * 0.7)
        ci_high = eta_mean * 1.3
    else:
        ci_low = float(ci[0]) * max(1, pos_int)
        ci_high = float(ci[1]) * max(1, pos_int)

    response = {
        "position": pos_int,
        "status": "waiting",
        "eta_mean_minutes": round(eta_mean, 1),
        "eta_minutes": round(eta_mean, 1),  # <-- добавлено для обратной совместимости
        "eta_ci_minutes": [round(ci_low, 1), round(ci_high, 1)],
        "per_person_minutes": round(per_person, 2),
        "per_person_ci_minutes": [round(estimate["ci"][0], 2) if estimate.get("ci") else None,
                                  round(estimate["ci"][1], 2) if estimate.get("ci") else None],
        "n_samples": estimate.get("n", 0),
        "note": ("Использовано {} последних измерений.".format(estimate.get("n")) if estimate.get("n") > 0
                 else "Нет измерений — используется prior."),
    }
    logger.info("position response: tg=%s event=%s -> %s", tg, event_id, response)
    return Response(response)

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

@api_view(['POST'])
@permission_classes([AllowAny])
def cancel_entry(request, entry_id):
    """
    POST /api/entries/<entry_id>/cancel/
    Отменяет заявку: удаляет из Redis и помечает в БД cancelled.
    """
    entry = get_object_or_404(QueueEntry, id=entry_id)
    if entry.status != 'waiting':
        return Response({"detail": "cannot_cancel", "status": entry.status}, status=400)

    event_id = entry.event_id
    user_id = entry.user_id

    # Попытка удалить из Redis; если Redis недоступен — всё равно помечаем cancelled в DB (fallback)
    try:
        removed = queue_utils.leave_queue_redis(event_id, user_id)
    except Exception as e:
        removed = False

    # Обновляем запись в БД
    entry.status = 'cancelled'
    entry.save(update_fields=['status'])

    return Response({"cancelled": True, "removed_from_redis": removed})