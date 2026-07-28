#!/bin/bash
# Mac (Apple Silicon) equivalent of submit_ngaib_run.sh, using Docker instead of
# SLURM + Apptainer. Runs data_download.py / run_model.py inside the same
# ngiab-2i2c image the HPC side pulls with Apptainer.
#
# The image is amd64-only (no native arm64 build) - `--platform linux/amd64`
# below runs it under emulation. In Docker Desktop, enable
# Settings > General > "Use Rosetta for x86/amd64 emulation" first; it's
# noticeably faster than the default QEMU emulation.
#
# One-time image pull:
#   docker pull --platform linux/amd64 quay.io/awiciroh/ngiab-2i2c:v1.2.3
#
# Usage:
#   ./run_docker_mac.sh download              # subset hydrofabric + forcings, all gages
#   ./run_docker_mac.sh run                    # run the model, all gages (sequential)
#   ./run_docker_mac.sh run gage-02464000      # run the model for one gage

set -euo pipefail

IMAGE="quay.io/awiciroh/ngiab-2i2c:v1.2.3"

# Repo root (parent of this script's notebooks/ dir). Bind-mounted at /workspace
# so NGIAB_HOME can be pinned to a path that exists on both sides -- Docker,
# unlike Apptainer, does not auto-bind $HOME, so run_model.py/data_download.py
# (which default NGIAB_HOME to Path.home()) need it set explicitly.
WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$WORKDIR/ngiab_preprocess_output" "$WORKDIR/logs"

MODE="${1:-run}"
GAGE="${2:-}"

case "$MODE" in
    download)
        SCRIPT="notebooks/data_download.py"
        ARGS=()
        ;;
    run)
        SCRIPT="notebooks/run_model.py"
        ARGS=(--start-date "2020-01-01" --end-date "2022-12-31" --run)
        [[ -n "$GAGE" ]] && ARGS+=(--hydrofabric-id "$GAGE")
        ;;
    *)
        echo "Usage: $0 {download|run} [gage-id]" >&2
        exit 1
        ;;
esac

START_TS=$(date +%s)
echo "[$MODE${GAGE:+ $GAGE}] started at $(date '+%Y-%m-%d %H:%M:%S')"

set +e
docker run --rm \
    --platform linux/amd64 \
    -v "$WORKDIR:/workspace" \
    -w /workspace \
    -e NGIAB_HOME=/workspace \
    -e HOME=/tmp \
    -e MPLCONFIGDIR=/tmp/mpl-cache \
    -e PROJ_LIB=/srv/conda/envs/notebook/share/proj \
    -e PROJ_DATA=/srv/conda/envs/notebook/share/proj \
    -e GDAL_DATA=/srv/conda/envs/notebook/share/gdal \
    -e HYDRA_LAUNCHER=fork \
    -e HYDRA_BOOTSTRAP=fork \
    "$IMAGE" \
    /ngen/.venv/bin/python "$SCRIPT" "${ARGS[@]}"
RC=$?
set -e

END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
printf '[%s%s] finished with exit %d in %02dh:%02dm:%02ds (%d seconds)\n' \
    "$MODE" "${GAGE:+ $GAGE}" "$RC" \
    $((ELAPSED/3600)) $(((ELAPSED%3600)/60)) $((ELAPSED%60)) "$ELAPSED"

exit $RC
