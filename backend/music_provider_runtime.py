from config import config
from music import build_provider_registry
from music import provider_configuration_status as provider_configuration_status


CATALOG_PROVIDERS = ("netease", "qq", "audius")
music_provider_registry = build_provider_registry(config)
