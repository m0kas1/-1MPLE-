import os
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

def queue_key(event_id: int) -> str:
    return f"queue:{event_id}"

def join_queue_redis(event_id: int, user_id: int) -> int:
    key = queue_key(event_id)
    # проверяем, есть ли уже
    pos = redis_client.lpos(key, str(user_id))
    if pos is not None:
        return pos + 1
    redis_client.rpush(key, str(user_id))
    return redis_client.llen(key)

def leave_queue_redis(event_id: int, user_id: int) -> bool:
    key = queue_key(event_id)
    removed = redis_client.lrem(key, 0, str(user_id))
    return removed > 0

def get_position_redis(event_id: int, user_id: int):
    key = queue_key(event_id)
    pos = redis_client.lpos(key, str(user_id))
    if pos is None:
        return None
    return pos + 1

def pop_next_redis(event_id: int):
    key = queue_key(event_id)
    uid = redis_client.lpop(key)
    if uid is None:
        return None
    return int(uid)

def list_queue_redis(event_id: int):
    key = queue_key(event_id)
    all_ids = redis_client.lrange(key, 0, -1)
    return [int(x) for x in all_ids]
