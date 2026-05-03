import numpy as np

try:
    from .. import utils
except ImportError:
    import utils


def normalize_heights(z_values, row_indices, col_indices, dtm_grid, nodata=utils.DEFAULT_NODATA):
    """
    Convert point elevations to height above ground using a DTM grid.

    Returns normalized heights and a validity mask. Invalid DTM cells produce nodata
    heights and False mask values.
    """
    z_values = np.asarray(z_values, dtype=np.float32)
    row_indices = np.asarray(row_indices, dtype=np.int64)
    col_indices = np.asarray(col_indices, dtype=np.int64)
    dtm_grid = np.asarray(dtm_grid, dtype=np.float32)

    if row_indices.shape != z_values.shape or col_indices.shape != z_values.shape:
        raise ValueError("z_values, row_indices, and col_indices must have matching shapes")
    if dtm_grid.ndim != 2:
        raise ValueError("dtm_grid must be a 2D array")

    rows, cols = dtm_grid.shape
    in_bounds = (
        (row_indices >= 0)
        & (row_indices < rows)
        & (col_indices >= 0)
        & (col_indices < cols)
    )

    normalized = np.full(z_values.shape, nodata, dtype=np.float32)
    valid = np.zeros(z_values.shape, dtype=bool)

    if not np.any(in_bounds):
        return normalized, valid

    ground = np.full(z_values.shape, nodata, dtype=np.float32)
    ground[in_bounds] = dtm_grid[row_indices[in_bounds], col_indices[in_bounds]]
    valid = in_bounds & np.isfinite(ground) & (ground != nodata) & np.isfinite(z_values)
    normalized[valid] = z_values[valid] - ground[valid]

    return normalized, valid


def normalize_las_points(
    las_file,
    dtm_grid,
    resolution,
    bounds,
    nodata=utils.DEFAULT_NODATA,
    progress_callback=None,
):
    """
    Normalize all points in a LAS/LAZ file into row, column, and height arrays.
    """
    min_x, max_y = bounds
    rows, cols = dtm_grid.shape

    row_chunks = []
    col_chunks = []
    height_chunks = []

    total_points = las_file.header.point_count
    points_processed = 0

    if progress_callback:
        progress_callback(1, "Normalizing point heights...")

    for points in las_file.chunk_iterator(utils.CHUNK_SIZE):
        x = points.x
        y = points.y
        z = points.z

        col = np.clip(((x - min_x) / resolution).astype(np.int64), 0, cols - 1)
        row = np.clip(((max_y - y) / resolution).astype(np.int64), 0, rows - 1)

        normalized, valid = normalize_heights(z, row, col, dtm_grid, nodata)
        if np.any(valid):
            row_chunks.append(row[valid])
            col_chunks.append(col[valid])
            height_chunks.append(normalized[valid])

        points_processed += len(x)
        if progress_callback and total_points:
            pct = 1 + (points_processed / total_points) * 98
            progress_callback(pct, "Normalizing point heights...")

    if progress_callback:
        progress_callback(100, "Point normalization complete")

    if not height_chunks:
        empty_int = np.array([], dtype=np.int64)
        empty_float = np.array([], dtype=np.float32)
        return empty_int, empty_int, empty_float

    return (
        np.concatenate(row_chunks),
        np.concatenate(col_chunks),
        np.concatenate(height_chunks).astype(np.float32),
    )
