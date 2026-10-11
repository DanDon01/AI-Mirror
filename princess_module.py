"""Compatibility imports for the former Princess-only avatar module.

New code should import :mod:`avatar_module`. This shim can be removed after
deployed Pi configurations and external scripts have migrated to AVATAR names.
"""

from avatar_module import (  # noqa: F401
    AvatarModule,
    _effective_intent,
    _intent_for,
    _load_system_prompt,
    _response_intent_and_text,
    _response_text,
    _spoken_reply,
)

PrincessModule = AvatarModule
