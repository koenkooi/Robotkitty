#!/usr/bin/env bash
#
# Rebuild everything in assets/ from the two drawings.
#
# Sigrids design.jpg  -> correct.py -> rectify.py  -> extract.py    -> webres.py
# Hadewychs ontwerp.jpg ->            rectify2.py  -> extract_hw.py -> webres_hw.py
#
# Hadewych's card is shot against black and is evenly lit, so it needs no
# flat-field pass; Sigrid's was hand-held under a lamp and does.
#
# Ends in exactly one line:
#   BUILD-ASSETS: SUCCESS (...)
#   BUILD-ASSETS: FAILURE (<stage>) -- <reason>
#
# Usage:
#   tools/build-assets.sh              # build into a temp dir, install into assets/
#   tools/build-assets.sh --check      # build and diff against assets/, install nothing
#   tools/build-assets.sh --only hadewych   # just one drawing (sigrid | hadewych)
#   tools/build-assets.sh --work DIR   # keep the intermediates in DIR
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIGRID="$REPO/Sigrids design.jpg"
HADEWYCH="$REPO/Hadewychs ontwerp.jpg"
CHECK=0
ONLY=""
WORK=""

fail() { echo "BUILD-ASSETS: FAILURE ($1) -- $2"; exit 1; }
trap 'fail "unexpected" "aborted at line $LINENO; see the output above"' ERR

while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1; shift ;;
    --only) ONLY="${2:-}"; shift 2 ;;
    --work) WORK="${2:-}"; shift 2 ;;
    *) fail "arguments" "unknown option '$1'" ;;
  esac
done
case "$ONLY" in ""|sigrid|hadewych) ;; *) fail "arguments" "--only takes sigrid or hadewych" ;; esac

python3 -c "import numpy, PIL" 2>/dev/null || fail "deps" "needs python3 with numpy and Pillow"

if [ -z "$WORK" ]; then
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
fi
mkdir -p "$WORK/s" "$WORK/h" || fail "workdir" "cannot create $WORK"

# A stage that exits 0 but leaves an empty or missing file is still a failure.
require() { [ -s "$2" ] || fail "$1" "produced no usable $2"; }

SIGRID_FILES="bg_field.jpg band_gold.jpg band_rail.jpg band_curtain.jpg band_ground.jpg
              kitty_body.png arm_left.png arm_right.png leg_left.png leg_right.png
              nugget1.png nugget2.png nugget3.png dome_left.png dome_right.png drawing.jpg"
HADEWYCH_FILES="hw_bg_full.jpg hw_band_soil.jpg hw_band_bar.jpg
                hw_cat_body.png hw_arm_left.png hw_arm_right.png hw_leg_left.png
                hw_leg_right.png hw_tail1.png hw_tail2.png hw_tail3.png hw_tail4.png
                hw_head_left.png hw_head_right.png
                hw_flower1.png hw_flower2.png hw_flower3.png hw_drawing.jpg"

WANT=""

if [ "$ONLY" != "hadewych" ]; then
  [ -f "$SIGRID" ] || fail "input" "missing $SIGRID"
  echo "== Sigrid =="
  python3 "$REPO/tools/correct.py" "$SIGRID" "$WORK/s/flat.jpg" || fail "correct" "correct.py exited non-zero"
  require correct "$WORK/s/flat.jpg"
  python3 "$REPO/tools/rectify.py" "$WORK/s/flat.jpg" "$WORK/s/screen.png" || fail "rectify" "rectify.py exited non-zero"
  require rectify "$WORK/s/screen.png"
  ( cd "$WORK/s" && python3 "$REPO/tools/extract.py" ) || fail "extract" "extract.py exited non-zero"
  ( cd "$WORK/s" && python3 "$REPO/tools/webres.py" ) || fail "webres" "webres.py exited non-zero"
  for f in $SIGRID_FILES; do require webres "$WORK/s/web/$f"; done
  WANT="$WANT $SIGRID_FILES"
  OUTDIR_S="$WORK/s/web"
fi

if [ "$ONLY" != "sigrid" ]; then
  [ -f "$HADEWYCH" ] || fail "input" "missing $HADEWYCH"
  echo "== Hadewych =="
  python3 "$REPO/tools/rectify2.py" "$HADEWYCH" "$WORK/h/card.png" || fail "rectify2" "rectify2.py exited non-zero"
  require rectify2 "$WORK/h/card.png"
  ( cd "$WORK/h" && python3 "$REPO/tools/extract_hw.py" ) || fail "extract_hw" "extract_hw.py exited non-zero"
  ( cd "$WORK/h" && python3 "$REPO/tools/webres_hw.py" ) || fail "webres_hw" "webres_hw.py exited non-zero"
  for f in $HADEWYCH_FILES; do require webres_hw "$WORK/h/web/$f"; done
  WANT="$WANT $HADEWYCH_FILES"
  OUTDIR_H="$WORK/h/web"
fi

find_built() {
  for d in "${OUTDIR_S:-}" "${OUTDIR_H:-}"; do
    [ -n "$d" ] && [ -f "$d/$1" ] && { echo "$d/$1"; return 0; }
  done
  return 1
}

if [ "$CHECK" = 1 ]; then
  DIFFS=0
  TOTAL=0
  for f in $WANT; do
    TOTAL=$((TOTAL + 1))
    src="$(find_built "$f")" || fail "check" "$f was not built"
    cmp -s "$src" "$REPO/assets/$f" || { echo "   differs: $f"; DIFFS=$((DIFFS + 1)); }
  done
  [ "$DIFFS" -eq 0 ] || fail "check" "$DIFFS of $TOTAL files differ from assets/"
  echo "BUILD-ASSETS: SUCCESS (check: all $TOTAL files match assets/)"
  exit 0
fi

N=0
for f in $WANT; do
  src="$(find_built "$f")" || fail "install" "$f was not built"
  cp "$src" "$REPO/assets/$f" || fail "install" "could not copy $f into assets/"
  N=$((N + 1))
done
echo "BUILD-ASSETS: SUCCESS ($N files rebuilt into assets/)"
