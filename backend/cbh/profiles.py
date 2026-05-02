import numpy as np

try:
    from .. import utils
    from ..dtm import generate_dtm_grid
except ImportError:
    import utils
    from dtm import generate_dtm_grid


def generate_vertical_profiles(
    las_file,
    width,
    height,
    resolution,
    bounds,
    dtm_grid=None,
    height_bin_size=0.5,
    max_height=60.0,
    min_height=0.0,
    progress_callback=None,
):
    """
    Build per-cell vertical point-count profiles from a LAS/LAZ file.

    Returns a dictionary with a 3-D histogram shaped
    (height, width, height_bins), plus bin metadata needed by the CBH proxy.
    Point heights are normalized against the supplied DTM grid. If no DTM is
    supplied, one is generated from the point cloud using the existing DTM path.
    """
    if height_bin_size <= 0:
        raise ValueError("height_bin_size must be greater than zero")
    if max_height <= min_height:
        raise ValueError("max_height must be greater than min_height")

    if dtm_grid is None:
        dtm_grid, _ = generate_dtm_grid(
            las_file, width, height, resolution, bounds, progress_callback
        )
        if dtm_grid is None:
            return None
        las_file.seek(0)

    min_x, max_y = bounds
    bin_edges = np.arange(
        min_height, max_height + height_bin_size, height_bin_size, dtype=np.float32
    )
    if bin_edges[-1] < max_height:
        bin_edges = np.append(bin_edges, np.float32(max_height))

    bin_count = len(bin_edges) - 1
    profile_counts = np.zeros((height, width, bin_count), dtype=np.uint32)
    point_counts = np.zeros((height, width), dtype=np.uint32)

    total_points = las_file.header.point_count
    points_processed = 0

    if progress_callback:
        progress_callback(1, "Generating vertical profiles...")

    for points in las_file.chunk_iterator(utils.CHUNK_SIZE):
        x = points.x
        y = points.y
        z = points.z

        col = np.clip(((x - min_x) / resolution).astype(np.int64), 0, width - 1)
        row = np.clip(((max_y - y) / resolution).astype(np.int64), 0, height - 1)

        ground = dtm_grid[row, col]
        normalized_height = z - ground
        valid = (
            (ground != utils.DEFAULT_NODATA)
            & np.isfinite(ground)
            & np.isfinite(normalized_height)
            & (normalized_height >= min_height)
            & (normalized_height < max_height)
        )

        if np.any(valid):
            row_valid = row[valid]
            col_valid = col[valid]
            h_valid = normalized_height[valid]

            bin_idx = np.floor((h_valid - min_height) / height_bin_size).astype(np.int64)
            bin_idx = np.clip(bin_idx, 0, bin_count - 1)

            flat_cell = row_valid * width + col_valid
            flat_profile = flat_cell * bin_count + bin_idx

            np.add.at(profile_counts.ravel(), flat_profile, 1)
            np.add.at(point_counts.ravel(), flat_cell, 1)

        points_processed += len(x)
        if progress_callback and total_points:
            pct = 1 + (points_processed / total_points) * 98
            progress_callback(pct, "Generating vertical profiles...")

    if progress_callback:
        progress_callback(100, "Vertical profiles complete")

    return {
        "histogram": profile_counts,
        "bin_edges": bin_edges,
        "bin_size": float(height_bin_size),
        "min_height": float(min_height),
        "max_height": float(max_height),
        "point_counts": point_counts,
        "dtm": dtm_grid,
    }
