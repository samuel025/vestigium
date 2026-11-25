#!/usr/bin/env bash
# One-command rerun. Needs GEMINI_API_KEY (and optionally GEMINI_API_KEY2, 3, ...) in .env.
# Resumable: finished runs are skipped, so rerun after a quota reset to fill the gaps.
set -euo pipefail
cd "$(dirname "$0")"
uv sync
uv run pytest -q                                   # engine matches the answer key on all 80 cases
uv run python -m vestigium.build_store             # vestigium.rl + answer_key.json
VESTIGIUM_RPM="${VESTIGIUM_RPM:-15}" uv run python -m vestigium.bench --arms D C A B --split heldout --repeats "${REPEATS:-1}"
uv run python -m vestigium.export_demo             # refresh demo/data.js
echo "Open demo/index.html for the overview and demo/app.html for the app (or: uv run python -m vestigium.serve)"
