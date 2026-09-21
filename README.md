# pydatamatch

[![CI](https://github.com/chross22/pydatamatch/actions/workflows/ci.yml/badge.svg)](https://github.com/chross22/pydatamatch/actions/workflows/ci.yml)

Match point observations to ocean model and satellite fields in space and
time. The Python counterpart of the R package
[datamatch](https://github.com/chross22/datamatch), starting with the
Copernicus Marine Service accessor.

The workflow is two calls: fetch an environmental field, then join it onto
your observations by nearest grid cell within the same time period.

```python
import pydatamatch as dm

env = dm.access_copernicus(
    variables=["SST", "SSS", "MLD"],
    years=range(2003, 2018), months=range(1, 13),
    bounding_box={"xmin": -76, "xmax": -65, "ymin": 35, "ymax": 45},
)

matched = dm.match_data(observations, env)

# Chains, so several sources land on one table
matched = dm.match_data(matched, chlorophyll)
```

`observations` is any `pandas.DataFrame` with longitude/latitude columns and
year/month (and day, for daily matching) columns. Column names are recognised
by prefix — `Year`, `month_utc` — and never guessed: an ambiguous or missing
name is an error naming the candidates.

## Installation

```bash
pip install git+https://github.com/chross22/pydatamatch
```

Copernicus downloads need a (free) Copernicus Marine account. Log in once and
the credentials are stored:

```bash
copernicusmarine login
```

## Variables

Variables are requested by short catalog names rather than Copernicus codes —
`"SST"` rather than `thetao` — and the names carry through to the result's
columns. `pydatamatch.copernicus_variables()` lists the catalog: physics
(`SST`, `SSS`, `BOTT`, `UO`, `VO`, `SSH`, `MLD`, `SIC`), satellite ocean
colour (`CHL`, `PP`, `DIATO`, `DINO`), biogeochemistry (`NO3`, `PO4`, `O2`,
`PH`, `CHL_MODEL`, `NPP_MODEL`) and wind (`WSPD`, `UWND`, `VWND`, `TAUX`,
`TAUY`, `TAU`). Raw Copernicus codes pass through for anything the catalog
does not cover, with `product_id`/`dataset_id` given explicitly.

Because the catalog knows which product and dataset holds each variable,
those identifiers can usually be omitted. Variables from different datasets
cannot share a request and are refused before anything is downloaded; fetch
them separately and chain `match_data`.

## Monthly, daily, and exact dates

`frequency="monthly"` (the default) fetches monthly means. `frequency="daily"`
fetches the daily datasets — note the cost: three months of daily data is ~91
downloads rather than 3. When matching daily data to observations, name the
exact dates instead, taken from the observations themselves:

```python
env = dm.access_copernicus(
    variables=["SST"],
    dates=observations["date"].unique(),
    bounding_box=bb,
)
```

`YYYYMMDD`, `YYYY-MM-DD`, and `date` objects are all accepted. A date the
calendar does not have (`20150230`) is an error naming it, never a silently
dropped request, and dates that have not happened yet are refused before
anything is fetched.

## Caching

Every time step is one NetCDF file in the cache (`~/.cache/pydatamatch`, or
`$PYDATAMATCH_CACHE`). Re-running a call downloads only what is missing, and
a partially failed fetch keeps its successes — the error names each failed
step, and re-running retries only those.

## Matching guarantees

`match_data` preserves the contract of the R original:

- **One row out per row in, in the same order.** A period the source does not
  cover gives NaN and a warning naming the periods, never a dropped row.
- **Your columns are never overwritten.** A source column colliding with one
  of yours is suffixed `.matched`.
- **Provenance travels with the values.** Each joined column gets a
  `<var>_source` companion (e.g. `"copernicus:cmems_mod_glo_phy_my_0.083deg_P1M-m"`),
  so a table with several sources chained onto it still says which produced
  what. Pass `record_source=False` for the narrower table.

## Not yet ported

Relative to the R package, this port does not yet have: the other accessors
(ERDDAP, FVCOM, HYCOM, CCMP), hourly wind, forecast mode, derived bottom
salinity (`BOTS`), bathymetry and climate indices, regridding/retiming, and
gap filling. The Copernicus catalog, caching, date handling, and the
spatiotemporal join are feature-equivalent.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests are offline: nothing in the suite touches the Copernicus API.
