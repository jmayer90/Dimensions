#!/usr/bin/env bash

set -euo pipefail

blender="blender"
output_directory=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --blender|-b)
            blender="${2:?Missing value for $1}"
            shift 2
            ;;
        --output-directory|-o)
            output_directory="${2:?Missing value for $1}"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--blender PATH] [--output-directory PATH]"
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
if [[ -z "$output_directory" ]]; then
    output_directory="$root/builds"
fi
stage="$root/builds/extension-stage"

rm -rf "$stage"
mkdir -p "$stage" "$output_directory"
cp -R "$root/dimensions/." "$stage/"
cp "$root/LICENSE" "$stage/LICENSE"
cp "$root/README.md" "$stage/README.md"

"$blender" --background --factory-startup --command extension build --source-dir "$stage" --output-dir "$output_directory"

version="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)"[[:space:]]*$/\1/p' "$stage/blender_manifest.toml")"
if [[ -z "$version" ]]; then
    echo "Could not read the extension version from blender_manifest.toml" >&2
    exit 1
fi

archive="$output_directory/dimensions-$version.zip"
if [[ ! -f "$archive" ]]; then
    echo "Expected extension archive was not created: $archive" >&2
    exit 1
fi

"$blender" --background --factory-startup --command extension validate "$archive"

if ! command -v unzip >/dev/null; then
    echo "Could not inspect extension archive: unzip is required on POSIX systems" >&2
    exit 1
fi
archive_entries="$(unzip -Z1 "$archive")"
for required_entry in __init__.py blender_manifest.toml LICENSE README.md; do
    if ! grep -Fxq "$required_entry" <<<"$archive_entries"; then
        echo "Extension archive does not contain required release file: $required_entry" >&2
        exit 1
    fi
done

if grep -Eq '(^|/)__pycache__/|\.py[co]$' <<<"$archive_entries"; then
    echo "Extension archive contains generated Python cache files" >&2
    exit 1
fi

echo "Submission-ready extension archive: $archive"
