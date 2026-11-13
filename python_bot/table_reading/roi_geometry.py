"""Bounded cache of immutable crop-local geometry, never frames or readings.

Dimensions must belong to the freshly detected table crop, not its host window.
The arithmetic is trivial; this centralizes validity, not a measured speedup.
"""
from dataclasses import dataclass
from functools import lru_cache

BLUE_COLORED_V1 = 'BLUE_COLORED_V1'

@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def slices(self):
        return slice(self.top,self.bottom),slice(self.left,self.right)

    def translated(self,x,y):
        """Translate local diagnostics without caching window position."""
        return Rect(self.left+x,self.top+y,self.right+x,self.bottom+y)

@lru_cache(maxsize=128)
def _cached_roi(width,height,region,layout):
    # Keep profiles explicit: a different skin must not silently reuse this ROI.
    if layout != BLUE_COLORED_V1 or region != 'board':
        raise ValueError('Unsupported layout or region')
    return Rect(round(width*.17),round(height*.35),round(width*.85),round(height*.50))

def get_roi(width,height,region='board',layout=BLUE_COLORED_V1):
    """Return bounds using the current crop dimensions; empty tiny ROIs allowed."""
    if type(width) is not int or type(height) is not int or width<=0 or height<=0:
        raise ValueError('Crop dimensions must be positive integers')
    return _cached_roi(width,height,region,layout)

def cache_info():
    return _cached_roi.cache_info()

def clear_cache():
    _cached_roi.cache_clear()
