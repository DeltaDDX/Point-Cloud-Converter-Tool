import csv
import os

import numpy as np

try:
    from .. import utils
    from . import config
    from .features import features_to_table, generate_cbh_features
    from .postprocess import postprocess_cbh
    from .profiles import generate_vertical_profiles
    from .proxy import estimate_cbh_proxy
    from .rasterize import write_feature_raster, write_single_band_raster
except ImportError:
    import utils

    try:
        from cbh import config
        from cbh.features import features_to_table, generate_cbh_features
        from cbh.postprocess import postprocess_cbh
        from cbh.profiles import generate_vertical_profiles
        from cbh.proxy import estimate_cbh_proxy
        from cbh.rasterize import write_feature_raster, write_single_band_raster
    except ImportError:
        import config
        from features import features_to_table, generate_cbh_features
        from postprocess import postprocess_cbh
        from profiles import generate_vertical_profiles
        from proxy import estimate_cbh_proxy
        from rasterize import write_feature_raster, write_single_band_raster


def generate_cbh(
    las_file,
    dtm_grid,
    canopy_height_grid=None,
    canopy_cover_grid=None,
    bounds=None,
    resolution=None,
    model=None,
    mode="proxy",
    target_grid=None,
    output_dir=None,
    transform=None,
    crs=None,
    height_bin_size=config.HEIGHT_BIN_SIZE,
    min_profile_height=config.MIN_PROFILE_HEIGHT,
    max_profile_height=config.MAX_PROFILE_HEIGHT,
    min_canopy_height=config.MIN_CANOPY_HEIGHT,
    cover_threshold=config.COVER_THRESHOLD,
    min_bin_points=config.MIN_BIN_POINTS,
    min_column_points=config.MIN_COLUMN_POINTS,
    gap_tolerance_bins=config.GAP_TOLERANCE_BINS,
    min_canopy_depth_bins=config.MIN_CANOPY_DEPTH_BINS,
    height_percentiles=config.HEIGHT_PERCENTILES,
    canopy_cover_thresholds=config.COVER_THRESHOLDS,
    progress_callback=None,
):
    """
    Run the CBH workflow.

    Modes:
    - proxy: generate a rule-based CBH raster
    - predict: generate model features and predicted CBH raster
    - train: generate model features and a model-ready training table
    """
    if dtm_grid is None:
        raise ValueError("dtm_grid is required")
    if bounds is None:
        raise ValueError("bounds is required")
    if resolution is None:
        raise ValueError("resolution is required")

    mode = mode.lower()
    if mode not in {"proxy", "predict", "train"}:
        raise ValueError("mode must be one of: proxy, predict, train")

    dtm_grid = np.asarray(dtm_grid, dtype=np.float32)
    if dtm_grid.ndim != 2:
        raise ValueError("dtm_grid must be a 2D array")

    height, width = dtm_grid.shape

    if progress_callback:
        progress_callback(1, "Building CBH vertical profiles...")

    vertical_profiles = generate_vertical_profiles(
        las_file,
        width,
        height,
        resolution,
        bounds,
        dtm_grid=dtm_grid,
        height_bin_size=height_bin_size,
        max_height=max_profile_height,
        min_height=min_profile_height,
        progress_callback=_scale_progress(progress_callback, 1, 45),
    )
    if vertical_profiles is None:
        return None

    feature_data = generate_cbh_features(
        vertical_profiles,
        canopy_height_grid=canopy_height_grid,
        canopy_cover_grid=canopy_cover_grid,
        height_percentiles=height_percentiles,
        canopy_cover_thresholds=canopy_cover_thresholds,
        nodata=config.NODATA,
    )

    result = {
        "mode": mode,
        "vertical_profiles": vertical_profiles,
        "features": feature_data,
        "valid_mask": feature_data["valid_mask"],
    }

    if mode in {"proxy", "train"}:
        cbh_proxy = estimate_cbh_proxy(
            vertical_profiles,
            min_canopy_height=min_canopy_height,
            min_bin_points=min_bin_points,
            min_column_points=min_column_points,
            gap_tolerance_bins=gap_tolerance_bins,
            min_canopy_depth_bins=min_canopy_depth_bins,
            nodata=config.NODATA,
        )
        cbh_proxy = postprocess_cbh(
            cbh_proxy,
            canopy_height_grid=canopy_height_grid,
            canopy_cover_grid=canopy_cover_grid,
            min_canopy_height=min_canopy_height,
            cover_threshold=cover_threshold,
            nodata=config.NODATA,
        )
        result["cbh_proxy"] = cbh_proxy

    if mode == "predict":
        if model is None:
            raise ValueError("model is required for predict mode")
        table = features_to_table(feature_data)
        predictions = model.predict(table["X"])
        cbh_predicted = np.full((height, width), config.NODATA, dtype=np.float32)
        cbh_predicted[table["row"], table["col"]] = predictions
        cbh_predicted = postprocess_cbh(
            cbh_predicted,
            canopy_height_grid=canopy_height_grid,
            canopy_cover_grid=canopy_cover_grid,
            min_canopy_height=min_canopy_height,
            cover_threshold=cover_threshold,
            nodata=config.NODATA,
        )
        result["feature_table"] = table
        result["cbh_predicted"] = cbh_predicted

    elif mode == "train":
        training_target = target_grid if target_grid is not None else result["cbh_proxy"]
        result["feature_table"] = features_to_table(feature_data, training_target)

    if output_dir is not None:
        result["outputs"] = write_cbh_outputs(
            output_dir,
            result,
            transform=transform,
            crs=crs,
            nodata=config.NODATA,
        )

    if progress_callback:
        progress_callback(100, "CBH workflow complete")

    return result


def write_cbh_outputs(output_dir, result, transform=None, crs=None, nodata=utils.DEFAULT_NODATA):
    """
    Write available CBH products to output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)
    outputs = {}

    if transform is not None:
        if "cbh_proxy" in result:
            outputs["cbh_proxy"] = write_single_band_raster(
                os.path.join(output_dir, "cbh_proxy.tif"),
                result["cbh_proxy"],
                transform,
                crs,
                "CBH Proxy",
                nodata,
            )
        if "cbh_predicted" in result:
            outputs["cbh_predicted"] = write_single_band_raster(
                os.path.join(output_dir, "cbh_predicted.tif"),
                result["cbh_predicted"],
                transform,
                crs,
                "CBH Predicted",
                nodata,
            )

        outputs["cbh_features"] = write_feature_raster(
            os.path.join(output_dir, "cbh_features.tif"),
            result["features"],
            transform,
            crs,
            nodata,
        )
        outputs["valid_mask"] = write_single_band_raster(
            os.path.join(output_dir, "valid_mask.tif"),
            result["valid_mask"].astype(np.float32),
            transform,
            crs,
            "Valid CBH Cells",
            nodata,
        )
        outputs.update(_write_diagnostic_rasters(output_dir, result, transform, crs, nodata))

    if "feature_table" in result and result["feature_table"] is not None:
        outputs["cbh_features_csv"] = write_feature_csv(
            os.path.join(output_dir, "cbh_features.csv"),
            result["feature_table"],
        )

    return outputs


def write_feature_csv(output_path, feature_table):
    """Write a model feature table to CSV without adding a dataframe dependency."""
    feature_names = feature_table["feature_names"]
    has_target = "y" in feature_table

    with open(output_path, "w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        header = ["row", "col", *feature_names]
        if has_target:
            header.append("target_cbh")
        writer.writerow(header)

        for index, row in enumerate(feature_table["X"]):
            csv_row = [
                int(feature_table["row"][index]),
                int(feature_table["col"][index]),
                *[float(value) for value in row],
            ]
            if has_target:
                csv_row.append(float(feature_table["y"][index]))
            writer.writerow(csv_row)

    return output_path


def _write_diagnostic_rasters(output_dir, result, transform, crs, nodata):
    outputs = {}
    feature_data = result["features"]
    feature_stack = feature_data["feature_stack"]
    names = feature_data["feature_names"]

    for feature_name, output_name, description in (
        ("return_count", "return_count.tif", "Return Count"),
        ("canopy_cover", "canopy_cover.tif", "Canopy Cover"),
        ("canopy_height", "canopy_height.tif", "Canopy Height"),
    ):
        if feature_name in names:
            band = names.index(feature_name)
            outputs[feature_name] = write_single_band_raster(
                os.path.join(output_dir, output_name),
                feature_stack[:, :, band],
                transform,
                crs,
                description,
                nodata,
            )

    confidence = _profile_confidence(result["vertical_profiles"], nodata)
    outputs["profile_confidence"] = write_single_band_raster(
        os.path.join(output_dir, "profile_confidence.tif"),
        confidence,
        transform,
        crs,
        "Profile Confidence",
        nodata,
    )
    return outputs


def _profile_confidence(vertical_profiles, nodata):
    point_counts = vertical_profiles["point_counts"].astype(np.float32)
    confidence = np.full(point_counts.shape, nodata, dtype=np.float32)
    valid = point_counts > 0
    if np.any(valid):
        confidence[valid] = np.clip(
            point_counts[valid] / float(config.MIN_COLUMN_POINTS),
            0.0,
            1.0,
        )
    return confidence


def _scale_progress(progress_callback, start, end):
    def callback(percent, message):
        scaled = start + (float(percent) / 100.0) * (end - start)
        progress_callback(scaled, message)

    return callback
