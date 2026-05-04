import numpy as np
from rasterio.fill import fillnodata
from scipy.interpolate import LinearNDInterpolator
from scipy.ndimage import gaussian_filter

import utils


MORPH_SEARCH_METERS = 20.0
TIN_TOLERANCE = 0.5
TIN_MAX_ITERATIONS = 5


def perform_tin_densification(dtm_raw_grid, resolution, search_meters):
    rows, cols = dtm_raw_grid.shape
    valid_y, valid_x = np.nonzero(dtm_raw_grid != np.inf)

    if len(valid_y) < 3:
        return dtm_raw_grid

    valid_z = dtm_raw_grid[valid_y, valid_x]

    block_size = int(search_meters / resolution)
    if block_size < 1:
        block_size = 1

    coarse_y = valid_y // block_size
    coarse_x = valid_x // block_size
    block_ids = coarse_y * cols + coarse_x

    sorter = np.lexsort((valid_z, block_ids))
    sorted_block_ids = block_ids[sorter]
    _, start_indices = np.unique(sorted_block_ids, return_index=True)

    end_indices = np.append(start_indices[1:], len(block_ids))
    counts = end_indices - start_indices
    points_to_skip = 2
    safe_offsets = np.clip(points_to_skip, 0, counts - 1)

    seed_indices_sorted = start_indices + safe_offsets
    seed_indices = sorter[seed_indices_sorted]

    is_ground_mask = np.zeros(len(valid_z), dtype=bool)
    is_ground_mask[seed_indices] = True

    for _ in range(TIN_MAX_ITERATIONS):
        ground_x = valid_x[is_ground_mask]
        ground_y = valid_y[is_ground_mask]
        ground_z = valid_z[is_ground_mask]

        try:
            tin_surf = LinearNDInterpolator(list(zip(ground_x, ground_y)), ground_z)
        except Exception:
            break

        candidate_mask = ~is_ground_mask
        cand_x = valid_x[candidate_mask]
        cand_y = valid_y[candidate_mask]
        cand_z = valid_z[candidate_mask]

        if len(cand_x) == 0:
            break

        predicted_z = tin_surf(list(zip(cand_x, cand_y)))
        residuals = cand_z - predicted_z
        new_ground = np.abs(residuals) < TIN_TOLERANCE

        if np.sum(new_ground) == 0:
            break

        full_indices = np.arange(len(valid_z))
        accepted_indices = full_indices[candidate_mask][new_ground]
        is_ground_mask[accepted_indices] = True

    final_dtm = np.full(dtm_raw_grid.shape, np.inf)
    final_dtm[valid_y[is_ground_mask], valid_x[is_ground_mask]] = valid_z[is_ground_mask]
    return final_dtm


def generate_dtm_grid(las_file, width, height, resolution, bounds, progress_callback=None):
    min_x, max_y = bounds
    dtm_class2 = np.full((height, width), np.inf)
    dtm_raw_min = np.full((height, width), np.inf)
    has_class_2 = False

    total_points = las_file.header.point_count
    points_processed = 0

    if progress_callback:
        progress_callback(1, "Scanning Ground Points...")

    for points in las_file.chunk_iterator(utils.CHUNK_SIZE):
        x = points.x
        y = points.y
        z = points.z
        classification = points.classification

        col_indices = np.clip(((x - min_x) / resolution).astype(int), 0, width - 1)
        row_indices = np.clip(((max_y - y) / resolution).astype(int), 0, height - 1)
        flat_indices = row_indices * width + col_indices

        np.minimum.at(dtm_raw_min.ravel(), flat_indices, z)

        ground_mask = classification == 2
        if np.any(ground_mask):
            has_class_2 = True
            np.minimum.at(dtm_class2.ravel(), flat_indices[ground_mask], z[ground_mask])

        points_processed += len(x)
        if progress_callback:
            pct = (points_processed / total_points) * 45
            progress_callback(pct, "Scanning Ground Points...")

    if progress_callback:
        progress_callback(46, "Interpolating Terrain Model...")

    if has_class_2:
        dtm_grid = dtm_class2
        mask_valid = dtm_grid != np.inf
        dtm_grid[~mask_valid] = utils.DEFAULT_NODATA
        dtm_final = fillnodata(dtm_grid, mask=mask_valid, max_search_distance=100.0)
    else:
        valid_mask = dtm_raw_min != np.inf
        if not np.any(valid_mask):
            return None, False

        tin_ground_grid = perform_tin_densification(dtm_raw_min, resolution, MORPH_SEARCH_METERS)

        mask_tin_valid = tin_ground_grid != np.inf
        if not np.any(mask_tin_valid):
            tin_ground_grid = dtm_raw_min
            mask_tin_valid = valid_mask

        tin_ground_grid[~mask_tin_valid] = utils.DEFAULT_NODATA
        dtm_final = fillnodata(tin_ground_grid, mask=mask_tin_valid, max_search_distance=200.0)
        dtm_final = gaussian_filter(dtm_final, sigma=1)

    return dtm_final, has_class_2
