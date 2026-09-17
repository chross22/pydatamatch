"""The Copernicus variable catalog and name resolution.

Ports datamatch's copernicus_variables() and resolve_variables(). Copernicus
codes are terse and easy to misremember (``thetao`` for temperature,
``mlotst`` for mixed layer depth, ``zos`` for sea surface height), so
variables are requested by short catalog names — ``SST``, ``CHL``, ``MLD`` —
and those names carry through to the result's columns. Raw codes still work,
for anything the catalog does not cover.

Because the catalog knows which product and dataset holds each variable,
``product_id`` and ``dataset_id`` can usually be omitted at the call site.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Variable:
    """One catalog entry: a short name mapped to a Copernicus variable."""

    variable: str
    label: str
    units: str
    product_id: str
    dataset_id: str
    daily_dataset_id: str | None = None
    hourly_dataset_id: str | None = None
    description: str = ""
    derived: dict = field(default_factory=dict)


_PHY_PRODUCT = "GLOBAL_MULTIYEAR_PHY_001_030"
_PHY_MONTHLY = "cmems_mod_glo_phy_my_0.083deg_P1M-m"
_PHY_DAILY = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
_BGC_PRODUCT = "GLOBAL_MULTIYEAR_BGC_001_029"
_BGC_MONTHLY = "cmems_mod_glo_bgc_my_0.25deg_P1M-m"
_BGC_DAILY = "cmems_mod_glo_bgc_my_0.25deg_P1D-m"
# Copernicus-GlobColour: satellite ocean colour rather than a model. Higher
# resolution (4 km vs 0.25 degrees) and observed rather than simulated, but
# surface-only and gappy under cloud. Daily ocean colour is the gap-free
# interpolated field, not the monthly composite at a finer step.
_OC_PRODUCT = "OCEANCOLOUR_GLO_BGC_L4_MY_009_104"
_OC_PLANKTON = "cmems_obs-oc_glo_bgc-plankton_my_l4-multi-4km_P1M"
_OC_PP = "cmems_obs-oc_glo_bgc-pp_my_l4-multi-4km_P1M"
_OC_PLANKTON_DAILY = "cmems_obs-oc_glo_bgc-plankton_my_l4-gapfree-multi-4km_P1D"
# Sea surface wind: the atmosphere forcing the ocean rather than the ocean
# itself, from its own product on its own grid. Monthly or hourly, never daily.
_WIND_PRODUCT = "WIND_GLO_PHY_CLIMATE_L4_MY_012_003"
_WIND_MONTHLY = "cmems_obs-wind_glo_phy_my_l4_P1M"
_WIND_HOURLY_PRODUCT = "WIND_GLO_PHY_L4_MY_012_006"
_WIND_HOURLY = "cmems_obs-wind_glo_phy_my_l4_0.125deg_PT1H"


def _phy(code, label, units, description, derived=None):
    return Variable(code, label, units, _PHY_PRODUCT, _PHY_MONTHLY,
                    daily_dataset_id=_PHY_DAILY, description=description,
                    derived=derived or {})


def _bgc(code, label, units, description, daily=_BGC_DAILY):
    return Variable(code, label, units, _BGC_PRODUCT, _BGC_MONTHLY,
                    daily_dataset_id=daily, description=description)


def _oc(code, label, units, description, dataset_id=_OC_PLANKTON, daily=None):
    return Variable(code, label, units, _OC_PRODUCT, dataset_id,
                    daily_dataset_id=daily, description=description)


def _wind(code, label, units, description, hourly=_WIND_HOURLY):
    return Variable(code, label, units, _WIND_PRODUCT, _WIND_MONTHLY,
                    hourly_dataset_id=hourly, description=description)


COPERNICUS_VARIABLES: dict[str, Variable] = {
    "SST": _phy("thetao", "Sea surface temperature", "degrees C",
                "Sea water potential temperature at the surface."),
    "SSS": _phy("so", "Sea surface salinity", "PSU",
                "Sea water salinity at the surface."),
    "BOTT": _phy("bottomT", "Bottom temperature", "degrees C",
                 "Sea water potential temperature at the sea floor."),
    # GLORYS12V1 publishes temperature at the sea floor but not salinity, so
    # BOTS is derived from the three-dimensional salinity field: the deepest
    # wet model level in each cell. Not yet implemented here; see the roadmap.
    "BOTS": _phy("so", "Bottom salinity", "PSU",
                 "Sea water salinity in the deepest wet model level of each "
                 "cell, derived from the three-dimensional salinity field.",
                 derived={"from": "so", "how": "deepest_level"}),
    "UO": _phy("uo", "Eastward current velocity", "m/s",
               "Eastward component of sea water velocity."),
    "VO": _phy("vo", "Northward current velocity", "m/s",
               "Northward component of sea water velocity."),
    "SSH": _phy("zos", "Sea surface height", "m",
                "Sea surface height above geoid. A proxy for mesoscale "
                "circulation features."),
    "MLD": _phy("mlotst", "Mixed layer depth", "m",
                "Ocean mixed layer thickness by a sigma-theta criterion."),
    "SIC": _phy("siconc", "Sea ice concentration", "fraction",
                "Fraction of the cell covered by sea ice."),
    "CHL": _oc("CHL", "Chlorophyll-a concentration (satellite)", "mg/m3",
               "Chlorophyll-a from Copernicus-GlobColour. Surface only; the "
               "daily field is the gap-free interpolated one.",
               daily=_OC_PLANKTON_DAILY),
    "PP": _oc("PP", "Primary production (satellite)", "mg/m2/day",
              "Depth-integrated primary production from Copernicus-GlobColour. "
              "Monthly only.", dataset_id=_OC_PP),
    "DIATO": _oc("DIATO", "Diatom chlorophyll-a concentration", "mg/m3",
                 "Diatom chlorophyll from Copernicus-GlobColour. Monthly only."),
    "DINO": _oc("DINO", "Dinophyte chlorophyll-a concentration", "mg/m3",
                "Dinoflagellate chlorophyll from Copernicus-GlobColour. "
                "Monthly only."),
    "NO3": _bgc("no3", "Nitrate concentration", "mmol/m3",
                "Mole concentration of nitrate, a limiting nutrient."),
    "PO4": _bgc("po4", "Phosphate concentration", "mmol/m3",
                "Mole concentration of phosphate."),
    "O2": _bgc("o2", "Dissolved oxygen", "mmol/m3",
               "Mole concentration of dissolved molecular oxygen."),
    # The daily biogeochemical reanalysis omits ph; only the monthly mean has it.
    "PH": _bgc("ph", "pH", "unitless",
               "Sea water pH on the total scale. Monthly only.", daily=None),
    "CHL_MODEL": _bgc("chl", "Chlorophyll-a concentration (model)", "mg/m3",
                      "Chlorophyll-a from the biogeochemistry reanalysis. "
                      "Coarser than satellite CHL but gap-free."),
    "NPP_MODEL": _bgc("nppv", "Net primary production (model)", "mg/m3/day",
                      "Net primary production from the biogeochemistry "
                      "reanalysis. Volumetric, unlike the satellite PP."),
    # The hourly wind product carries the vector components but not the
    # magnitudes, which it leaves to be computed from them.
    "WSPD": _wind("wind_speed", "Wind speed", "m/s",
                  "Scalar wind speed at 10 m. Monthly only.", hourly=None),
    "UWND": _wind("eastward_wind", "Eastward wind", "m/s",
                  "Eastward component of wind velocity at 10 m."),
    "VWND": _wind("northward_wind", "Northward wind", "m/s",
                  "Northward component of wind velocity at 10 m."),
    "TAUX": _wind("eastward_stress", "Eastward wind stress", "N/m2",
                  "Eastward component of the surface downward stress."),
    "TAUY": _wind("northward_stress", "Northward wind stress", "N/m2",
                  "Northward component of the surface downward stress."),
    "TAU": _wind("wind_stress_magnitude", "Wind stress magnitude", "N/m2",
                 "Magnitude of the surface downward stress. Monthly only.",
                 hourly=None),
}


def copernicus_variables() -> dict[str, Variable]:
    """The catalog of named Copernicus variables, one entry per short name."""
    return dict(COPERNICUS_VARIABLES)


def resolve_variables(names) -> tuple[list[str], list[str]]:
    """Resolve requested names into (codes to send, column names to return).

    Catalog names ("SST") resolve to their Copernicus codes ("thetao");
    anything outside the catalog is passed through as a raw code, since
    Copernicus serves far more than the catalog covers — but a typo looks
    identical to a real code, so the passthrough is the caller's risk.
    """
    if isinstance(names, str):
        names = [names]
    codes, out_names = [], []
    for name in names:
        entry = COPERNICUS_VARIABLES.get(name)
        codes.append(entry.variable if entry else name)
        out_names.append(name)
    return codes, out_names


def infer_dataset(names, frequency: str = "monthly") -> tuple[str, str]:
    """Infer the (product_id, dataset_id) that serves every requested variable.

    Variables from different datasets cannot be fetched in one request, and
    mixing them is refused before anything is downloaded rather than failing
    obscurely at the API.
    """
    if isinstance(names, str):
        names = [names]
    unknown = [n for n in names if n not in COPERNICUS_VARIABLES]
    if unknown:
        raise ValueError(
            f"Not in the catalog: {', '.join(unknown)}. Pass product_id and "
            "dataset_id explicitly to fetch raw Copernicus codes."
        )

    pairs = set()
    for n in names:
        entry = COPERNICUS_VARIABLES[n]
        if frequency == "daily":
            if entry.daily_dataset_id is None:
                raise ValueError(
                    f"{n} has no daily dataset - Copernicus publishes it "
                    "monthly only. Drop it from a daily request."
                )
            pairs.add((entry.product_id, entry.daily_dataset_id))
        elif frequency == "hourly":
            if entry.hourly_dataset_id is None:
                raise ValueError(
                    f"{n} has no hourly dataset. Only the wind components "
                    "(UWND, VWND, TAUX, TAUY) are published hourly."
                )
            pairs.add((_WIND_HOURLY_PRODUCT, entry.hourly_dataset_id))
        else:
            pairs.add((entry.product_id, entry.dataset_id))

    if len(pairs) > 1:
        datasets = ", ".join(sorted(d for _, d in pairs))
        raise ValueError(
            "The requested variables live in different datasets and cannot "
            f"be fetched in one request: {datasets}. Fetch them in separate "
            "calls and chain match_data()."
        )
    return next(iter(pairs))
