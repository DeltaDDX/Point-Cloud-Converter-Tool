import numpy as np

try:
    from .. import utils
    from . import config
except ImportError:
    import utils

    try:
        from cbh import config
    except ImportError:
        import config


def postprocess_cbh(
    cbh_grid,
    canopy_height_grid=None,
    canopy_cover_grid=None,
    min_canopy_height=config.MIN_CANOPY_HEIGHT,
    cover_threshold=config.COVER_THRESHOLD,
    nodata=utils.DEFAULT_NODATA,
):
    """
    Apply physical and data-quality constraints to a CBH grid.
    """
    if cbh_grid is None:
        return None

    cbh = np.asarray(cbh_grid, dtype=np.float32).copy()
    valid = np.isfinite(cbh) & (cbh != nodata)

    cbh[valid & (cbh < 0)] = 0
    cbh[valid & (cbh < min_canopy_height)] = 0

    if canopy_cover_grid is not None:
        canopy_cover = _validate_matching_grid(canopy_cover_grid, cbh.shape, "canopy_cover_grid")
        low_cover = np.isfinite(canopy_cover) & (canopy_cover < cover_threshold)
        cbh[valid & low_cover] = 0
        valid &= np.isfinite(canopy_cover) & (canopy_cover != nodata)

    if canopy_height_grid is not None:
        canopy_height = _validate_matching_grid(
            canopy_height_grid,
            cbh.shape,
            "canopy_height_grid",
        )
        valid_height = np.isfinite(canopy_height) & (canopy_height != nodata)
        cbh[valid & valid_height & (canopy_height < cbh)] = canopy_height[
            valid & valid_height & (canopy_height < cbh)
        ]
        cbh[valid & valid_height & (canopy_height < min_canopy_height)] = 0
        valid &= valid_height

    cbh[~valid] = nodata
    return cbh.astype(np.float32)


def build_valid_mask(*grids, nodata=utils.DEFAULT_NODATA):
    """
    Build a shared validity mask for rasters using finite, non-nodata cells.
    """
    if not grids:
        raise ValueError("at least one grid is required")

    first = np.asarray(grids[0])
    mask = np.ones(first.shape, dtype=bool)

    for index, grid in enumerate(grids):
        if grid is None:
            continue
        grid = _validate_matching_grid(grid, first.shape, f"grid_{index}")
        mask &= np.isfinite(grid) & (grid != nodata)

    return mask


def _validate_matching_grid(grid, shape, name):
    grid = np.asarray(grid, dtype=np.float32)
    if grid.shape != shape:
        raise ValueError(f"{name} shape {grid.shape} does not match {shape}")
    return grid
