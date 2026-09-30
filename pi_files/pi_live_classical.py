"""
Live vein overlay on Raspberry Pi 5 + standard (IR-cut) Pi camera.
No trained model -- see vein_classical.py for why. Best with an OPEN,
RELAXED hand, even soft light, camera and hand both still.

Setup:
    sudo apt install -y python3-picamera2 python3-opencv
    pip install scikit-image scipy   # if not already present
Files needed alongside this one: vein_postprocess.py, vein_classical.py
Run:
    python3 pi_live_classical.py
Keys: q quit | s save frame | r reset the frame-averager (after moving the hand)
"""
import time
import cv2
import numpy as np
from picamera2 import Picamera2
from vein_classical import process, FrameAverager
from vein_postprocess import draw, TargetSmoother

cam = Picamera2()
cam.configure(cam.create_video_configuration(main={"size": (960, 720), "format": "RGB888"}))
cam.set_controls({"AeEnable": True, "AwbEnable": True})   # auto is fine once the scene is fixed
cam.start()
time.sleep(0.5)

avg, sm = FrameAverager(n=6), TargetSmoother(alpha=0.25, jump_px=30)

while True:
    frame = cam.capture_array()                            # RGB888
    bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    a, t, roi = process(bgr, avg)

    if a is None:
        vis = bgr.copy()
        cv2.putText(vis, "No hand detected", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    else:
        vis = draw(bgr, a, None)
        p = sm.update(t)
        if p:
            cv2.drawMarker(vis, p, (0, 0, 255), cv2.MARKER_CROSS, 24, 2)
            cv2.putText(vis, f"TARGET: {p}", (p[0] + 12, p[1] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
            print(f"target=({p[0]},{p[1]})")               # coordinates on stdout for another process to read
        else:
            cv2.putText(vis, "No reliable vein yet", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 140, 255), 2)

    cv2.imshow("vein (visible-light, classical)", vis)
    k = cv2.waitKey(1) & 0xFF
    if k == ord("q"):
        break
    elif k == ord("s"):
        cv2.imwrite(f"capture_{int(time.time())}.png", vis)
    elif k == ord("r"):
        avg.buf.clear()

cam.stop()
cv2.destroyAllWindows()
