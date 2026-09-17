"""Access environmental data from the Copernicus Marine Service.

The Python counterpart of datamatch's ``accessCopernicus()``. Where the R
package shells out to the ``copernicusmarine`` command-line client, this one
imports the official Python package directly — same service, one less moving
part. Credentials are the ones ``copernicusmarine login`` stores.

Each time step is downloaded once into the cache (see ``_cache``) and read
locally after that, so re-running a call retries only what failed.
"""

from __future__ import annotations

import calendar
import datetime as _dt
import warnings
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ._cache import cache_file
from ._dates import parse_dates, stop_if_future
from .variables import COPERNICUS_VARIABLES, infer_dataset, resolve_variables

_FREQUENCIES = ("monthly", "daily")


def access_copernicus(
    variables,
    years=None,
    months=None,
    bounding_box: dict | None = None,
    dates=None,
    frequency: str | None = None,
    depth=(0.0, 1.0),
    product_id: str | None = None,
    dataset_id: str | None = None,
    n_workers: int = 4,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Fetch a Copernicus dataset over a box and time range as a DataFrame.

    Parameters
    ----------
    variables:
        Names from the catalog (``"SST"``, ``"CHL"``, ``"MLD"``), raw
        Copernicus codes, or a mixture. Catalog names carry through to the
        result, so a request for ``"SST"`` returns a column called ``SST``
        rather than ``thetao``.
    years, months:
        Whole months to fetch. Required unless ``dates`` names the time
        steps itself.
    bounding_box:
        ``{"xmin": ..., "xmax": ..., "ymin": ..., "ymax": ...}`` in degrees.
    dates:
        Exact dates to fetch — YYYYMMDD, YYYY-MM-DD, or date objects.
        Implies ``frequency="daily"`` and replaces ``years``/``months``.
        This is the argument to use when matching daily data to
        observations: take the dates from the observations themselves.
    frequency:
        ``"monthly"`` (the default) or ``"daily"``. Note the cost of daily:
        three months is ~91 downloads rather than 3.
    depth:
        ``(min, max)`` in metres. The default selects the surface level.
    product_id, dataset_id:
        Optional when every requested variable is in the catalog, which
        knows where each one lives.
    n_workers:
        Concurrent downloads. The limit is the service, not local cores, so
        keep it modest.
    overwrite:
        Re-download steps already in the cache.

    Returns
    -------
    pandas.DataFrame
        One row per grid cell and time step: ``x``, ``y``, one column per
        variable, and ``YEAR``/``MONTH``/``DAY``. ``df.attrs`` records the
        temporal ``step`` and the ``source`` for provenance, which
        ``match_data`` reads.
    """
    if isinstance(variables, str):
        variables = [variables]
    if bounding_box is None:
        raise ValueError("`bounding_box` is required: a dict with xmin, xmax, ymin, ymax.")
    missing_keys = {"xmin", "xmax", "ymin", "ymax"} - set(bounding_box)
    if missing_keys:
        raise ValueError(f"`bounding_box` is missing: {', '.join(sorted(missing_keys))}")

    for name in variables:
        entry = COPERNICUS_VARIABLES.get(name)
        if entry is not None and entry.derived:
            raise NotImplementedError(
                f"{name} is a derived variable (deepest wet level of "
                f"'{entry.derived['from']}'), which this port does not "
                "compute yet. Fetch the column with the raw code and derive "
                "it yourself, or use the R package for now."
            )

    frequency_given = frequency is not None
    if frequency_given and frequency not in _FREQUENCIES:
        raise ValueError(f"`frequency` must be one of {_FREQUENCIES}.")

    if dates is not None:
        dates = parse_dates(dates)
        if years is not None or months is not None:
            raise ValueError(
                "`dates` already names which time steps to fetch, so `years` "
                "and `months` are not used with it."
            )
        if frequency_given and frequency == "monthly":
            raise ValueError(
                "`dates` names days to fetch, but frequency='monthly' was "
                "given. A monthly mean has one field per month, so a date "
                "within it selects nothing."
            )
        frequency = "daily"
        stop_if_future(dates, "Copernicus")
    else:
        if years is None or months is None:
            raise ValueError(
                "`years` and `months` are required, unless `dates` names the "
                "exact dates to fetch."
            )
        frequency = frequency or "monthly"
        years = [years] if isinstance(years, int) else list(years)
        months = [months] if isinstance(months, int) else list(months)
        latest = _dt.date(max(years), max(months), 1)
        stop_if_future([latest], "Copernicus")

    codes, out_names = resolve_variables(variables)
    if product_id is None or dataset_id is None:
        inferred_product, inferred_dataset = infer_dataset(variables, frequency=frequency)
        product_id = product_id or inferred_product
        dataset_id = dataset_id or inferred_dataset

    daily = "_P1D" in dataset_id or frequency == "daily"

    # One work item per time step: its date and its cache path, resolved once
    # so the download and read phases agree on where the file is.
    if dates is not None:
        step_dates = dates
    elif daily:
        step_dates = [
            _dt.date(y, m, d)
            for y in years for m in months
            for d in range(1, calendar.monthrange(y, m)[1] + 1)
        ]
    else:
        step_dates = [_dt.date(y, m, 1) for y in years for m in months]

    items = [
        {"time": d, "path": cache_file(dataset_id, d, codes, bounding_box, depth)}
        for d in step_dates
    ]

    needed = [i for i in items if overwrite or not i["path"].exists()]
    if needed:
        _download(needed, dataset_id, codes, bounding_box, depth,
                  daily=daily, n_workers=n_workers)

    frames = [_read_step(i, codes, out_names) for i in items]
    out = pd.concat(frames, ignore_index=True)
    out.attrs["step"] = "day" if daily else "month"
    out.attrs["source"] = f"copernicus:{dataset_id}"
    return out


def _download(items, dataset_id, codes, bounding_box, depth, daily, n_workers):
    """Download the missing steps, a few at a time, collecting every failure.

    A step that fails does not abort the others: every one is attempted, the
    successes stay in the cache, and the error names each failure — so
    re-running the same call retries only those.
    """
    import copernicusmarine  # deferred: only a real fetch needs credentials

    def fetch(item):
        day = item["time"]
        if daily:
            start = _dt.datetime.combine(day, _dt.time.min)
            end = _dt.datetime.combine(day, _dt.time.max)
        else:
            # A monthly mean is one field somewhere in the month, so the
            # window is the whole month.
            last = calendar.monthrange(day.year, day.month)[1]
            start = _dt.datetime(day.year, day.month, 1)
            end = _dt.datetime(day.year, day.month, last, 23, 59, 59)
        try:
            copernicusmarine.subset(
                dataset_id=dataset_id,
                variables=list(codes),
                minimum_longitude=bounding_box["xmin"],
                maximum_longitude=bounding_box["xmax"],
                minimum_latitude=bounding_box["ymin"],
                maximum_latitude=bounding_box["ymax"],
                start_datetime=start,
                end_datetime=end,
                minimum_depth=depth[0],
                maximum_depth=depth[1],
                output_filename=item["path"].name,
                output_directory=str(item["path"].parent),
                overwrite=True,
                disable_progress_bar=True,
            )
            return None
        except Exception as e:  # noqa: BLE001 - reported, not swallowed
            item["path"].unlink(missing_ok=True)  # never cache a truncated file
            return f"  {day.isoformat()}: {e}"

    workers = max(1, min(n_workers, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        failures = [f for f in pool.map(fetch, items) if f is not None]

    if failures:
        raise RuntimeError(
            f"{len(failures)} of {len(items)} time step(s) could not be "
            "downloaded:\n" + "\n".join(failures) +
            "\nThe steps that did succeed are cached, so re-running this "
            "call retries only the failures."
        )


def _read_step(item, codes, out_names) -> pd.DataFrame:
    """Read one cached time step into a flat DataFrame.

    Columns take the names the caller asked for, so requesting "SST" yields
    a column called SST rather than thetao.
    """
    import xarray as xr

    day = item["time"]
    with xr.open_dataset(item["path"]) as ds:
        missing = [c for c in codes if c not in ds.data_vars]
        if missing:
            raise RuntimeError(
                f"The download for {day.isoformat()} did not return: "
                f"{', '.join(missing)}. It contains: "
                f"{', '.join(ds.data_vars)}. That variable may not exist in "
                "this dataset, or may not be served at the requested depth "
                "or date."
            )
        ds = ds[list(codes)]
        # A depth range spanning several model levels would silently multiply
        # the rows; say which levels rather than mislabelling anything.
        if "depth" in ds.dims and ds.sizes["depth"] > 1:
            levels = ", ".join(f"{d:.3f}" for d in ds["depth"].values)
            raise RuntimeError(
                f"The depth range returned several model levels: {levels}. "
                "Request a single level, e.g. depth=(0, 1)."
            )
        df = ds.squeeze(drop=True).to_dataframe().reset_index()

    lon = next((c for c in df.columns if c.lower() in ("longitude", "lon", "x")), None)
    lat = next((c for c in df.columns if c.lower() in ("latitude", "lat", "y")), None)
    if lon is None or lat is None:
        raise RuntimeError(
            f"Could not find longitude/latitude columns in {sorted(df.columns)}."
        )

    df = df.rename(columns={lon: "x", lat: "y", **dict(zip(codes, out_names))})
    df = df[["x", "y", *out_names]]
    # Land and clipped cells hold nothing for any variable; drop them, as the
    # R version does, rather than returning a grid of NA rows.
    df = df.dropna(how="all", subset=out_names).reset_index(drop=True)
    df["YEAR"] = day.year
    df["MONTH"] = day.month
    df["DAY"] = day.day
    return df
