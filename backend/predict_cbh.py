import json
import os
import sys
import traceback

import laspy

import utils
from cbh import config
from cbh.model import CBHModel
from cbh.pipeline import generate_cbh
from dtm import generate_dtm_grid
from generate_cbh import _get_float, _get_int, _get_number_list


def predict_cbh_outputs(input_path, output_dir, resolution, model_path, params):
    if not model_path:
        raise ValueError("modelPath is required for CBH prediction")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"CBH model not found: {model_path}")

    os.makedirs(output_dir, exist_ok=True)
    model = CBHModel.load(model_path)

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

        result = generate_cbh(
            las_file,
            dtm_grid,
            bounds=bounds,
            resolution=resolution,
            mode="predict",
            model=model,
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

    predicted_path = None
    if result and "outputs" in result:
        predicted_path = result["outputs"].get("cbh_predicted")

    return True, predicted_path or output_dir


def main():
    if len(sys.argv) < 6:
        print(json.dumps({"status": "error", "message": "Missing arguments"}))
        return

    try:
        input_path = sys.argv[1]
        output_dir = sys.argv[2]
        resolution = float(sys.argv[3])
        model_path = sys.argv[4]
        params = json.loads(sys.argv[5])

        success, output = predict_cbh_outputs(
            input_path,
            output_dir,
            resolution,
            model_path,
            params,
        )
        if success:
            utils.send_progress(100, "Done")
            print(json.dumps({"status": "success", "file": output}))
        else:
            print(json.dumps({"status": "error", "message": output}))

    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"CBH prediction crash: {str(exc)}",
                    "traceback": traceback.format_exc(),
                }
            )
        )


if __name__ == "__main__":
    main()
