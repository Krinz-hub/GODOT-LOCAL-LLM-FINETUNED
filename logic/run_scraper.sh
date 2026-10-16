#!/usr/bin/env bash
# ==============================================================================
# Godot Logic Pipeline Manual Launcher
# ==============================================================================
# Safe manual execution script for Godot Logic Data Collection & Cleaning Pipeline.
# NEVER auto-starts scraping on load. Requires explicit subcommands.
# ==============================================================================

set -euo pipefail

# 1. Resolve project root reliably
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# 2. Virtual Environment Detection & Activation
PYTHON_EXEC=""
if [[ -f "${SCRIPT_DIR}/.venv/bin/python" ]]; then
    PYTHON_EXEC="${SCRIPT_DIR}/.venv/bin/python"
elif [[ -f "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON_EXEC="${REPO_ROOT}/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_EXEC="$(command -v python3)"
else
    echo "ERROR: Python 3 not found."
    echo "Please create a virtual environment first:"
    echo "  python3 -m venv logic/.venv"
    echo "  logic/.venv/bin/python -m pip install -r logic/requirements.txt"
    exit 1
fi

# 3. Ensure PYTHONPATH includes logic/src
export PYTHONPATH="${REPO_ROOT}:${SCRIPT_DIR}/src:${PYTHONPATH:-}"

# 4. Check configuration file
CONFIG_FILE="${SCRIPT_DIR}/config/pipeline.yaml"
if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "ERROR: Configuration file not found at ${CONFIG_FILE}"
    exit 1
fi

# 5. Check arguments
if [[ $# -eq 0 ]]; then
    echo "=================================================================="
    echo "Godot Logic Pipeline Launcher"
    echo "=================================================================="
    echo "Usage: ./logic/run_scraper.sh <subcommand> [options]"
    echo ""
    echo "Commands:"
    echo "  check-config                    Audit configuration, schemas, and structured datasets"
    echo "  ingest --sample-size 50         Ingest existing structured datasets (read-only)"
    echo "  ingest --dry-run                Preview ingestion yield without writing files"
    echo "  collect --dry-run               Preview collection plan without downloading"
    echo "  collect --source local          Collect from local Godot projects"
    echo "  collect --source github         Collect from GitHub Godot repositories"
    echo "  collect --source docs           Collect official Godot documentation"
    echo "  normalize                       Normalize line endings and text encoding"
    echo "  clean                           Scrub sensitive data and quarantine bloat"
    echo "  deduplicate                     Remove exact and near duplicates"
    echo "  validate                        Validate schemas and cross-references"
    echo "  report                          Generate dataset statistics and quality reports"
    echo "  export                          Export distinct Datasets A, B, and C to ShareGPT"
    echo "  run --stage all --sample-size 50 Run all pipeline stages sequentially"
    echo "=================================================================="
    exit 0
fi

# 6. Inform user before executing
echo "--> Executing: ${PYTHON_EXEC} -m logic.logic_pipeline.cli $*"
echo ""

# 7. Execute command
exec "${PYTHON_EXEC}" -m logic.logic_pipeline.cli "$@"
