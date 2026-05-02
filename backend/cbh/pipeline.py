# This file handles high-level orchestration of each of the other files
# Possible final function:
# def generate_cbh(
#     las_file,
#     dtm_grid,
#     canopy_height_grid,
#     canopy_cover_grid,
#     bounds,
#     resolution,
#     model=None,
#     mode="proxy"
# ):
# ...
# Modes: 
# mode="proxy"   → output rule-based CBH
# mode="predict" → output ML-predicted CBH
# mode="train"   → generate training table
# Data products:
# Minimum:
# # cbh_proxy.tif
# # cbh_predicted.tif
# # cbh_features.parquet/csv
# # valid_mask.tif
# Useful diagnostics:
# return_count.tif
# profile_confidence.tif
# canopy_cover.tif
# canopy_height.tif


