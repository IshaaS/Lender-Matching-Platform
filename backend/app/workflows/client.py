from functools import lru_cache

from hatchet_sdk import Hatchet

from app.config import get_settings


@lru_cache
def get_hatchet() -> Hatchet:
    """The Hatchet client reads HATCHET_CLIENT_TOKEN itself and refuses to start without one,
    so nothing in app.workflows may be imported unless `settings.use_hatchet` is true."""
    if not get_settings().hatchet_client_token:
        raise RuntimeError("HATCHET_CLIENT_TOKEN is not set; use the in-process runner instead.")
    return Hatchet()
