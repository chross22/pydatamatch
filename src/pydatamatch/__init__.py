"""pydatamatch: match observations to ocean data in space and time.

The Python counterpart of the R package `datamatch`, starting with the
Copernicus Marine Service accessor. The workflow is two calls:

    import pydatamatch as dm

    env = dm.access_copernicus(
        variables=["SST", "MLD"],
        years=range(2010, 2015), months=range(1, 13),
        bounding_box={"xmin": -76, "xmax": -65, "ymin": 35, "ymax": 45},
    )
    matched = dm.match_data(observations, env)
"""

from .copernicus import access_copernicus
from .match import match_data
from .variables import copernicus_variables

__all__ = ["access_copernicus", "match_data", "copernicus_variables"]
__version__ = "0.1.0"
