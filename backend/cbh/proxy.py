import numpy as np

try:
    from .. import utils
except ImportError:
    import utils


def estimate_cbh_proxy(
    vertical_profiles,
    min_canopy_height=2.0,
    min_bin_points=2,
    min_column_points=5,
    gap_tolerance_bins=1,
    min_canopy_depth_bins=2,
    nodata=utils.DEFAULT_NODATA,
):
    """
    Estimate CBH from vertical profiles by finding the first sustained canopy
    density above the minimum canopy height.
    """
    if vertical_profiles is None:
        return None

    histogram = vertical_profiles.get("histogram")
    bin_edges = vertical_profiles.get("bin_edges")
    point_counts = vertical_profiles.get("point_counts")

    if histogram is None or bin_edges is None:
        raise ValueError("vertical_profiles must include histogram and bin_edges")
    if histogram.ndim != 3:
        raise ValueError("histogram must be a 3D array")

    rows, cols, bin_count = histogram.shape
    if len(bin_edges) != bin_count + 1:
        raise ValueError("bin_edges length must equal histogram depth + 1")

    bin_bottoms = bin_edges[:-1].astype(np.float32)
    start_bin = np.searchsorted(bin_bottoms, min_canopy_height, side="left")
    start_bin = int(np.clip(start_bin, 0, bin_count))

    occupied = histogram >= min_bin_points
    cbh = np.full((rows, cols), nodata, dtype=np.float32)

    if point_counts is None:
        valid_cells = np.sum(histogram, axis=2) >= min_column_points
    else:
        valid_cells = point_counts >= min_column_points

    for row in range(rows):
        for col in range(cols):
            if not valid_cells[row, col]:
                continue

            canopy_bin = _first_sustained_bin(
                occupied[row, col],
                start_bin,
                gap_tolerance_bins,
                min_canopy_depth_bins,
            )
            if canopy_bin is not None:
                cbh[row, col] = bin_bottoms[canopy_bin]

    return cbh


def _first_sustained_bin(
    occupied_profile,
    start_bin,
    gap_tolerance_bins,
    min_canopy_depth_bins,
):
    candidate_bins = np.flatnonzero(occupied_profile[start_bin:]) + start_bin
    if candidate_bins.size == 0:
        return None

    for candidate in candidate_bins:
        occupied_seen = 0
        gaps_seen = 0

        for bin_idx in range(candidate, len(occupied_profile)):
            if occupied_profile[bin_idx]:
                occupied_seen += 1
                gaps_seen = 0
                if occupied_seen >= min_canopy_depth_bins:
                    return int(candidate)
            else:
                gaps_seen += 1
                if gaps_seen > gap_tolerance_bins:
                    break

    return None
