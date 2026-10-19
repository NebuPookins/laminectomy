#!/usr/bin/env bash
# Run the built executable against an empty Unity project to check that it
# starts, prints help, and writes a viewer folder with its bundled page.
set -euo pipefail

exe="$(ls dist/laminectomy-* | head -n 1)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "Testing $exe"
"$exe" --help > /dev/null

mkdir -p "$work/project/Assets" "$work/project/ProjectSettings"
"$exe" build "$work/project" -o "$work/out"

test -f "$work/out/rigs.json"
test -f "$work/out/index.html"
grep -q "spine-player" "$work/out/index.html"
echo "Smoke test passed"
