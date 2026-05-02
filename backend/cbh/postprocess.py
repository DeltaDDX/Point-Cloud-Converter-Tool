# This file applies constraints such as:
# cbh[cbh < 0] = 0
# cbh[cbh < MIN_CANOPY_HEIGHT] = 0
# cbh[canopy_cover < COVER_THRESHOLD] = 0
# cbh[canopy_height < cbh] = canopy_height