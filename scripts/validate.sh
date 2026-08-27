#!/usr/bin/env bash

set -euo pipefail

blender="blender"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --blender|-b)
            blender="${2:?Missing value for $1}"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--blender PATH]"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [[ "$blender" == */* ]]; then
    blender="$(cd "$(dirname "$blender")" && pwd)/$(basename "$blender")"
else
    blender="$(command -v "$blender" || true)"
fi

if [[ -z "$blender" || ! -x "$blender" ]]; then
    echo "Could not find Blender. Pass --blender /path/to/blender or put blender on PATH." >&2
    exit 1
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
blender_root="$(cd "$(dirname "$blender")/.." && pwd)"
python="$(find "$blender_root" -type f \( -name python -o -name 'python3*' \) -path '*/python/bin/*' -print -quit 2>/dev/null || true)"
if [[ -z "$python" ]]; then
    python="$("$blender" --background --factory-startup --python-expr 'import sys; print("DIMENSIONS_PYTHON=" + sys.executable)' 2>&1 | sed -n 's/^DIMENSIONS_PYTHON=//p' | tail -n 1)"
fi
if [[ -z "$python" || ! -x "$python" ]]; then
    echo "Could not locate Blender's Python interpreter from $blender" >&2
    exit 1
fi

cd "$root"
"$python" -m compileall -q dimensions tests
"$python" tests/stroke_font_smoke.py
"$blender" --background --factory-startup --python tests/blender_smoke.py
"$blender" --background --factory-startup --python tests/blender_modal.py
"$blender" --background --factory-startup --python tests/blender_lifecycle.py
"$blender" --background --factory-startup --python tests/output_geometry_smoke.py
"$blender" --background --factory-startup --python tests/output_smoke.py
"$blender" --background --factory-startup --python tests/output_operator_smoke.py
"$blender" --background --factory-startup --command extension validate dimensions
"$root/scripts/build_extension.sh" --blender "$blender"

archive="$(find "$root/build" -maxdepth 1 -type f -name 'dimensions-*.zip' -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)"
if [[ -z "$archive" ]]; then
    echo "Extension archive was not created" >&2
    exit 1
fi

if ! command -v unzip >/dev/null; then
    echo "Could not inspect extension archive: unzip is required on POSIX systems" >&2
    exit 1
fi
if ! unzip -Z1 "$archive" | grep -Fxq LICENSE; then
    echo "Extension archive does not contain LICENSE" >&2
    exit 1
fi
"$blender" --background --factory-startup --command extension validate "$archive"
