"""Match one set of points to another in space and time.

The Python counterpart of datamatch's ``matchData()``: a spatiotemporal
nearest-neighbour join between two tables that carry coordinates and
``YEAR``/``MONTH``/``DAY`` columns. Neither side has to be species
observations or environmental data — stations against a covariate grid, tag
positions against a model field, one gridded product against another.

The contract, carried over from the R version:

- One row out per row of ``dat``, in the same order, whatever happens. A
  period ``source`` does not cover gives NaN for its columns and a warning
  naming the periods, rather than dropping rows — a silent change in row
  count is a worse outcome than a visible gap.
- ``dat`` keeps its own columns. A ``source`` column that collides with a
  name already in ``dat`` is suffixed ``.matched``.
- Each joined column gets a companion ``<var>_source`` naming where it came
  from, so a table with several sources chained onto it still says which
  produced what.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

_TIME_COLUMNS = ("YEAR", "MONTH", "DAY", "HOUR")

# Day-of-year columns are never a candidate for anything: "yearday" begins
# with "year" and would otherwise be taken as the year itself. The value is an
# ordinal day, so every row would land in a period no source covers.
_DAY_OF_YEAR_NAMES = frozenset(
    ["yearday", "dayofyear", "day_of_year", "jday", "julianday", "julian_day", "doy"]
)

_RESOLUTION_KEYS = {
    "day": ["YEAR", "MONTH", "DAY"],
    "month": ["YEAR", "MONTH"],
    "year": ["YEAR"],
}


def match_data(
    dat: pd.DataFrame,
    source: pd.DataFrame,
    temporal_resolution: str = "auto",
    record_source: bool = True,
) -> pd.DataFrame:
    """Join each row of ``dat`` to the nearest ``source`` point in its period.

    Parameters
    ----------
    dat:
        The points to add columns to. Needs longitude/latitude columns
        (recognised by prefix: ``lon``/``lat``, or ``x``/``y``), plus year
        and month columns, and a day column when matching daily. Columns
        whose names *begin* with those words are recognised, whatever their
        case, so ``Year`` and ``month_utc`` work but ``obs_month`` does not.
    source:
        The points to take values from — what ``access_copernicus`` returns:
        ``x``/``y`` coordinates, variable columns, and time columns.
    temporal_resolution:
        ``"auto"`` (the default) uses the step the access function recorded
        in ``source.attrs["step"]``, or infers it from the time steps
        present. Otherwise one of ``"day"``, ``"month"``, ``"year"``.
    record_source:
        Add a ``<var>_source`` column per joined column, naming the source,
        when ``source`` carries the stamp an access function leaves.

    Returns
    -------
    pandas.DataFrame
        ``dat`` with ``source``'s columns joined on, one row per input row,
        in the input order.
    """
    if temporal_resolution == "auto":
        temporal_resolution = detect_temporal_resolution(source)
    if temporal_resolution not in _RESOLUTION_KEYS:
        raise ValueError(
            f"`temporal_resolution` must be 'auto' or one of "
            f"{sorted(_RESOLUTION_KEYS)}, not {temporal_resolution!r}."
        )
    match_keys = _RESOLUTION_KEYS[temporal_resolution]

    dat = standardize_time_columns(dat.copy(), match_keys)
    dat_x, dat_y = _coordinate_columns(dat, "dat")
    src_x, src_y = _coordinate_columns(source, "source")

    source_vars = [
        c for c in source.columns
        if c not in (*_TIME_COLUMNS, src_x, src_y)
    ]

    # Give a source column that shares a name with one in `dat` an explicit
    # ".matched" suffix, so nothing of dat's is overwritten or renamed.
    collisions = [c for c in source_vars if c in dat.columns]
    if collisions:
        renames = {c: f"{c}.matched" for c in collisions}
        source = source.rename(columns=renames)
        source_vars = [renames.get(c, c) for c in source_vars]

    out = dat.reset_index(drop=True)
    for v in source_vars:
        out[v] = np.nan

    src_periods = source.groupby(match_keys, sort=False)
    available = set(src_periods.groups)
    unmatched: list[str] = []

    for period, rows_idx in out.groupby(match_keys, sort=False).groups.items():
        key = period if isinstance(period, tuple) else (period,)
        if key not in available:
            unmatched.append("-".join(str(k) for k in key))
            continue
        src = src_periods.get_group(period if len(key) > 1 else key[0])
        tree = cKDTree(np.column_stack([src[src_x], src[src_y]]))
        _, nearest = tree.query(
            np.column_stack([out.loc[rows_idx, dat_x], out.loc[rows_idx, dat_y]])
        )
        for v in source_vars:
            out.loc[rows_idx, v] = src[v].to_numpy()[nearest]

    if unmatched:
        shown = ", ".join(unmatched[:5]) + (", ..." if len(unmatched) > 5 else "")
        warnings.warn(
            f"No data in `source` for {len(unmatched)} period(s); matched "
            f"columns set to NaN for: {shown}",
            stacklevel=2,
        )

    provenance = source.attrs.get("source")
    if record_source and provenance is not None:
        for v in source_vars:
            out[f"{v}_source"] = provenance

    return out


def detect_temporal_resolution(source: pd.DataFrame) -> str:
    """Infer the temporal resolution of ``source``'s time steps.

    The step the access function recorded is trusted over inspection: a
    ``dates`` request of one date per month — survey dates, typically — is
    indistinguishable from monthly data by looking, and guessing monthly
    there would quietly ignore the day.

    Otherwise: more than one day within any month means daily, more than one
    month within any year means monthly. Annual is inferred only with
    positive evidence — several years, each stamped on the same single
    month. Everything else falls back to monthly, because guessing too
    coarse silently matches the wrong time step, whereas guessing too fine
    leaves rows unmatched and warns.
    """
    recorded = source.attrs.get("step")
    if recorded in _RESOLUTION_KEYS:
        return recorded

    have = [c for c in ("YEAR", "MONTH", "DAY") if c in source.columns]
    times = source[have].drop_duplicates()
    if {"YEAR", "MONTH", "DAY"} <= set(have):
        if (times.groupby(["YEAR", "MONTH"])["DAY"].nunique() > 1).any():
            return "day"
    if {"YEAR", "MONTH"} <= set(have):
        if (times.groupby("YEAR")["MONTH"].nunique() > 1).any():
            return "month"
        if times["YEAR"].nunique() > 1 and times["MONTH"].nunique() == 1:
            return "year"
    return "month"


def standardize_time_columns(dat: pd.DataFrame, match_keys) -> pd.DataFrame:
    """Rename ``dat``'s time columns to YEAR/MONTH/DAY.

    Only the columns the requested match keys need are required, so monthly
    matching works on data that has no day column at all. Recognition is by
    prefix — ``Year``, ``month_utc`` — and an ambiguous or missing column is
    an error naming the candidates, so nothing has to be guessed at.
    """
    for key in match_keys:
        if key in dat.columns:
            continue
        prefix = key.lower()
        candidates = [
            c for c in dat.columns
            if c.lower().startswith(prefix) and c.lower() not in _DAY_OF_YEAR_NAMES
        ]
        # An exact match wins over a mere prefix match, so a dataset carrying
        # both "day" and "day_night" resolves to "day".
        exact = [c for c in candidates if c.lower() == prefix]
        if len(exact) == 1:
            candidates = exact
        if len(candidates) == 0:
            near = [c for c in dat.columns if prefix in c.lower()]
            hint = (
                f" These have a similar name but were not used: "
                f"{', '.join(near)}. Rename the intended one to '{key}'."
                if near else ""
            )
            raise ValueError(
                f"`dat` has no column for '{key}' (looked for names starting "
                f"with '{prefix}'). It is required to match at this temporal "
                f"resolution.{hint}"
            )
        if len(candidates) > 1:
            raise ValueError(
                f"`dat` has multiple candidate '{key}' columns: "
                f"{', '.join(candidates)}. Rename the intended one to '{key}'."
            )
        dat = dat.rename(columns={candidates[0]: key})
    return dat


def _coordinate_columns(df: pd.DataFrame, name: str) -> tuple[str, str]:
    """Find the longitude and latitude columns of one side of a match."""
    cols = {c.lower(): c for c in df.columns}
    for x_key, y_key in (("x", "y"), ("lon", "lat"), ("longitude", "latitude")):
        x = cols.get(x_key) or next(
            (c for lc, c in cols.items() if lc.startswith(x_key)), None
        )
        y = cols.get(y_key) or next(
            (c for lc, c in cols.items() if lc.startswith(y_key)), None
        )
        if x is not None and y is not None:
            return x, y
    raise ValueError(
        f"`{name}` has no recognisable coordinate columns. Looked for x/y, "
        f"lon/lat, or longitude/latitude among: {', '.join(df.columns)}."
    )
