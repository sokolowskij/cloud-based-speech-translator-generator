from django.core.cache import cache
from datetime import datetime


def get_user_limit(user, limit_name):
    return getattr(user.role, f"{limit_name}_limit", 0)


def _get_cache_key(user_id, action_type):
    date_str = datetime.now().strftime('%Y-%m-%d')
    return f"{user_id}:{action_type}:{date_str}"


def initialize_limit_if_needed(user, action_type):
    cache_key = _get_cache_key(user.id, action_type)
    if cache.get(cache_key) is None:
        cache.set(cache_key, 0, timeout=86400)


def check_and_increment_limit(user, action_type):
    
    max_limit = get_user_limit(user, action_type)
    cache_key = _get_cache_key(user.id, action_type)
    current_count = cache.get(cache_key, 0)

    if current_count >= max_limit:
        return False

    cache.set(cache_key, current_count + 1, timeout=86400)
    return True


def is_within_file_limit(user, limit_name, value):
    limit = get_user_limit(user, limit_name)
    return value <= limit
