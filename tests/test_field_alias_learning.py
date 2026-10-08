"""Alias learning must work without combined photometry and count stars once."""
import pandas as pd
import pytest
from groove.periods import aliases, settings as S


def rows(n=8, bands=("o", "c"), period=7.321):
    return pd.DataFrame([
        {"source_id": str(3216489845356186500 + i), "series": band,
         "ra_deg": 12.0, "dec_deg": 22.0, "ls_top_periods_days": str(period)}
        for i in range(n) for band in bands
    ])


def counts(inventory):
    return inventory[["alias_period_days", "n_stars_in_field", "n_stars_hit", "hit_fraction"]]


def test_default_learns_oc_and_counts_each_star_once(monkeypatch):
    monkeypatch.setattr(S, "ALIAS_LEARNING_SERIES", "auto")
    inventory = aliases.build_field_alias_inventory(rows())
    assert len(inventory) == 1
    assert inventory.iloc[0].n_stars_in_field == 8
    assert inventory.iloc[0].n_stars_hit == 8
    assert inventory.iloc[0].hit_fraction == 1
    assert aliases.field_alias_match(7.321, 12, 22, inventory)["field_alias_hit"]


def test_band_rows_cannot_satisfy_minimum_star_count():
    assert aliases.build_field_alias_inventory(rows(4), "auto").empty


@pytest.mark.parametrize("band", ["o", "c"])
def test_auto_single_band_matches_explicit(band):
    data = rows(bands=(band,))
    pd.testing.assert_frame_equal(counts(aliases.build_field_alias_inventory(data, "auto")),
                                  counts(aliases.build_field_alias_inventory(data, band)))


def test_auto_pools_both_bands_without_inflating_hits():
    data = rows()
    data.loc[data.series.eq("o"), "ls_top_periods_days"] = "11.731"
    inventory = aliases.build_field_alias_inventory(data, "auto")
    assert len(inventory) == 2
    assert set(inventory.n_stars_hit) == {8}
    assert set(inventory.n_stars_in_field) == {8}


def test_combined_references_take_precedence_and_match_legacy():
    reference = rows(bands=("combined",), period=11.731)
    mixed = pd.concat([rows(), reference], ignore_index=True)
    pd.testing.assert_frame_equal(counts(aliases.build_field_alias_inventory(mixed, "auto")),
                                  counts(aliases.build_field_alias_inventory(reference, "combined")))


def test_duplicate_reference_rows_do_not_count_twice():
    data = rows()
    inventory = aliases.build_field_alias_inventory(pd.concat([data, data]), "auto")
    assert inventory.iloc[0].n_stars_in_field == inventory.iloc[0].n_stars_hit == 8


def test_universal_aliases_still_excluded():
    assert aliases.build_field_alias_inventory(rows(period=1.0), "auto").empty


def test_explicit_missing_band_warns(capsys):
    assert aliases.build_field_alias_inventory(rows(), "combined").empty
    assert "No combined rows" in capsys.readouterr().out


def test_invalid_series_rejected():
    with pytest.raises(ValueError, match="alias_learning_series"):
        aliases.build_field_alias_inventory(rows(), "unknown")


def test_reference_source_ids_are_preserved(tmp_path, monkeypatch):
    reference = tmp_path / "reference.csv"
    data = rows(bands=("combined",))
    data.loc[0, "source_id"] = None
    data.to_csv(reference, index=False)
    monkeypatch.setattr(S, "REFERENCE_SUMMARY_CSVS", [reference])
    loaded = aliases.load_reference_summaries()
    assert loaded.source_id.iloc[1] == "3216489845356186501"
