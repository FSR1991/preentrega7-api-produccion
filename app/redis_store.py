from redis import Redis
from redis.exceptions import RedisError

from app.config import get_redis_url


def create_redis_client() -> Redis:
    """Crea un cliente Redis a partir de la configuración del proyecto."""
    return Redis.from_url(
        get_redis_url(),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=10,
        health_check_interval=30,
    )


def check_redis_connection(client: Redis) -> bool:
    """Comprueba la conectividad con Redis."""
    try:
        return bool(client.ping())
    except RedisError:
        return False