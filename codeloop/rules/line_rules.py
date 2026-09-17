"""Line rules: allowlist check, laterality modifiers for paired structures, units sanity."""

from __future__ import annotations

PAIRED_BODY_PARTS: tuple[str, ...] = (
    "hand",
    "wrist",
    "elbow",
    "shoulder",
    "humerus",
    "forearm",
    "finger",
    "thumb",
    "foot",
    "ankle",
    "knee",
    "tibia",
    "fibula",
    "femur",
    "hip",
    "toe",
    "clavicle",
    "scapula",
    "heel",
    "calcaneus",
    "leg",
    "arm",
)


def laterality_modifiers(body_part: str | None, laterality: str) -> list[str]:
    """RT/LT for a documented side on a paired structure; bilateral studies carry no side modifier here
    (a bilateral-specific code is preferred when one exists)."""
    if not body_part or laterality not in ("right", "left"):
        return []
    bp = body_part.lower()
    if any(p in bp for p in PAIRED_BODY_PARTS):
        return ["RT" if laterality == "right" else "LT"]
    return []
