# CCNH

Batch NextGen-in-a-Box (NGIAB) hydrofabric download and model runs for a set of
USGS gages, using the `ngiab-2i2c` container image. Supports two environments:

- **HPC (Apptainer + Slurm)** — the primary workflow, run as a Slurm job array.
- **Mac / Apple Silicon (Docker)** — for local development and testing.

Both environments run the same scripts (`notebooks/data_download.py`,
`notebooks/run_model.py`) inside the same container image, so results are
reproducible across the two.

## Gages

The default gage set, used by both `data_download.py` and `run_model.py`
unless overridden:

```
gage-02464000
gage-02361000
gage-02469800
gage-03574500
```

## HPC workflow (Apptainer + Slurm)

### 1. Pull the container image

```bash
module load Anaconda3
module load Apptainer
export APPTAINER_CACHEDIR=/scratch/$USER/.apptainer_cache   # avoid blowing up $HOME quota; this image is large
apptainer pull ngiab-2i2c_v1.2.3.sif docker://quay.io/awiciroh/ngiab-2i2c:v1.2.3
```

### 2. Download and subset the data

```bash
apptainer exec --cleanenv --bind /scratch ngiab-2i2c_v1.2.3.sif \
    /ngen/.venv/bin/python notebooks/data_download.py
```

By default this writes to `$HOME/ngiab_preprocess_output`. To redirect to
scratch instead:

```bash
NGIAB_HOME=/scratch/$USER apptainer exec --cleanenv --bind /scratch ngiab-2i2c_v1.2.3.sif \
    /ngen/.venv/bin/python notebooks/data_download.py
```

### 3. Run the model

Submit the Slurm job array (one task per gage):

```bash
mkdir -p logs
sbatch submit_ngaib_run.sh
```

[submit_ngaib_run.sh](submit_ngaib_run.sh) expects the repo (and the pulled
`.sif`) at `$HOME/notebooks_for_git/CCNH` — update `SIF`/`WORKDIR` at the top
of the script if your clone lives elsewhere. It runs
[notebooks/run_model.py](notebooks/run_model.py) once per gage with
`--cleanenv` and the PROJ/GDAL env vars the container needs, and logs
per-task timing to `logs/run_<jobid>_<taskid>.out`.

### 4. Use Jupyter on a compute node (optional)

To work interactively instead of via Slurm, request a compute node and load
the extra filesystem modules the container image needs:

```bash
module load squashfuse
module load gocryptfs
module load squashfs-tools
apptainer exec --bind /scratch ngiab-2i2c_v1.2.3.sif \
    jupyter lab --no-browser --ip=$(hostname -s) --port=8888
```

Find the compute node's hostname:

```bash
hostname
```

From your local machine, tunnel to it (replace `amdcompute005` with your
node's hostname):

```bash
ssh -L 8888:amdcompute005:8888 username@<login_node>
```

Then open in a browser:

```
http://127.0.0.1:8888/lab/
```

## Mac workflow (Docker)

[notebooks/run_docker_mac.sh](notebooks/run_docker_mac.sh) is the Mac
(Apple Silicon) equivalent of the HPC steps above, using Docker instead of
Apptainer/Slurm against the same container image.

The image is amd64-only, so it runs under emulation — in Docker Desktop,
enable **Settings > General > "Use Rosetta for x86/amd64 emulation"** first
for noticeably better performance than the default QEMU emulation.

One-time image pull:

```bash
docker pull --platform linux/amd64 quay.io/awiciroh/ngiab-2i2c:v1.2.3
```

Download data (all gages):

```bash
./notebooks/run_docker_mac.sh download
```

Run the model (all gages, sequential):

```bash
./notebooks/run_docker_mac.sh run
```

Run the model for a single gage:

```bash
./notebooks/run_docker_mac.sh run gage-02464000
```

Output is written under `ngiab_preprocess_output/` in the repo root, and
per-run timing is printed to the console.

## Notebooks

[notebooks/](notebooks/) also contains interactive counterparts to the batch
scripts above, plus post-processing analysis:

| Notebook | Purpose |
| --- | --- |
| [NextGen_Data_Preparation.ipynb](notebooks/NextGen_Data_Preparation.ipynb) | Interactive hydrofabric/forcing download and subsetting (notebook form of `data_download.py`) |
| [NextGen_Run.ipynb](notebooks/NextGen_Run.ipynb) | Interactive model run (notebook form of `run_model.py`) |
| [NextGen_Calibration.ipynb](notebooks/NextGen_Calibration.ipynb) | Model calibration |
| [NextGen_Outputs_Analysis.ipynb](notebooks/NextGen_Outputs_Analysis.ipynb) | Post-run output analysis and plotting |
| [NextGEN_TEEHR_Evaluation.ipynb](notebooks/NextGEN_TEEHR_Evaluation.ipynb) | Model evaluation against observations via TEEHR |

Supporting modules (`cal_utils.py`, `forcings_utils.py`,
`hydrofabric_visualization_utils.py`, `ngen_outputs_utils.py`,
`ngiab_utils.py`) are imported by both the scripts and the notebooks above.

## Environment variables

- `NGIAB_HOME` — base directory for outputs (`$NGIAB_HOME/ngiab_preprocess_output`).
  Defaults to the user's home directory; set it to point at `/scratch` on HPC
  or is set automatically to the repo root by `run_docker_mac.sh`.

## Notes

- On HPC, `submit_ngaib_run.sh` deliberately does **not** `module load
  Apptainer` (it puts the Apptainer binary on `PATH` directly) — loading the
  module pulls in a GCCcore toolchain swap that leaks host `PROJ_LIB`/`GDAL_DATA`
  into the container and breaks projection lookups.
- Model runs are sequential by design (one gage at a time): each run already
  uses all available cores via MPI, so parallelizing across gages would
  oversubscribe the node. Data downloads are network-bound and safe to
  parallelize (see `MAX_WORKERS` in `data_download.py`).
