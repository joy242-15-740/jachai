"""Network score: the payer-shop graph, point in time.

Every `snapshot_every_days` days (snapshot day S), features are built from QR
payments in [S - window_days, S - 1]: nothing from day S or later. A shop-day D
uses the latest snapshot S <= D.

Two kinds of features:

1) From the bipartite payer-shop graph (all payments in the window)
   payer_diversity       distinct payers / payments (1 = every payment a new person)
   distant_payer_share   distinct payers living >= far_payer_km away

2) From a shop-shop "same-day heavy" graph
   Two shops are linked when the same payer paid both ON THE SAME DAY, paid at
   least `link_min_shops_same_day` shops that day, and that payer's QR total that
   day passed `link_min_day_total_share` of the daily cash-out limit: the brief's
   limit-bypass definition. Honest shoppers rarely do this.
   Earlier designs and why they failed (on train + validation shops):
     - any shared payer: neighbourhoods share regulars, so Louvain found whole
       neighbourhoods (about 60 shops) and no rings;
     - same day above half the limit across 2 shops: honest big shoppers (a TV
       plus groceries) linked many honest shops.
   Louvain community detection (NetworkX, fixed seed) runs on this sparse graph.
   linking_payers        distinct payers linking the shop to others in its community
   community_size        shops in its community (1 = no heavy links)
   community_span_km     largest distance between two shops of the community
   ring_flag             small, tight community with enough linking payers (rules.yaml)
"""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
from networkx.algorithms.community import louvain_communities

from jachai.labels.config import RingFlag
from jachai.models.config import NetworkConfig
from jachai.world.world import public_view

NETWORK_COLUMNS = [
    "payer_diversity",
    "distant_payer_share",
    "linking_payers",
    "community_size",
    "community_span_km",
    "ring_flag",
]


def snapshot_days(start: pd.Timestamp, n_days: int, cfg: NetworkConfig) -> pd.DatetimeIndex:
    days = pd.date_range(start, periods=n_days, freq="D")
    return days[cfg.snapshot_every_days :: cfg.snapshot_every_days]


def heavy_same_day_pairs(window: pd.DataFrame, cfg: NetworkConfig, limit: float) -> pd.DataFrame:
    """Unique (payer_id, shop_id, day) where the payer paid enough shops that day
    and their day total passed the link threshold."""
    w = window.assign(day=window["ts"].dt.normalize())
    per = w.groupby(["payer_id", "day", "shop_id"], as_index=False)["amount"].sum()
    g = per.groupby(["payer_id", "day"])
    day_total, n_shops = g["amount"].transform("sum"), g["shop_id"].transform("size")
    keep = (
        (day_total > cfg.link_min_day_total_share * limit)
        & (n_shops >= cfg.link_min_shops_same_day)
        & (n_shops <= cfg.max_shops_per_payer)
    )
    return per.loc[keep, ["payer_id", "day", "shop_id"]]


def shop_links(pairs: pd.DataFrame, cfg: NetworkConfig) -> pd.DataFrame:
    """Shop pairs with the number of distinct payers who paid both on the same day."""
    both = pairs.merge(pairs, on=["payer_id", "day"], suffixes=("_a", "_b"))
    both = both[both["shop_id_a"] < both["shop_id_b"]]
    shared = (
        both.groupby(["shop_id_a", "shop_id_b"])["payer_id"]
        .nunique()
        .rename("shared")
        .reset_index()
    )
    return shared[shared["shared"] >= cfg.min_shared_payers]


def snapshot_features(
    window: pd.DataFrame,
    shops: pd.DataFrame,
    customers: pd.DataFrame,
    cfg: NetworkConfig,
    ring: RingFlag,
    far_km: float,
    limit: float,
    seed: int,
) -> pd.DataFrame:
    """Network features for every shop from one window of payments."""
    out = pd.DataFrame(index=pd.Index(shops["shop_id"], name="shop_id"))
    pairs = window[["payer_id", "shop_id"]].drop_duplicates()
    out["payer_diversity"] = (
        pairs.groupby("shop_id").size() / window.groupby("shop_id").size()
    ).reindex(out.index)

    sx, sy = shops.set_index("shop_id")["x_km"], shops.set_index("shop_id")["y_km"]
    cx, cy = customers.set_index("customer_id")["x_km"], customers.set_index("customer_id")["y_km"]
    dist = np.hypot(
        pairs["payer_id"].map(cx) - pairs["shop_id"].map(sx),
        pairs["payer_id"].map(cy) - pairs["shop_id"].map(sy),
    )
    out["distant_payer_share"] = (
        (dist >= far_km).groupby(pairs["shop_id"]).mean().reindex(out.index)
    )

    heavy = heavy_same_day_pairs(window, cfg, limit)
    edges = shop_links(heavy, cfg)
    graph = nx.Graph()
    graph.add_nodes_from(out.index)
    graph.add_weighted_edges_from(
        edges[["shop_id_a", "shop_id_b", "shared"]].itertuples(index=False)
    )
    communities = louvain_communities(graph, weight="weight", seed=seed)
    community_of = {shop: i for i, members in enumerate(communities) for shop in members}
    community = pd.Series(out.index.map(community_of), index=out.index)
    out["community_size"] = community.map(community.value_counts())

    # Linking payers: paid this shop and another shop of the same community on the same day.
    h = heavy.assign(community=heavy["shop_id"].map(community_of))
    shops_in_comm = h.groupby(["payer_id", "day", "community"])["shop_id"].transform("nunique")
    linking = h[shops_in_comm > 1].groupby("shop_id")["payer_id"].nunique()
    out["linking_payers"] = linking.reindex(out.index, fill_value=0)

    lo, hi = ring.community_size
    span = {}
    for i, members in enumerate(communities):
        m = list(members)
        if len(m) == 1:
            span[i] = 0.0
        elif len(m) <= hi:
            xs, ys = sx.loc[m].to_numpy(), sy.loc[m].to_numpy()
            span[i] = float(np.hypot(xs[:, None] - xs, ys[:, None] - ys).max())
        else:
            span[i] = np.inf  # too big to be a ring; skip the pairwise distances
    out["community_span_km"] = community.map(span)

    out["ring_flag"] = (
        out["community_size"].between(lo, hi)
        & (out["community_span_km"] <= ring.max_span_km)
        & (out["linking_payers"] >= ring.min_linking_payers)
    ).astype(np.int8)
    return out


def build_network_features(
    tables: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    n_days: int,
    cfg: NetworkConfig,
    ring: RingFlag,
    far_km: float,
    limit: float,
    seed: int,
) -> pd.DataFrame:
    """One row per (snapshot day, shop). Each snapshot uses only earlier payments."""
    qr = public_view(tables["qr_payments"])[["ts", "payer_id", "shop_id", "amount"]]
    day = qr["ts"].dt.normalize()
    shops, customers = public_view(tables["shops"]), public_view(tables["customers"])
    frames = []
    for snap in snapshot_days(start, n_days, cfg):
        window = qr[(day < snap) & (day >= snap - pd.Timedelta(days=cfg.window_days))]
        f = snapshot_features(window, shops, customers, cfg, ring, far_km, limit, seed)
        frames.append(f.reset_index().assign(snapshot=snap))
    return pd.concat(frames, ignore_index=True)


def network_as_of(network: pd.DataFrame, shop_day: pd.DataFrame) -> pd.DataFrame:
    """For each shop-day, the latest snapshot on or before that day (NaN before the first)."""
    left = shop_day[["shop_id", "day"]].reset_index(names="_row").sort_values("day")
    right = network.rename(columns={"snapshot": "day"}).sort_values("day")
    merged = pd.merge_asof(
        left.astype({"day": "datetime64[ns]"}),
        right.astype({"day": "datetime64[ns]"}),
        on="day",
        by="shop_id",
        allow_exact_matches=True,
    )
    return merged.set_index("_row").sort_index()[NETWORK_COLUMNS].set_axis(shop_day.index)
