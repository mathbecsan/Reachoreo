#!/bin/sh
# Downloads what the dashboard's camera mode needs, so it also works offline at the venue:
# MediaPipe Tasks Vision (browser build) and the pose landmarker model.
set -e
cd "$(dirname "$0")/.."
V=reachy_dance/dashboard/static/vendor/mediapipe
TMP=$(mktemp -d)
curl -sSL -o "$TMP/tv.tgz" https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-1.1.1.tgz
tar xzf "$TMP/tv.tgz" -C "$TMP"
mkdir -p "$V/wasm" models
cp "$TMP/package/vision_bundle.mjs" "$V/"
cp "$TMP"/package/wasm/vision_wasm_internal.* "$TMP"/package/wasm/vision_wasm_nosimd_internal.* "$V/wasm/"
[ -f models/pose_landmarker_full.task ] || curl -sSL -o models/pose_landmarker_full.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task
rm -rf "$TMP"
echo "camera assets ready"
