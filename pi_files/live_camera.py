"""
Run the trained vein model on a LIVE camera (run on your own laptop / Jetson / Pi, NOT in Kaggle).

Setup (once):
    pip install torch opencv-python numpy scipy scikit-image segmentation-models-pytorch
Files needed in the same folder:
    vein_postprocess.py      (from the earlier download)
    best_unet.pt             (download from Kaggle: notebook Output panel -> /kaggle/working/best_unet.pt)
Run:
    python live_camera.py            # camera 0
    python live_camera.py 1          # camera 1
Keys:  q = quit,  s = save current frame,  [ / ] = lower / raise the threshold
"""
import sys, time
import cv2, numpy as np, torch
import segmentation_models_pytorch as smp
from vein_postprocess import analyse, pick_target, draw, TargetSmoother

SIZE = 512
device = "cuda" if torch.cuda.is_available() else "cpu"

net = smp.Unet("resnet34", encoder_weights=None, in_channels=3, classes=1).to(device)
net.load_state_dict(torch.load("best_unet.pt", map_location=device))
net.eval()

clahe = cv2.createCLAHE(3.0, (8, 8))
MEAN = np.array([0.485, 0.456, 0.406], np.float32)      # same normalisation as training (albumentations default)
STD = np.array([0.229, 0.224, 0.225], np.float32)


@torch.no_grad()
def predict_prob(bgr):
    h, w = bgr.shape[:2]
    g = clahe.apply(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    x = cv2.cvtColor(cv2.resize(g, (SIZE, SIZE)), cv2.COLOR_GRAY2RGB).astype(np.float32) / 255
    x = torch.from_numpy(((x - MEAN) / STD).transpose(2, 0, 1))[None].to(device)
    p = torch.sigmoid(net(x))[0, 0].cpu().numpy()        # no flip-TTA here: keeps live latency low
    return cv2.resize(p, (w, h))


cam = int(sys.argv[1]) if len(sys.argv) > 1 else 0
cap = cv2.VideoCapture(cam)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
sm, thr, t0 = TargetSmoother(alpha=0.3, jump_px=25), 0.5, time.time()

while True:
    ok, frame = cap.read()
    if not ok:
        break
    prob = predict_prob(frame)
    a = analyse(prob, thr=thr, min_area=80, spur_len=10, junction_pad=6)
    t = pick_target(a, min_len=25, min_width=4.0, safe_junction_px=15, end_margin=8)
    vis = draw(frame, a, None)
    p = sm.update(t)
    if p:
        cv2.drawMarker(vis, p, (0, 0, 255), cv2.MARKER_CROSS, 24, 2)
        cv2.putText(vis, f"TARGET: {p}", (p[0] + 12, p[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
    fps = 1 / max(time.time() - t0, 1e-6); t0 = time.time()
    cv2.putText(vis, f"{fps:.1f} FPS  thr={thr:.2f}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.imshow("vein", vis)
    k = cv2.waitKey(1) & 0xFF
    if k == ord("q"):
        break
    elif k == ord("s"):
        cv2.imwrite(f"capture_{int(time.time())}.png", vis)
    elif k == ord("["):
        thr = max(0.1, thr - 0.05)
    elif k == ord("]"):
        thr = min(0.9, thr + 0.05)

cap.release()
cv2.destroyAllWindows()
