"""Compatibility imports for :mod:`avatar_services`."""

from avatar_services import (  # noqa: F401
    AVATAR_MODULE,
    FAL_AVATAR_SERVICE,
    OPENAI_TTS_SERVICE,
    TEXT_AVATAR_PRICE_PER_SECOND_USD,
    AvatarConfigurationError,
    AvatarServiceError,
    FalResult,
    FlashTalkService,
    OpenAITTSService,
    TTSResult,
    atomic_write_json,
    dataclass_dict,
    inspect_media,
    is_pi_playback_compatible,
    normalize_video,
    sha256_file,
    utc_now,
)

PrincessConfigurationError = AvatarConfigurationError
PrincessServiceError = AvatarServiceError
PRINCESS_MODULE = AVATAR_MODULE
