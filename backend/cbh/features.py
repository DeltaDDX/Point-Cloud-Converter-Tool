import numpy as np

try:
    from .. import utils
except ImportError:
    import utils


DEFAULT_HEIGHT_PERCENTILES = (10, 25, 50, 75, 90, 95)
DEFAULT_COVER_THRESHOLDS = (0.5, 1.0, 2.0, 5.0)


def generate_cbh_features(
    vertical_profiles,
    canopy_height_grid=None,
    canopy_cover_grid=None,
    height_percentiles=DEFAULT_HEIGHT_PERCENTILES,
    canopy_cover_thresholds=DEFAULT_COVER_THRESHOLDS,
    density_bin_edges=None,
    nodata=utils.DEFAULT_NODATA,
):
    """
    Generate per-cell CBH model features from vertical profile histograms.

    Returns a dict with:
    - feature_stack: float32 array shaped (rows, cols, feature_count)
    - feature_names: names matching the last feature_stack axis
    - valid_mask: cells with enough data to use the generated features
    """
    if vertical_profiles is None:
        return None

    histogram, bin_edges, point_counts = _validate_vertical_profiles(vertical_profiles)
    rows, cols, _ = histogram.shape

    if point_counts is None:
        point_counts = np.sum(histogram, axis=2, dtype=np.uint32)

    bin_bottoms = bin_edges[:-1].astype(np.float32)
    bin_tops = bin_edges[1:].astype(np.float32)
    bin_centers = ((bin_bottoms + bin_tops) / 2.0).astype(np.float32)

    valid_mask = point_counts > 0
    features = []
    names = []

    _append_feature(features, names, point_counts.astype(np.float32), "return_count")

    for percentile in height_percentiles or ():
        percentile_value = _weighted_percentile_from_histogram(
            histogram,
            bin_centers,
            point_counts,
            percentile,
            nodata,
        )
        _append_feature(
            features,
            names,
            percentile_value,
            f"height_p{_format_number(percentile)}",
        )

    for threshold in canopy_cover_thresholds or ():
        cover = _cover_above_threshold(
            histogram,
            bin_bottoms,
            point_counts,
            threshold,
            nodata,
        )
        _append_feature(
            features,
            names,
            cover,
            f"cover_ge_{_format_number(threshold)}m",
        )

    if density_bin_edges is None:
        density_bin_edges = bin_edges
    density_features, density_names = _vertical_bin_densities(
        histogram,
        bin_edges,
        point_counts,
        density_bin_edges,
        nodata,
    )
    features.extend(density_features)
    names.extend(density_names)

    largest_gap = _largest_vertical_gap(histogram, bin_edges, point_counts, nodata)
    _append_feature(features, names, largest_gap, "largest_vertical_gap")

    if canopy_height_grid is not None:
        canopy_height = _validate_grid(
            canopy_height_grid,
            rows,
            cols,
            "canopy_height_grid",
        )
        valid_mask &= np.isfinite(canopy_height) & (canopy_height != nodata)
        _append_feature(features, names, canopy_height, "canopy_height")

    if canopy_cover_grid is not None:
        canopy_cover = _validate_grid(
            canopy_cover_grid,
            rows,
            cols,
            "canopy_cover_grid",
        )
        valid_mask &= np.isfinite(canopy_cover) & (canopy_cover != nodata)
        _append_feature(features, names, canopy_cover, "canopy_cover")

    feature_stack = np.stack(features, axis=2).astype(np.float32)
    feature_stack[~valid_mask, :] = nodata

    return {
        "feature_stack": feature_stack,
        "feature_names": names,
        "valid_mask": valid_mask,
        "nodata": nodata,
    }


def features_to_table(feature_data, target_grid=None):
    """
    Convert generated raster features into a 2D model table.

    If target_grid is provided, only cells with valid target values are returned.
    """
    if feature_data is None:
        return None

    feature_stack = feature_data["feature_stack"]
    valid_mask = feature_data["valid_mask"].copy()
    nodata = feature_data.get("nodata", utils.DEFAULT_NODATA)

    if target_grid is not None:
        target = _validate_grid(
            target_grid,
            feature_stack.shape[0],
            feature_stack.shape[1],
            "target_grid",
        )
        target_valid = np.isfinite(target) & (target != nodata)
        valid_mask &= target_valid
    else:
        target = None

    flat_features = feature_stack[valid_mask]
    result = {
        "X": flat_features.astype(np.float32),
        "feature_names": feature_data["feature_names"],
        "row": np.nonzero(valid_mask)[0],
        "col": np.nonzero(valid_mask)[1],
    }

    if target is not None:
        result["y"] = target[valid_mask].astype(np.float32)

    return result


def _validate_vertical_profiles(vertical_profiles):
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
    if point_counts is not None and point_counts.shape != (rows, cols):
        raise ValueError("point_counts shape must match histogram rows and columns")

    return histogram, np.asarray(bin_edges, dtype=np.float32), point_counts


def _append_feature(features, names, values, name):
    features.append(np.asarray(values, dtype=np.float32))
    names.append(name)


def _weighted_percentile_from_histogram(
    histogram,
    bin_centers,
    point_counts,
    percentile,
    nodata,
):
    if percentile < 0 or percentile > 100:
        raise ValueError("height percentiles must be between 0 and 100")

    rows, cols, _ = histogram.shape
    output = np.full((rows, cols), nodata, dtype=np.float32)
    valid = point_counts > 0
    if not np.any(valid):
        return output

    cumulative = np.cumsum(histogram, axis=2)
    rank = np.ceil(point_counts.astype(np.float32) * (float(percentile) / 100.0))
    rank = np.maximum(rank, 1)

    hit = cumulative >= rank[:, :, None]
    first_hit = np.argmax(hit, axis=2)
    output[valid] = bin_centers[first_hit[valid]]
    return output


def _cover_above_threshold(histogram, bin_bottoms, point_counts, threshold, nodata):
    rows, cols, _ = histogram.shape
    output = np.full((rows, cols), nodata, dtype=np.float32)
    valid = point_counts > 0
    if not np.any(valid):
        return output

    cover_bins = bin_bottoms >= float(threshold)
    cover_counts = np.sum(histogram[:, :, cover_bins], axis=2, dtype=np.float32)
    output[valid] = cover_counts[valid] / point_counts[valid].astype(np.float32)
    return output


def _vertical_bin_densities(
    histogram,
    bin_edges,
    point_counts,
    density_bin_edges,
    nodata,
):
    density_bin_edges = np.asarray(density_bin_edges, dtype=np.float32)
    if density_bin_edges.ndim != 1 or density_bin_edges.size < 2:
        raise ValueError("density_bin_edges must contain at least two edges")
    if np.any(np.diff(density_bin_edges) <= 0):
        raise ValueError("density_bin_edges must be strictly increasing")

    rows, cols, _ = histogram.shape
    valid = point_counts > 0
    features = []
    names = []

    bin_bottoms = bin_edges[:-1]
    bin_tops = bin_edges[1:]

    for low, high in zip(density_bin_edges[:-1], density_bin_edges[1:]):
        included = (bin_bottoms >= low) & (bin_tops <= high)
        density = np.full((rows, cols), nodata, dtype=np.float32)
        if np.any(valid):
            counts = np.sum(histogram[:, :, included], axis=2, dtype=np.float32)
            density[valid] = counts[valid] / point_counts[valid].astype(np.float32)
        features.append(density)
        names.append(f"density_{_format_number(low)}m_{_format_number(high)}m")

    return features, names


def _largest_vertical_gap(histogram, bin_edges, point_counts, nodata):
    rows, cols, _ = histogram.shape
    output = np.full((rows, cols), nodata, dtype=np.float32)
    bin_size = float(np.median(np.diff(bin_edges)))

    for row in range(rows):
        for col in range(cols):
            if point_counts[row, col] == 0:
                continue

            occupied_bins = np.flatnonzero(histogram[row, col] > 0)
            if occupied_bins.size < 2:
                output[row, col] = 0
                continue

            largest_empty_run = int(np.max(np.diff(occupied_bins) - 1))
            output[row, col] = largest_empty_run * bin_size

    return output


def _validate_grid(grid, rows, cols, name):
    grid = np.asarray(grid, dtype=np.float32)
    if grid.shape != (rows, cols):
        raise ValueError(f"{name} shape {grid.shape} does not match {(rows, cols)}")
    return grid


def _format_number(value):
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return str(value).replace(".", "p")
