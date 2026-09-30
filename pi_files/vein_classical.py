"""
Classical (no deep learning) vein extraction for VISIBLE-LIGHT cameras.

Why this file exists: with a standard (IR-cut) Pi camera, veins are faint
grey/green ridges, not the dark NIR lines the earlier U-Net was trained on.
A vesselness (ridge) filter, restricted to skin and tuned per-frame, tracks
that faint signal far better than a network trained on a different domain.

Needs: opencv-python, numpy, scipy, scikit-image  (same as vein_postprocess.py)
"""
import cv2
import numpy as np
from skimage.filters import sato
from vein_postprocess import analyse, pick_target, draw, TargetSmoother   # reused as-is

WORK_W = 480          # vesselness runs at this width for speed, result is upscaled back


def skin_mask(bgr):
    """Rough hand silhouette in YCrCb, eroded inward so the bright rim of the
    hand (which always looks like a strong 'edge') is excluded from the ROI."""
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    m = cv2.inRange(ycrcb, (0, 133, 77), (255, 180, 135))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        m = (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8) * 255
    m = cv2.erode(m, np.ones((25, 25), np.uint8))
    return m > 0


def enhance(bgr):
    """Green channel has the best vein/skin contrast in visible light on most
    skin tones (haemoglobin absorbs green more than red); CLAHE + bilateral
    lift local contrast while keeping vein edges (unlike a plain blur)."""
    g = cv2.split(bgr)[1]
    g = cv2.createCLAHE(2.0, (8, 8)).apply(g)
    return cv2.bilateralFilter(g, 9, 50, 50)


def vesselness(gray_full, roi_full):
    """Multi-scale ridge filter, computed small then upscaled (this is the
    slow step on a Pi CPU)."""
    h, w = gray_full.shape
    scale = WORK_W / w
    small = cv2.resize(gray_full, (WORK_W, int(h * scale)))
    v = sato(small.astype(np.float32) / 255, sigmas=np.arange(1.2, 4, 0.7), black_ridges=True)
    v = cv2.resize(v, (w, h))
    v = cv2.GaussianBlur(v, (0, 0), 0.8)
    v[~roi_full] = 0
    m = v.max()
    return v / m if m > 1e-6 else v


class FrameAverager:
    """Averages the last N grayscale frames to cut sensor noise. Only helps
    when the camera AND the hand are both still -- exactly your setup."""
    def __init__(self, n=6):
        self.n, self.buf = n, []

    def push(self, gray):
        self.buf.append(gray.astype(np.float32))
        self.buf = self.buf[-self.n:]
        return np.mean(self.buf, axis=0).astype(np.uint8)


def process(bgr, avg: FrameAverager, min_width_px=2.5):
    roi = skin_mask(bgr)
    if roi.sum() < 0.02 * roi.size:                      # no hand in frame
        return None, None, roi
    stable_gray = avg.push(enhance(bgr))
    prob = vesselness(stable_gray, roi)
    thr = max(float(np.percentile(prob[roi], 98.5)), 0.12)
    a = analyse(prob, thr=thr, min_area=60, spur_len=15, junction_pad=8)
    t = pick_target(a, min_len=30, min_width=min_width_px, safe_junction_px=12, end_margin=8)
    return a, t, roi
