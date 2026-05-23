"""Provider registry for Robot Mower Yard."""

from __future__ import annotations

from .entity import EntityProvider
from .husqvarna import HusqvarnaProvider
from .mock import MockProvider
from .navimow import NavimowProvider

PROVIDERS = {
    "entity": EntityProvider,
    "husqvarna": HusqvarnaProvider,
    "mock": MockProvider,
    "navimow": NavimowProvider,
}
