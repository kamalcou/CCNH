# CCNH
```module load Anaconda3
module load Apptainer
export APPTAINER_CACHEDIR=/scratch/$USER/.apptainer_cache   # avoid blowing up $HOME quota; this image is large
apptainer pull ngiab-2i2c_v1.2.3.sif docker://quay.io/awiciroh/ngiab-2i2c:v1.2.3
```

```
module load squashfuse 
module load gocryptfs
module load squashfs-tools

```

hostname
