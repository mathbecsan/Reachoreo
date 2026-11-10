"""Find which OpenCV camera index is which: grabs one frame from each and saves it.

    python tools/list_cameras.py            # writes camera_<i>.jpg for every index that opens

Then put the right index under perception.camera in config/show.yaml.
On macOS the first run triggers the camera permission prompt for the app running this shell.
"""
import sys
import time

import cv2

out = sys.argv[1] if len(sys.argv) > 1 else "."
for i in range(5):
    cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY)
    if not cap.isOpened():
        print(f"camera {i}: not available")
        continue
    frame = None
    for _ in range(30):                     # first frames can be black while the sensor wakes
        ok, f = cap.read()
        if ok:
            frame = f
        time.sleep(0.03)
    if frame is None:
        print(f"camera {i}: opened but gave no frames")
    else:
        path = f"{out}/camera_{i}.jpg"
        cv2.imwrite(path, frame)
        print(f"camera {i}: {frame.shape[1]}x{frame.shape[0]} -> {path}")
    cap.release()
