import numpy as np
import rasterio

try:
    from .. import utils
except ImportError:
    import utils


def write_cbh_proxy_raster(
    output_path,
    cbh_proxy,
    width,
    height,
    transform,
    crs,
    nodata=utils.DEFAULT_NODATA,
):
    """Write a single-band canopy-base-height proxy raster."""
    if cbh_proxy is None:
        raise ValueError("cbh_proxy cannot be None")

    data = np.asarray(cbh_proxy, dtype=np.float32)
    if data.shape != (height, width):
        raise ValueError(
            f"cbh_proxy shape {data.shape} does not match raster shape {(height, width)}"
        )

    data = data.copy()
    data[~np.isfinite(data)] = nodata

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=rasterio.float32,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(data, 1)
        dst.set_band_description(1, "Canopy Base Height Proxy")

    return output_path


def write_single_band_raster(
    output_path,
    data,
    transform,
    crs,
    band_description=None,
    nodata=utils.DEFAULT_NODATA,
):
    """Write a single-band float32 raster using the shape of data."""
    if data is None:
        raise ValueError("data cannot be None")

    data = np.asarray(data, dtype=np.float32)
    height, width = data.shape
    writable = data.copy()
    writable[~np.isfinite(writable)] = nodata

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=rasterio.float32,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(writable, 1)
        if band_description:
            dst.set_band_description(1, band_description)

    return output_path


def write_feature_raster(
    output_path,
    feature_data,
    transform,
    crs,
    nodata=utils.DEFAULT_NODATA,
):
    """Write generated CBH features as a multi-band float32 GeoTIFF."""
    if feature_data is None:
        raise ValueError("feature_data cannot be None")

    feature_stack = np.asarray(feature_data["feature_stack"], dtype=np.float32)
    feature_names = feature_data["feature_names"]
    if feature_stack.ndim != 3:
        raise ValueError("feature_stack must be a 3D array")
    if feature_stack.shape[2] != len(feature_names):
        raise ValueError("feature_names length must match feature_stack band count")

    height, width, band_count = feature_stack.shape
    writable = feature_stack.copy()
    writable[~np.isfinite(writable)] = nodata

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=band_count,
        dtype=rasterio.float32,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        for band_idx, name in enumerate(feature_names, start=1):
            dst.write(writable[:, :, band_idx - 1], band_idx)
            dst.set_band_description(band_idx, name)

    return output_path
