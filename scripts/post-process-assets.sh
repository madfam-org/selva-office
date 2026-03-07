#!/usr/bin/env bash
#
# post-process-assets.sh
#
# Optional post-processing for generated pixel-art PNGs:
# - 2x/4x upscaling with nearest-neighbor (no interpolation)
# - WebP conversion with PNG fallback
#
# Requires ImageMagick (magick or convert). Gracefully skips if not installed.
#
# Usage:
#   bash scripts/post-process-assets.sh [--scale 2|4] [--webp] [--input dir] [--output dir]

set -euo pipefail

SCALE=2
WEBP=false
INPUT_DIR="apps/office-ui/public/assets"
OUTPUT_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scale) SCALE="$2"; shift 2 ;;
    --webp) WEBP=true; shift ;;
    --input) INPUT_DIR="$2"; shift 2 ;;
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="${INPUT_DIR}/processed"
fi

# Check for ImageMagick
MAGICK_CMD=""
if command -v magick &>/dev/null; then
  MAGICK_CMD="magick"
elif command -v convert &>/dev/null; then
  MAGICK_CMD="convert"
else
  echo "ImageMagick not found (magick or convert). Skipping post-processing."
  echo "Install with: brew install imagemagick (macOS) or apt install imagemagick (Linux)"
  exit 0
fi

echo "Post-processing assets from ${INPUT_DIR} -> ${OUTPUT_DIR}"
echo "Scale: ${SCALE}x | WebP: ${WEBP} | Using: ${MAGICK_CMD}"

mkdir -p "$OUTPUT_DIR"

count=0
find "$INPUT_DIR" -name '*.png' -not -path '*/processed/*' | while read -r png; do
  rel="${png#$INPUT_DIR/}"
  outdir="$OUTPUT_DIR/$(dirname "$rel")"
  mkdir -p "$outdir"
  basename="$(basename "$rel" .png)"

  # Nearest-neighbor upscale
  ${MAGICK_CMD} "$png" -filter point -resize "${SCALE}00%" "$outdir/${basename}@${SCALE}x.png"

  # WebP conversion
  if [[ "$WEBP" == "true" ]]; then
    ${MAGICK_CMD} "$png" -define webp:lossless=true "$outdir/${basename}.webp" 2>/dev/null || true
    ${MAGICK_CMD} "$outdir/${basename}@${SCALE}x.png" -define webp:lossless=true "$outdir/${basename}@${SCALE}x.webp" 2>/dev/null || true
  fi

  count=$((count + 1))
done

echo "Post-processed ${count} assets."
