import json
import os
import sys
import traceback

import laspy

import utils
from dtm import generate_dtm_grid
from cbh import config
from cbh.pipeline import generate_cbh


def _get_float(params, name, default, minimum=0, allow_zero=False):
    try:
        value = float(params.get(name, default))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")

    if allow_zero:
        if value < minimum:
            raise ValueError(f"{name} must be at least {minimum}")
    elif value <= minimum:
        raise ValueError(f"{name} must be greater than {minimum}")

    return value


def _get_int(params, name, default, minimum=0):
    try:
        value = int(params.get(name, default))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _get_number_list(params, name, default):
    raw_value = params.get(name, default)
    if isinstance(raw_value, str):
        raw_value = [part.strip() for part in raw_value.split(",") if part.strip()]

    values = []
    for item in raw_value:
        try:
            value = float(item)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must contain only numbers")
        if value < 0:
            raise ValueError(f"{name} cannot contain negative values")
        values.append(value)

    if not values:
        raise ValueError(f"{name} must contain at least one value")
    return tuple(values)


def generate_cbh_outputs(input_path, output_dir, resolution, params):
    os.makedirs(output_dir, exist_ok=True)

    with laspy.open(input_path) as las_file:
        width, height, transform, bounds = utils.get_grid_dimensions(
            las_file.header,
            resolution,
        )

        dtm_grid, _ = generate_dtm_grid(
            las_file,
            width,
            height,
            resolution,
            bounds,
            progress_callback=lambda p, m: utils.send_progress(p * 0.35, m),
        )
        if dtm_grid is None:
            return False, "Could not generate DTM"

        las_file.seek(0)

        try:
            crs = las_file.header.parse_crs()
        except Exception:
            crs = None

        generate_cbh(
            las_file,
            dtm_grid,
            bounds=bounds,
            resolution=resolution,
            mode="train",
            output_dir=output_dir,
            transform=transform,
            crs=crs,
            height_bin_size=_get_float(params, "heightBinSize", config.HEIGHT_BIN_SIZE),
            min_profile_height=config.MIN_PROFILE_HEIGHT,
            max_profile_height=_get_float(params, "maxProfileHeight", config.MAX_PROFILE_HEIGHT),
            min_canopy_height=_get_float(
                params,
                "minCanopyHeight",
                config.MIN_CANOPY_HEIGHT,
                allow_zero=True,
            ),
            cover_threshold=_get_float(
                params,
                "coverThreshold",
                config.COVER_THRESHOLD,
                allow_zero=True,
            ),
            min_bin_points=_get_int(params, "minBinPoints", config.MIN_BIN_POINTS, 1),
            min_column_points=_get_int(
                params,
                "minColumnPoints",
                config.MIN_COLUMN_POINTS,
                1,
            ),
            gap_tolerance_bins=_get_int(
                params,
                "gapToleranceBins",
                config.GAP_TOLERANCE_BINS,
                0,
            ),
            min_canopy_depth_bins=_get_int(
                params,
                "minCanopyDepthBins",
                config.MIN_CANOPY_DEPTH_BINS,
                1,
            ),
            height_percentiles=_get_number_list(
                params,
                "heightPercentiles",
                config.HEIGHT_PERCENTILES,
            ),
            canopy_cover_thresholds=_get_number_list(
                params,
                "coverThresholds",
                config.COVER_THRESHOLDS,
            ),
            progress_callback=lambda p, m: utils.send_progress(35 + p * 0.65, m),
        )

    return True, "CBH feature extraction complete"


def main():
    if len(sys.argv) < 5:
        print(json.dumps({"status": "error", "message": "Missing arguments"}))
        return

    try:
        input_path = sys.argv[1]
        output_dir = sys.argv[2]
        resolution = float(sys.argv[3])
        params = json.loads(sys.argv[4])

        success, message = generate_cbh_outputs(input_path, output_dir, resolution, params)
        if success:
            utils.send_progress(100, "Done")
            print(json.dumps({"status": "success", "file": output_dir}))
        else:
            print(json.dumps({"status": "error", "message": message}))

    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"CBH extraction crash: {str(exc)}",
                    "traceback": traceback.format_exc(),
                }
            )
        )


if __name__ == "__main__":
    main()
