from typing import List, Dict, Tuple, Optional
from core.config import config, LineConfig
from utils.geometry import intersect, get_centroid
import math

# ── Occlusion recovery constants ──────────────────────────────────────────────
GHOST_MAX_DIST    = 120   # px – max centroid distance to match a ghost track
GHOST_TIMEOUT     = 60    # frames – how long to keep a ghost before discarding


class VehicleCounter:
    def __init__(self):
        # Store previous centroid for each track_id
        self.track_history: Dict[int, Tuple[int, int]] = {}

        # Count statistics: {line_name: {class_name: count}}
        self.counts: Dict[str, Dict[str, int]] = {
            line.name: {v: 0 for v in ["car", "bus", "truck", "motorbike"]}
            for line in config.counting_lines
        }

        # IDs that have already crossed each line (avoids double-count)
        self.crossed_ids: Dict[str, set] = {
            line.name: set() for line in config.counting_lines
        }

        # ── Ghost-track memory for occlusion recovery ──────────────────────
        # Structure: { old_id: {
        #     "centroid":      (cx, cy),
        #     "class_name":    str,
        #     "ttl":           int,          # frames remaining
        #     "crossed_lines": set[str]      # line names already crossed
        # }}
        self._ghost_tracks: Dict[int, dict] = {}

        self._frame_count = 0

    # ── public API ─────────────────────────────────────────────────────────────
    def update(self, tracks: List[Dict]) -> None:
        self._frame_count += 1
        current_ids = {t['track_id'] for t in tracks}

        # ── 1. Detect IDs that just disappeared → promote to ghost ──
        lost_ids = set(self.track_history.keys()) - current_ids
        for lid in lost_ids:
            # Only ghost tracks that have history and are not already ghost
            if lid not in self._ghost_tracks:
                crossed = {
                    ln for ln, ids in self.crossed_ids.items()
                    if lid in ids
                }
                self._ghost_tracks[lid] = {
                    "centroid":      self.track_history[lid],
                    "class_name":    None,   # filled below if we had cls info
                    "ttl":           GHOST_TIMEOUT,
                    "crossed_lines": crossed,
                }

        # ── 2. Tick down ghost TTL; discard expired ones ──
        expired = [gid for gid, g in self._ghost_tracks.items() if g["ttl"] <= 0]
        for gid in expired:
            del self._ghost_tracks[gid]
            self.track_history.pop(gid, None)
        for g in self._ghost_tracks.values():
            g["ttl"] -= 1

        # ── 3. Process current tracks ──
        for track in tracks:
            track_id  = track['track_id']
            cls_name  = track['class_name']
            centroid  = get_centroid(track['bbox'])

            # Store class_name in ghost if we see this ID for the first time
            # (or if a ghost existed we need to record its class)

            # ── 3a. Check if this is a re-appeared track matching a ghost ──
            if track_id not in self.track_history:
                ghost_id = self._find_ghost_match(centroid, cls_name)
                if ghost_id is not None:
                    ghost = self._ghost_tracks.pop(ghost_id)
                    # Inherit history and crossed-line state from the ghost
                    self.track_history[track_id] = ghost["centroid"]
                    for ln, ids in self.crossed_ids.items():
                        if ln in ghost["crossed_lines"]:
                            ids.add(track_id)

            # ── 3b. Line-crossing detection ──
            if track_id in self.track_history:
                prev_centroid = self.track_history[track_id]
                for line in config.counting_lines:
                    if track_id not in self.crossed_ids[line.name]:
                        if intersect(prev_centroid, centroid, line.pt1, line.pt2):
                            self.crossed_ids[line.name].add(track_id)
                            if cls_name not in self.counts[line.name]:
                                self.counts[line.name][cls_name] = 0
                            self.counts[line.name][cls_name] += 1

            # ── 3c. Update history ──
            self.track_history[track_id] = centroid

            # Annotate ghost class (so we can use it if it disappears later)
            if track_id in self._ghost_tracks:
                self._ghost_tracks[track_id]["class_name"] = cls_name

    def has_crossed(self, track_id: int) -> bool:
        """Returns True if the vehicle has already crossed any counting line."""
        for line_name, crossed_set in self.crossed_ids.items():
            if track_id in crossed_set:
                return True
        return False

    # ── helpers ────────────────────────────────────────────────────────────────
    def _find_ghost_match(self, centroid: Tuple[int, int],
                           cls_name: str) -> Optional[int]:
        """
        Search ghost tracks for the closest one within GHOST_MAX_DIST.
        Prefer same class if possible.
        Returns ghost_id or None.
        """
        best_id   = None
        best_dist = GHOST_MAX_DIST + 1

        for gid, ghost in self._ghost_tracks.items():
            dist = math.hypot(centroid[0] - ghost["centroid"][0],
                              centroid[1] - ghost["centroid"][1])
            if dist < best_dist:
                # Prefer matching class; if no class info recorded, accept anyway
                if ghost["class_name"] is None or ghost["class_name"] == cls_name:
                    best_dist = dist
                    best_id   = gid

        return best_id if best_dist <= GHOST_MAX_DIST else None

    # ── standard API ───────────────────────────────────────────────────────────
    def get_counts(self) -> Dict[str, Dict[str, int]]:
        return self.counts

    def reset(self):
        self.track_history.clear()
        self._ghost_tracks.clear()
        self._frame_count = 0
        for line in self.counts:
            for cls in self.counts[line]:
                self.counts[line][cls] = 0
            self.crossed_ids[line].clear()
