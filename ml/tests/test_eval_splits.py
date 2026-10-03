"""Splits: no shop in two groups, time order respected, held-out pattern unseen."""

import pandas as pd
import pytest

from jachai.eval.splits import assign_split, shop_groups
from jachai.features import build_features
from jachai.features.config import load_thresholds
from jachai.world.world import TRUE_PATTERN


@pytest.fixture(scope="module")
def split_setup(pattern_world):
    thr = load_thresholds()
    # The small world runs 22 Sep - 21 Oct; move the boundaries inside it.
    split = thr.split.model_copy(
        update={
            "train_end": pd.Timestamp("2026-10-08").date(),
            "validation_end": pd.Timestamp("2026-10-14").date(),
        }
    )
    thr = thr.model_copy(
        update={"split": split, "eval": thr.eval.model_copy(update={"warmup_days": 5})}
    )
    pay = build_features(pattern_world.tables, pattern_world.config, thr.features)["payments"]
    split_col = assign_split(pay, pattern_world.tables, pattern_world.config, thr)
    return pattern_world, thr, pay.assign(split=split_col.to_numpy())


def test_every_group_has_rows(split_setup):
    _, _, pay = split_setup
    assert {"train", "validation", "test"} <= set(pay["split"])


def test_no_shop_in_two_groups(split_setup):
    _, _, pay = split_setup
    used = pay[pay["split"] != ""]
    assert (used.groupby("shop_id")["split"].nunique() == 1).all()


def test_time_order(split_setup):
    _, thr, pay = split_setup
    by = pay[pay["split"] != ""].groupby("split")["ts"]
    assert by.max()["train"] < by.min()["validation"]
    assert by.max()["validation"] < by.min()["test"]


def test_held_out_pattern_only_in_test(split_setup):
    world, thr, pay = split_setup
    held = thr.split.holdout_pattern
    pattern = pay["payment_id"].map(
        world.tables["qr_payments"].set_index("payment_id")[TRUE_PATTERN]
    )
    assert (pattern == held).any()
    assert set(pay.loc[pattern == held, "split"]) <= {"test", ""}
    assert (pay.loc[pattern == held, "split"] == "test").any()
    groups = shop_groups(world.tables["shops"], thr, world.config.seed)
    held_shops = world.tables["shops"].loc[world.tables["shops"][TRUE_PATTERN] == held, "shop_id"]
    assert (groups.loc[held_shops] == "test").all()


def test_split_is_stable(split_setup):
    world, thr, pay = split_setup
    again = assign_split(pay.drop(columns="split"), world.tables, world.config, thr)
    assert (again.to_numpy() == pay["split"].to_numpy()).all()


def test_shares_roughly_match(split_setup):
    world, thr, _ = split_setup
    groups = shop_groups(
        world.tables["shops"],
        thr.model_copy(update={"split": thr.split.model_copy(update={"holdout_pattern": None})}),
        world.config.seed,
    )
    share = groups.value_counts(normalize=True)
    assert abs(share["train"] - 0.6) < 0.1
