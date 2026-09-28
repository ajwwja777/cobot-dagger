from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)

"""Optional segmented-teach capture overlay for Task5."""

from .state import (
    CaptureNode,
    CaptureSnapshot,
    CaptureState,
    InvalidCaptureEvent,
    SegmentedCaptureReducer,
    SyncedSnapshot,
    TeachMask,
)

__all__ = [
    "CaptureNode",
    "CaptureSnapshot",
    "CaptureState",
    "InvalidCaptureEvent",
    "SegmentedCaptureReducer",
    "SyncedSnapshot",
    "TeachMask",
]
