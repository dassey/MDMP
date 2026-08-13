#!/bin/sh
# Start the MDMP harness. Requires only Python 3.9+.
cd "$(dirname "$0")" || exit 1
for py in python3 python; do
  if command -v $py >/dev/null 2>&1; then exec $py serve.py "$@"; fi
done
echo "Python 3.9 or newer is required and was not found on PATH." >&2
exit 1
