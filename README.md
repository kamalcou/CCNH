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
apptainer exec --bind /scratch ngiab-2i2c_v1.2.3.sif   jupyter lab --no-browser --ip=$(hostname -s) --port=8888
```
Use the command in the compute node where we want to run the Jupyter notebook
```
hostname
```
If it is amdcompute005 then it will be: 
```
ssh -L 8888:amdcompute005:8888 username@<login_node>
```

After tunneling use the computer browser to access the compute node and run the jupyter notebook.

```
http://127.0.0.1:8888/lab/
```


