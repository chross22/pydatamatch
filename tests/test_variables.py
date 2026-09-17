import pytest

from pydatamatch.variables import (
    copernicus_variables,
    infer_dataset,
    resolve_variables,
)


def test_catalog_names_resolve_to_codes():
    codes, names = resolve_variables(["SST", "MLD", "SSH"])
    assert codes == ["thetao", "mlotst", "zos"]
    assert names == ["SST", "MLD", "SSH"]


def test_raw_codes_pass_through():
    codes, names = resolve_variables(["thetao", "SST"])
    assert codes == ["thetao", "thetao"]
    assert names == ["thetao", "SST"]


def test_dataset_inferred_for_physics_variables():
    product, dataset = infer_dataset(["SST", "SSS", "MLD"])
    assert product == "GLOBAL_MULTIYEAR_PHY_001_030"
    assert dataset.endswith("P1M-m")


def test_daily_frequency_selects_daily_dataset():
    _, dataset = infer_dataset(["SST"], frequency="daily")
    assert "P1D" in dataset


def test_daily_chl_is_the_gapfree_dataset():
    _, dataset = infer_dataset(["CHL"], frequency="daily")
    assert "gapfree" in dataset


def test_monthly_only_variable_refused_daily():
    with pytest.raises(ValueError, match="PH"):
        infer_dataset(["PH"], frequency="daily")


def test_mixed_datasets_refused_before_download():
    with pytest.raises(ValueError, match="different datasets"):
        infer_dataset(["SST", "NO3"])


def test_unknown_variable_needs_explicit_ids():
    with pytest.raises(ValueError, match="catalog"):
        infer_dataset(["not_a_variable"])


def test_catalog_entries_are_complete():
    for name, entry in copernicus_variables().items():
        assert entry.variable, name
        assert entry.product_id, name
        assert entry.dataset_id, name
        assert entry.units, name
