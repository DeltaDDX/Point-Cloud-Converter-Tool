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
