#!/bin/bash
#SBATCH --job-name=ngiab_run
#SBATCH --output=logs/run_%A_%a.out
#SBATCH --error=logs/run_%A_%a.err
#SBATCH --partition=icelake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64           # cores granted to the task; run_model caps
                                     # ranks to min(this, catchment count)
#SBATCH --mem=16G
#SBATCH --time=06:00:00
#SBATCH --array=0-3                  # 4 gages (indices 0-3). Append %N to cap
                                     # concurrent tasks, e.g. 0-3%2 = 2 at a time.

set -euo pipefail

# logs/ must exist BEFORE the job writes to it. mkdir here is a safety net, but
# create it once before submitting (`mkdir -p logs`) so the very first task's
# --output path is valid.
mkdir -p logs

# ── Hydrofabric IDs (index must line up with --array range above) ──────────────
HYDROFABRIC_IDS=(
    "gage-02464000"
    "gage-02361000"
    "gage-02469800"
    "gage-03574500"
)
HYDROFABRIC_ID=${HYDROFABRIC_IDS[$SLURM_ARRAY_TASK_ID]}
echo "Task $SLURM_ARRAY_TASK_ID -> $HYDROFABRIC_ID on $(hostname)"

# ── Apptainer on PATH ──────────────────────────────────────────────────────────
# Do NOT `module load Apptainer`: it pulls in squashfs-tools/GCCcore-12.3.0, which
# forces a GCCcore toolchain swap and leaks host PROJ_LIB/GDAL_DATA into the run
# (the "Open of .../share/proj failed" error). We only need the binary on PATH.
export PATH=/apps/zen5/software/Apptainer/1.4.5/bin:$PATH

# ── Paths ────────────────────────────────────────────────────────────────────
SIF="$HOME/CCNH/ngiab-2i2c_v1.2.3.sif"   # adjust if elsewhere
WORKDIR="$HOME/CCNH"                     # holds notebooks/
cd "$WORKDIR"

# Per-task matplotlib cache in a writable dir (avoids the /scratch RO warning).
export MPLCONFIGDIR="/tmp/mpl-$USER-$SLURM_ARRAY_TASK_ID"

# ── Run one gage inside the container ──────────────────────────────────────────
# --cleanenv strips SLURM_* at the container boundary so Hydra uses fork, not srun.
# sched_getaffinity inside the container sees this task's --cpus-per-task cores.
START_TS=$(date +%s)
echo "Task $SLURM_ARRAY_TASK_ID ($HYDROFABRIC_ID) started at $(date '+%Y-%m-%d %H:%M:%S')"

# Temporarily disable -e so a failed run still reaches the timing/summary block
# below (we capture and re-raise the real exit code ourselves).
set +e
apptainer exec --cleanenv --bind /scratch \
    --env MPLCONFIGDIR="$MPLCONFIGDIR" \
    --env PROJ_LIB=/srv/conda/envs/notebook/share/proj \
    --env PROJ_DATA=/srv/conda/envs/notebook/share/proj \
    --env GDAL_DATA=/srv/conda/envs/notebook/share/gdal \
    "$SIF" \
    /ngen/.venv/bin/python notebooks/run_model.py \
        --hydrofabric-id "$HYDROFABRIC_ID" \
        --start-date "2020-01-01" \
        --end-date   "2022-12-31" \
        --run
RC=$?
set -e

# ── Elapsed time ───────────────────────────────────────────────────────────────
END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
printf 'Task %s (%s) finished with exit %d in %02dh:%02dm:%02ds (%d seconds)\n' \
    "$SLURM_ARRAY_TASK_ID" "$HYDROFABRIC_ID" "$RC" \
    $((ELAPSED/3600)) $(((ELAPSED%3600)/60)) $((ELAPSED%60)) "$ELAPSED"

exit $RC
