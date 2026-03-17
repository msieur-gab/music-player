"""Soniq -- audio feature analysis, classification, and playlist generation."""

from .profiles import CONTEXT_PROFILES
from .db import _connect
from .scoring import classify_track
from .classifiers import predict_all
from .playlists import (
    get_zones, generate_playlist,
    save_playlist, list_playlists, get_playlist, delete_playlist,
)
from .similarity import (
    find_similar, find_by_harmony, get_mood_clusters, find_transitions,
)
from .scanner import analyze_library, migrate_from_json
