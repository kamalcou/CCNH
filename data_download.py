#!/usr/bin/env python
"""
Batch download + subset NGIAB data (hydrofabric + AORC forcings) for one or more
gages, then plot a basin-mean time series per gage.

Run with the CONTAINER's venv python:

    apptainer exec --cleanenv --bind /scratch ngiab-2i2c_v1.2.3.sif \
        /ngen/.venv/bin/python notebooks/data_download.py

Redirect output to scratch with the NGIAB_HOME env var:

    NGIAB_HOME=/scratch/mhchowdhury  apptainer exec ... /ngen/.venv/bin/python notebooks/data_download.py
"""

# ----------------------------- Imports -----------------------------
import os
import sys
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import matplotlib
matplotlib.use("Agg")  # headless: write PNGs, no GUI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from hydrofabric_visualization_utils import conus_hydrofabric_download
from forcings_utils import process_time_series, get_var_label, get_var_full_name

# ----------------------------- Config -----------------------------
HYDROFABRIC_IDS = [
    "gage-02464000",
    "gage-02361000",
    "gage-02469800",
    "gage-03574500",
]

start_date = "2020-01-01"   # forcing window start, YYYY-MM-DD
end_date   = "2022-12-31"   # forcing window end,   YYYY-MM-DD
var_name   = "precip_rate"  # forcing variable to plot

# Parallelism. 1 = sequential (most robust). 2-4 supervises that many CLI
# subprocesses concurrently; higher risks AORC/NWM network throttling and disk
# contention, with little gain since each download is network-bound.
MAX_WORKERS = 1

NGIAB_HOME = Path(os.environ.get("NGIAB_HOME", Path.home()))
OUTPUT_ROOT = NGIAB_HOME / "ngiab_preprocess_output"
VENV_PY = "/ngen/.venv/bin/python"


def run_cli(*args, tag=""):
    """Invoke ngiab_data_cli via the container venv."""
    cmd = [VENV_PY, "-m", "ngiab_data_cli", *args]
    print(f"[{tag}] >>> {' '.join(cmd)}", flush=True)
    # capture output so parallel logs don't interleave into noise; surface on error
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"[{tag}] ngiab_data_cli failed (exit {r.returncode})\n"
            f"--- stdout ---\n{r.stdout[-2000:]}\n"
            f"--- stderr ---\n{r.stderr[-2000:]}"
        )
    return r


def download_gage(hydrofabric_id):
    """Subset hydrofabric + forcings for one gage. Returns (id, data_dir, gpkg, forcing)."""
    data_dir = (OUTPUT_ROOT / hydrofabric_id).resolve()

    # 1. subset hydrofabric
    run_cli("-i", hydrofabric_id, "-s", tag=hydrofabric_id)
    gpkg_path = data_dir / "config" / f"{hydrofabric_id}_subset.gpkg"
    if not gpkg_path.exists():
        raise FileNotFoundError(f"[{hydrofabric_id}] geopackage missing: {gpkg_path}")

    # 2. subset forcings
    run_cli("-i", hydrofabric_id, "-f", "--start", start_date, "--end", end_date,
            tag=hydrofabric_id)

    # 3. generate realization + cat_config + troute.yaml
    #    NOTE: the -r step uses --start_date/--end_date, NOT --start/--end
    #    like the forcings step. Different flag names, same values.
    run_cli("-i", hydrofabric_id, "-r",
            "--start_date", start_date, "--end_date", end_date,
            tag=hydrofabric_id)
    realization = data_dir / "config" / "realization.json"
    if not realization.exists():
        raise FileNotFoundError(
            f"[{hydrofabric_id}] realization.json not created: {realization}"
        )

    # 4. validate forcings.nc resolves to a real file (catches dangling symlinks
    #    that otherwise surface later as ngen's cryptic NcException)
    forcings_path = data_dir / "forcings" / "forcings.nc"
    real = Path(os.path.realpath(forcings_path))
    if not real.exists():
        raise FileNotFoundError(
            f"[{hydrofabric_id}] forcings.nc does not resolve to a real file:\n"
            f"  link {forcings_path} -> {real}"
        )
    print(f"[{hydrofabric_id}] forcings OK -> {real} ({real.stat().st_size:,} bytes)",
          flush=True)
    return hydrofabric_id, data_dir, gpkg_path, forcings_path


def plot_gage(hydrofabric_id, data_dir, gpkg_path, forcings_path):
    """Basin-mean time series PNG for one gage."""
    series = process_time_series(str(forcings_path), str(gpkg_path), var_name)
    start, end = series.index.min(), series.index.max()
    months_span = (end.year - start.year) * 12 + (end.month - start.month) + 1
    interval = max(1, months_span // 24)

    fig = plt.figure(figsize=(12, 6))
    plt.plot(series.index, series.values, linewidth=1, label=get_var_full_name(var_name))
    plt.xlabel("Date/Time", labelpad=10)
    plt.ylabel(get_var_label(var_name) or "Value", labelpad=10)
    plt.title(f"{hydrofabric_id} - Hourly {get_var_full_name(var_name)}", pad=14)
    ax = plt.gca()
    ax.set_xlim(start, end)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.xticks(rotation=45)
    plt.grid(True, linestyle="--", linewidth=0.7)
    plt.tight_layout()

    out = NGIAB_HOME / f"hourly_{var_name}_{hydrofabric_id}.png"
    plt.savefig(out, dpi=200)
    plt.close(fig)
    print(f"[{hydrofabric_id}] saved plot -> {out}", flush=True)


# ----------------------------- Run -----------------------------
def main():
    # CONUS hydrofabric: shared cache in ~/.ngiab, download ONCE before the loop.
    # (Doing this inside parallel workers would race on the same files.)
    print("Ensuring CONUS hydrofabric is present (first run ~2-3 min)...", flush=True)
    conus_hydrofabric_download()

    results, failures = [], []

    if MAX_WORKERS <= 1:
        for gid in HYDROFABRIC_IDS:
            try:
                results.append(download_gage(gid))
            except Exception as e:
                failures.append((gid, e))
                print(f"[{gid}] FAILED: {e}", file=sys.stderr, flush=True)
    else:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = {ex.submit(download_gage, gid): gid for gid in HYDROFABRIC_IDS}
            for fut in as_completed(futs):
                gid = futs[fut]
                try:
                    results.append(fut.result())
                except Exception as e:
                    failures.append((gid, e))
                    print(f"[{gid}] FAILED: {e}", file=sys.stderr, flush=True)

    # Plot sequentially (matplotlib's pyplot state machine is not thread-safe).
    for gid, data_dir, gpkg, forcing in results:
        try:
            plot_gage(gid, data_dir, gpkg, forcing)
        except Exception as e:
            print(f"[{gid}] plot FAILED: {e}", file=sys.stderr, flush=True)

    print(f"\nDone. {len(results)} succeeded, {len(failures)} failed.")
    for gid, e in failures:
        print(f"  FAILED {gid}: {str(e).splitlines()[0]}")


if __name__ == "__main__":
    main()