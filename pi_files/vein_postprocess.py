"""
Vein post-processing: probability map -> clean mask -> skeleton -> junctions
-> best straight/thick segment -> needle target point (+ direction).
Pure numpy / scipy / scikit-image / OpenCV (no deep-learning dependency).
"""
import cv2
import numpy as np
from dataclasses import dataclass
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

K8 = np.ones((3, 3), int)
K8[1, 1] = 0


@dataclass
class Target:
    x: int
    y: int
    width_px: float          # local vein diameter (2 x distance transform)
    direction: np.ndarray    # unit vector along the vein (dx, dy)
    dist_to_junction_px: float
    score: float


def clean_mask(prob, thr=0.5, min_area=80):
    m = (prob > thr).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area          # drop tiny blobs (noise)
    m = keep[lab].astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return m.astype(bool)


def _neighbours(skel):
    return ndi.convolve(skel.astype(int), K8, mode="constant") * skel


def prune_spurs(skel, spur_len=10, passes=2):
    """Remove short side-branches (skeleton 'hairs') that hang off a junction."""
    skel = skel.copy()
    for _ in range(passes):
        nb = _neighbours(skel)
        junc = skel & (nb >= 3)
        zone = cv2.dilate(junc.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        branches = skel & ~zone
        lab, n = ndi.label(branches, structure=np.ones((3, 3)))
        endpoints = skel & (nb == 1)
        zone_touch = cv2.dilate(zone.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        for i in range(1, n + 1):
            comp = lab == i
            if comp.sum() < spur_len and (comp & endpoints).any() and (comp & zone_touch).any():
                skel[comp] = False
        skel = skeletonize(skel)
    return skel


def analyse(prob, thr=0.5, min_area=80, spur_len=10, junction_pad=6):
    mask = clean_mask(prob, thr, min_area)
    dt = ndi.distance_transform_edt(mask)                 # radius at every vein pixel
    skel = prune_spurs(skeletonize(mask), spur_len)
    nb = _neighbours(skel)
    junctions = skel & (nb >= 3)                          # bifurcations / confluences
    endpoints = skel & (nb == 1)
    k = 2 * junction_pad + 1
    jzone = cv2.dilate(junctions.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool)
    segments, nseg = ndi.label(skel & ~jzone, structure=np.ones((3, 3)))
    dist_to_j = (ndi.distance_transform_edt(~junctions) if junctions.any()
                 else np.full(mask.shape, 1e6))
    return dict(mask=mask, dt=dt, skel=skel, junctions=junctions, endpoints=endpoints,
                segments=segments, nseg=nseg, dist_to_j=dist_to_j)


def _direction(pts, cy, cx, r=12):
    d = np.hypot(pts[:, 0] - cy, pts[:, 1] - cx)
    p = pts[d <= r].astype(float)
    if len(p) < 3:
        return np.array([1.0, 0.0])
    p -= p.mean(0)
    _, _, vt = np.linalg.svd(p, full_matrices=False)
    v = vt[0]                                             # (dy, dx)
    return np.array([v[1], v[0]])                         # -> (dx, dy)


def pick_target(a, min_len=25, min_width=4.0, safe_junction_px=15, end_margin=8):
    """Choose the best needle target on the best segment.
    score = width * straightness * length factor; pixel = widest point that is
    far from junctions and from the ends of the segment."""
    best = None
    for i in range(1, a["nseg"] + 1):
        ys, xs = np.nonzero(a["segments"] == i)
        L = len(ys)
        if L < min_len:
            continue
        pts = np.stack([ys, xs], 1)
        w = 2 * a["dt"][ys, xs]
        # straightness: 1.0 = straight line, lower = curvy
        s = np.linalg.svd(pts - pts.mean(0), compute_uv=False)
        straight = 1.0 if s[1] < 1e-6 else float(1 - min(s[1] / s[0], 1.0))
        # keep pixels away from junctions and from segment ends
        far_j = a["dist_to_j"][ys, xs] >= safe_junction_px
        ends = a["endpoints"][ys, xs]
        if ends.any():
            ey, ex = ys[ends], xs[ends]
            far_e = np.min(np.hypot(ys[:, None] - ey[None], xs[:, None] - ex[None]), 1) >= end_margin
        else:
            far_e = np.ones(L, bool)
        # smooth width along the segment to ignore single-pixel noise
        w_s = ndi.uniform_filter1d(w[np.argsort(ys * 10000 + xs)], 5)[np.argsort(np.argsort(ys * 10000 + xs))]
        ok = far_j & far_e & (w_s >= min_width)
        if not ok.any():
            continue
        idx = np.flatnonzero(ok)[np.argmax(w_s[ok])]
        seg_score = float(w_s[idx] * straight * min(L / 60.0, 1.0))
        if best is None or seg_score > best.score:
            best = Target(int(xs[idx]), int(ys[idx]), float(w_s[idx]),
                          _direction(pts, ys[idx], xs[idx]),
                          float(a["dist_to_j"][ys[idx], xs[idx]]), seg_score)
    return best


def draw(img_bgr, a, target, show_junctions=True):
    out = img_bgr.copy()
    out[a["skel"]] = (0, 255, 0)                          # green skeleton
    if show_junctions:
        for y, x in zip(*np.nonzero(a["junctions"])):
            cv2.circle(out, (int(x), int(y)), 3, (0, 165, 255), -1)   # orange = branch point
    if target is not None:
        c = (target.x, target.y)
        cv2.drawMarker(out, c, (0, 0, 255), cv2.MARKER_CROSS, 24, 2)  # red pointer
        tip = (int(c[0] + 30 * target.direction[0]), int(c[1] + 30 * target.direction[1]))
        cv2.arrowedLine(out, c, tip, (255, 0, 0), 1, tipLength=0.3)   # vein axis
        cv2.putText(out, f"TARGET: ({target.x}, {target.y})  w={target.width_px:.1f}px",
                    (c[0] + 12, c[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
    return out


class TargetSmoother:
    """Video use: exponential smoothing + only report when stable."""
    def __init__(self, alpha=0.3, jump_px=25):
        self.alpha, self.jump, self.p = alpha, jump_px, None

    def update(self, t):
        if t is None:
            return None if self.p is None else tuple(map(int, self.p))
        q = np.array([t.x, t.y], float)
        if self.p is None or np.linalg.norm(q - self.p) > self.jump:
            self.p = q                                    # re-lock on a new vein
        else:
            self.p = (1 - self.alpha) * self.p + self.alpha * q
        return tuple(map(int, self.p))
