"""Base world: deterministic, inside the calendar, labels hidden, no personal data."""

import re

import numpy as np
import pandas as pd

from jachai.world.generate import generate_world, read_world_tables, write_world
from jachai.world.world import (
    EVENT_TABLES,
    HIDDEN_PREFIX,
    TRUE_LABEL,
    TRUE_PATTERN,
    public_view,
)


def test_same_seed_gives_identical_world(small_cfg):
    a = generate_world(small_cfg).tables
    b = generate_world(small_cfg).tables
    assert a.keys() == b.keys()
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name], obj=name)


def test_different_seed_gives_different_world(make_cfg):
    a = generate_world(make_cfg(seed=1)).tables["qr_payments"]
    b = generate_world(make_cfg(seed=2)).tables["qr_payments"]
    assert not a["amount"].equals(b["amount"])


def test_events_inside_calendar_window(small_cfg):
    world = generate_world(small_cfg)
    lo = pd.Timestamp(small_cfg.calendar.start)
    hi = pd.Timestamp(small_cfg.calendar.end) + pd.Timedelta(days=1)
    for name in EVENT_TABLES:
        ts = world.tables[name]["ts"]
        assert ts.is_monotonic_increasing, name
        assert ((ts >= lo) & (ts < hi)).all(), name


def test_every_table_has_rows_and_unique_ids(make_cfg):
    tables = generate_world(make_cfg(scenario__p2p_qr_enabled=True)).tables
    for name, df in tables.items():
        assert len(df) > 0, name
        id_col = df.columns[0]
        assert id_col.endswith("_id"), name
        assert df[id_col].is_unique, name


def test_p2p_table_empty_unless_scenario_enabled(small_cfg):
    assert generate_world(small_cfg).tables["p2p_transfers"].empty


def test_true_labels_are_hidden(small_cfg):
    world = generate_world(small_cfg)
    for name in ("shops", "qr_payments"):
        df = world.tables[name]
        assert {TRUE_LABEL, TRUE_PATTERN} <= set(df.columns)
        assert not any(c.startswith(HIDDEN_PREFIX) for c in public_view(df).columns)


def test_parquet_round_trip(small_cfg, tmp_path):
    world = generate_world(small_cfg)
    write_world(world, tmp_path)
    back = read_world_tables(tmp_path)
    for name, df in world.tables.items():
        pd.testing.assert_frame_equal(df, back[name], check_dtype=False, obj=name)


# --- No real-looking personal data -----------------------------------------

PERSONAL_COLUMN = re.compile(r"name|phone|mobile_no|msisdn|nid|email|address|dob|birth", re.I)
# Bangladeshi mobile number, optionally with country code, as a standalone token.
PHONE = re.compile(r"(?<![0-9A-Za-z])(?:\+?88)?01[3-9]\d{8}(?![0-9A-Za-z])")
# NID numbers are 10, 13 or 17 digits.
NID = re.compile(r"^\d{10}$|^\d{13}$|^\d{17}$")


def test_no_personal_data_columns_or_values(make_cfg):
    tables = generate_world(make_cfg(scenario__p2p_qr_enabled=True)).tables
    for name, df in tables.items():
        for col in df.columns:
            assert not PERSONAL_COLUMN.search(col), f"{name}.{col} looks like personal data"
            if df[col].dtype.kind in "OSUT" or str(df[col].dtype) == "str":
                values = df[col].dropna().astype(str).unique()
                assert not any(PHONE.search(v) for v in values), f"phone-like value in {name}.{col}"
                assert not any(NID.match(v) for v in values), f"NID-like value in {name}.{col}"
            elif df[col].dtype.kind in "iu":
                # Integers of phone/NID length would also be suspicious.
                assert df[col].abs().max() < 10**9, f"{name}.{col} has phone/NID-sized numbers"


def test_ids_are_random_strings(small_cfg):
    shops = generate_world(small_cfg).tables["shops"]
    assert shops["shop_id"].str.fullmatch(r"SH[0-9a-f]{10}").all()
    # Not sequential: sorted order differs from generation order.
    assert not np.array_equal(shops["shop_id"].to_numpy(), np.sort(shops["shop_id"].to_numpy()))
