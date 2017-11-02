from django.contrib.sessions.backends.cached_db import SessionStore as CachedDBStore
from django.contrib.sessions.base_session import AbstractBaseSession
from django.db import models

# I did this cos I want to save user Id along with session object
# from django.contrib.sessions.backends.cached_db
class SessionStore(CachedDBStore):
    cache_key_prefix = 'core.overrides.cached_db'

    def __init__(self, session_key=None):
        super(SessionStore, self).__init__(session_key)

    @classmethod
    def get_model_class(cls):
        from core.models import AuthSession
        return AuthSession

    def create_model_instance(self, data):
        obj = super(SessionStore, self).create_model_instance(data)
        try:
            user = int(data.get('_auth_user_id'))
        except (ValueError, TypeError):
            user = None

        obj.user_id = user
        return obj

