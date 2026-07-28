import os
import sys
import geopandas as gpd
import folium
from folium import GeoJson, GeoJsonTooltip

"""Hydrofabric utilities: CONUS dataset download and map helpers."""

import contextlib
import logging
import os
import warnings

_NGIAB_DIR = os.path.expanduser("~/.ngiab")
_NGEN_PYTHON = "/ngen/.venv/bin/python"
_HF_BOOTSTRAPPED = False

_DOWNLOAD_SCRIPT = """
from data_sources.source_validation import FilePaths, download_and_update_hf

download_and_update_hf()
FilePaths.set_working_dir("~/ngiab_preprocess_output/")
"""


@contextlib.contextmanager
def _quiet_output():
    saved_env = {
        key: os.environ.get(key)
        for key in ("TQDM_DISABLE", "HF_HUB_DISABLE_PROGRESS_BARS", "RICH_DISABLE")
    }
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["RICH_DISABLE"] = "1"

    tqdm_restore = []
    try:
        import tqdm as tqdm_mod
        import tqdm.auto as tqdm_auto

        for module, name, original in (
            (tqdm_mod, "tqdm", tqdm_mod.tqdm),
            (tqdm_auto, "tqdm", tqdm_auto.tqdm),
        ):

            def _make_disabled(orig):
                def _disabled(*args, **kwargs):
                    kwargs["disable"] = True
                    return orig(*args, **kwargs)

                return _disabled

            setattr(module, name, _make_disabled(original))
            tqdm_restore.append((module, name, original))
    except ImportError:
        pass

    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.setLevel(logging.ERROR)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with open(os.devnull, "w", encoding="utf-8") as devnull:
                with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
                    yield
    finally:
        root_logger.setLevel(previous_level)
        for module, name, original in reversed(tqdm_restore):
            setattr(module, name, original)
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def conus_hydrofabric_download():
    """Download CONUS hydrofabric if ~/.ngiab is missing."""
    import subprocess

    global _HF_BOOTSTRAPPED
    if _HF_BOOTSTRAPPED or os.path.isdir(_NGIAB_DIR):
        _HF_BOOTSTRAPPED = True
        return

    print(
        "Hydrofabric dataset: downloading and unpacking (~2-3 min). Please wait...",
        flush=True,
    )

    if not os.path.isfile(_NGEN_PYTHON):
        raise FileNotFoundError(
            f"NGIAB Python not found at {_NGEN_PYTHON}. "
            "Run this notebook in the NGIAB environment."
        )

    # Run inside /ngen/.venv to avoid boto3/botocore clashes with the notebook kernel.
    with _quiet_output():
        subprocess.run(
            [_NGEN_PYTHON, "-c", _DOWNLOAD_SCRIPT],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    _HF_BOOTSTRAPPED = True
    print("Hydrofabric dataset: ready.", flush=True)
    
# _NGIAB_DIR = os.path.expanduser("~/.ngiab")
# _VENV_SITE_PACKAGES = "/ngen/.venv/lib/python3.11/site-packages"
# _HF_BOOTSTRAPPED = False
# def ensure_hydrofabric_data() -> None:
#     """Download hydrofabric if not available in the default location."""
#     global _HF_BOOTSTRAPPED
#     if _HF_BOOTSTRAPPED:
#         return
#     if os.path.isdir(_NGIAB_DIR):
#         _HF_BOOTSTRAPPED = True
#         return
#     sys.path.insert(0, _VENV_SITE_PACKAGES)
#     try:
#         from data_sources.source_validation import download_and_update_hf, FilePaths
#         download_and_update_hf()
#         FilePaths.set_working_dir("~/ngiab_preprocess_output/")
#     finally:
#         if sys.path and sys.path[0] == _VENV_SITE_PACKAGES:
#             sys.path.pop(0)
#     _HF_BOOTSTRAPPED = True
# # Runs automatically when this module is imported
# ensure_hydrofabric_data()

def display_hydrofabric_map(gpkg_path):
    # Load layers
    divides = gpd.read_file(gpkg_path, layer='divides')
    flowpaths = gpd.read_file(gpkg_path, layer='flowpaths')
    nexus = gpd.read_file(gpkg_path, layer='nexus')
    hydrolocations = gpd.read_file(gpkg_path, layer='hydrolocations')  # Load hydrolocations layer

    # Convert to WGS84 (for web maps)
    target_crs = "EPSG:4326"
    divides = divides.to_crs(target_crs)
    flowpaths = flowpaths.to_crs(target_crs)
    nexus = nexus.to_crs(target_crs)
    hydrolocations = hydrolocations.to_crs(target_crs)  # Convert hydrolocations to target CRS

    # Filter hydrolocations for "gages" in the 'hl_reference' column
    gages = hydrolocations[hydrolocations['hl_reference'].str.contains('gages', case=False, na=False)]

    # Get map center using the full extent of all layers
    all_geometries = divides.geometry.unary_union.union(flowpaths.geometry.unary_union).union(nexus.geometry.unary_union).union(gages.geometry.unary_union)
    bounds = all_geometries.bounds  # Get the bounds of the combined geometries (minx, miny, maxx, maxy)

    # Create the map centered around the full extent of the features
    m = folium.Map(location=[(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2],
                   zoom_start=12)

    # Define tooltips
    def tooltip(gdf, label):
        return GeoJsonTooltip(
            fields=["name"] if "name" in gdf.columns else ["id"],
            aliases=[f"{label}:"]
        )

    # Add GeoJson layers with default styling
    GeoJson(divides,
            name='Divides',
            style_function=lambda x: {'color': 'black', 'weight': 2, 'fillOpacity': 0},
            tooltip=tooltip(divides, "Divide")).add_to(m)

    GeoJson(flowpaths,
            name='Flowpaths',
            style_function=lambda x: {'color': 'blue', 'weight': 2},
            tooltip=tooltip(flowpaths, "Flowpath")).add_to(m)

    # Nexus as circles instead of lines
    for _, row in nexus.iterrows():
        geom = row.geometry
        if geom.geom_type == 'Point':
            folium.CircleMarker(
                location=[geom.y, geom.x],
                radius=5,
                color='red',
                fill=True,
                fill_opacity=1,
                popup=row.get("name", row.get("id", "Nexus"))
            ).add_to(m)

    # Add Gages to the map (from the hydrolocations layer)
    for _, row in gages.iterrows():
        geom = row.geometry
        if geom.geom_type == 'Point':
            folium.Marker(
                location=[geom.y, geom.x],
                popup=f"Gage Name: {row.get('hl_uri', 'No Name')}<br> Divide ID: {row.get('id', 'No ID')}",
                icon=folium.Icon(color='blue', icon='tachometer-alt', prefix='fa')  # Use FontAwesome cloud icon for gages
            ).add_to(m)

    # Fit map bounds to show the full extent of all layers
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    folium.LayerControl().add_to(m)
    return m
