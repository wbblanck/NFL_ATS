"""Canonical player identity for Generation 2 (sprint 1, task 3).

One internal id per person, `uid`:
  * the nflverse GSIS id when the person has one (nflverse `players` is keyed by it, so this is stable and public);
  * otherwise `pfr:<pfr_id>` for people who appear only in PFR-keyed data (snap counts, PFR advanced stats).
Source-specific ids (PFR, ESB, PFF, ESPN, NFL, smart) are attached as columns. Team history comes from weekly rosters.
`diagnostics()` reports every duplicate or ambiguous mapping instead of silently picking one.
"""
from __future__ import annotations

import polars as pl

# nflverse keys `players` by GSIS id ("00-0034796"); players from before GSIS ids carry a 9-character legacy id
# ("ABB498348") in the same column. Both are stable keys. Anything else (empty strings) is not an id.
GSIS_RE = r"^(00-\d{7}|[A-Z]{3}\d{6})$"
ID_COLS = ["pfr_id", "esb_id", "pff_id", "espn_id", "nfl_id", "smart_id"]
FRANCHISE = {"STL": "LA", "SD": "LAC", "OAK": "LV", "JAC": "JAX", "LAR": "LA"}
KEEP = ["display_name", "birth_date", "position_group", "position", "rookie_season", "last_season", "draft_year",
        "draft_round", "draft_pick", "height", "weight", "college_name"]


def build_identity(players: pl.DataFrame, rosters: pl.DataFrame, snaps: pl.DataFrame) -> pl.DataFrame:
    """players: nflverse players. rosters: weekly rosters (all seasons stacked). snaps: snap counts (all seasons stacked).
    Returns one row per uid: uid, gsis_id, id columns, attributes, source ('players', 'roster_only', 'pfr_only')."""
    pl_ok = players.filter(pl.col("gsis_id").str.contains(GSIS_RE))
    base = pl_ok.select("gsis_id", *ID_COLS, *KEEP).with_columns(
        pl.col("gsis_id").alias("uid"), pl.lit("players").alias("source"), pl.col("birth_date").str.to_date(strict=False))
    # `players` rows whose gsis_id is empty or malformed: keyed by their other ids, never by the bad value
    odd = players.filter(~pl.col("gsis_id").str.contains(GSIS_RE) | pl.col("gsis_id").is_null()).select(*ID_COLS, *KEEP).with_columns(
        pl.coalesce(pl.when(pl.col("pfr_id").is_not_null()).then("pfr:" + pl.col("pfr_id")),
                    pl.when(pl.col("esb_id").is_not_null()).then("esb:" + pl.col("esb_id"))).alias("uid"),
        pl.lit("players_nonGSIS").alias("source"), pl.lit(None, dtype=pl.String).alias("gsis_id"),
        pl.col("birth_date").str.to_date(strict=False)).filter(pl.col("uid").is_not_null())
    base = pl.concat([base, odd], how="diagonal_relaxed")
    # people on weekly rosters but missing from `players`: keep their GSIS id, take what the roster row carries
    rw = rosters.filter(pl.col("gsis_id").str.contains(GSIS_RE)).select(
        "gsis_id", pl.col("pfr_id"), pl.col("esb_id"), pl.col("pff_id").cast(pl.String), pl.col("espn_id").cast(pl.String),
        pl.col("smart_id"), pl.col("full_name").alias("display_name"), pl.col("birth_date").cast(pl.Date),
        pl.col("position"), pl.col("rookie_year").alias("rookie_season")).unique("gsis_id", keep="last")
    extra = rw.join(base.filter(pl.col("gsis_id").is_not_null()).select("gsis_id"), on="gsis_id", how="anti").with_columns(
        pl.col("gsis_id").alias("uid"), pl.lit("roster_only").alias("source"), pl.lit(None, dtype=pl.String).alias("nfl_id"))
    # fill id gaps in `players` from rosters (never overwrite a value that is present)
    fill = rw.select("gsis_id", *[pl.col(c).alias(c + "_r") for c in ("pfr_id", "esb_id", "pff_id", "espn_id", "smart_id")])
    # a roster id may fill a gap only when no other person in `players` already owns it (one id, one person)
    for c in ("pfr_id", "esb_id", "pff_id", "espn_id", "smart_id"):
        owned = base[c].drop_nulls().to_list()
        fill = fill.with_columns(pl.when(pl.col(c + "_r").is_in(owned)).then(None).otherwise(pl.col(c + "_r")).alias(c + "_r"))
    base = base.join(fill, on="gsis_id", how="left").with_columns(
        *[pl.coalesce(c, c + "_r").alias(c) for c in ("pfr_id", "esb_id", "pff_id", "espn_id", "smart_id")]).drop(
        [c + "_r" for c in ("pfr_id", "esb_id", "pff_id", "espn_id", "smart_id")])
    out = pl.concat([base, extra], how="diagonal_relaxed")
    # PFR-only people (snap counts key on pfr_player_id)
    known = set(out["pfr_id"].drop_nulls().to_list())
    sn = snaps.filter(pl.col("pfr_player_id").is_not_null()).group_by("pfr_player_id").agg(
        pl.col("player").last().alias("display_name"), pl.col("position").last().alias("position"),
        pl.col("season").min().alias("rookie_season"), pl.col("season").max().alias("last_season"))
    pfr_only = sn.filter(~pl.col("pfr_player_id").is_in(list(known))).select(
        pl.col("pfr_player_id").alias("pfr_id"), "display_name", "position", "rookie_season", "last_season").with_columns(
        (pl.lit("pfr:") + pl.col("pfr_id")).alias("uid"), pl.lit(None, dtype=pl.String).alias("gsis_id"),
        pl.lit("pfr_only").alias("source"))
    out = pl.concat([out, pfr_only], how="diagonal_relaxed")
    return _alias_legacy(out).sort("uid")


def _alias_legacy(ident: pl.DataFrame) -> pl.DataFrame:
    """`canonical_uid`: a legacy-format id (ABC123456) that shares name and birth date with exactly one 00-xxxxxxx id is the same
    person; point it at the GSIS id. Two GSIS ids with the same name and birth date are left alone and only flagged."""
    legacy = pl.col("uid").str.contains(r"^[A-Z]{3}\d{6}$")
    modern = pl.col("uid").str.contains(r"^00-\d{7}$")
    key = ["display_name", "birth_date"]
    m = ident.filter(modern, pl.col("birth_date").is_not_null()).group_by(key).agg(pl.col("uid").first().alias("g"), pl.len().alias("n")).filter(pl.col("n") == 1)
    al = ident.filter(legacy, pl.col("birth_date").is_not_null()).join(m, on=key, how="inner").select(pl.col("uid"), pl.col("g").alias("canonical_uid"))
    return ident.join(al, on="uid", how="left").with_columns(pl.coalesce("canonical_uid", "uid").alias("canonical_uid"))


def team_history(rosters: pl.DataFrame, ident: pl.DataFrame) -> pl.DataFrame:
    """One row per (uid, season, week, team) from weekly rosters, franchise names unified."""
    m = ident.filter(pl.col("gsis_id").is_not_null()).select("gsis_id", "uid")
    return rosters.filter(pl.col("gsis_id").str.contains(GSIS_RE)).select(
        "gsis_id", pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64), pl.col("team").replace(FRANCHISE), "position",
        "game_type", "status").join(m, on="gsis_id").drop("gsis_id").unique(["uid", "season", "week", "team"])


def diagnostics(ident: pl.DataFrame, rosters: pl.DataFrame, snaps: pl.DataFrame) -> dict:
    """Counts of duplicate and ambiguous identities. Every list should be empty or explained in the audit doc."""
    d: dict = {"people": ident.height, "by_source": dict(ident.group_by("source").len().iter_rows())}
    d["duplicate_uid"] = int(ident["uid"].is_duplicated().sum())
    pf = ident.filter(pl.col("pfr_id").is_not_null())
    d["pfr_id_on_multiple_uids"] = pf.filter(pl.col("pfr_id").is_duplicated()).select("uid", "pfr_id", "display_name").to_dicts()
    # roster rows that tie one gsis id to several pfr ids, or one pfr id to several gsis ids
    rp = rosters.filter(pl.col("gsis_id").is_not_null(), pl.col("pfr_id").is_not_null()).select("gsis_id", "pfr_id").unique()
    d["gsis_with_multiple_pfr_in_rosters"] = rp.group_by("gsis_id").agg(pl.col("pfr_id")).filter(pl.col("pfr_id").list.len() > 1).to_dicts()
    d["pfr_with_multiple_gsis_in_rosters"] = rp.group_by("pfr_id").agg(pl.col("gsis_id")).filter(pl.col("gsis_id").list.len() > 1).to_dicts()
    # same name and birth date under different uids (possible split identity)
    nb = ident.filter(pl.col("birth_date").is_not_null(), pl.col("display_name").is_not_null())
    nb = nb.with_columns(pl.col("canonical_uid").alias("uid_c"))
    sp = nb.group_by("display_name", "birth_date").agg(pl.col("uid_c").n_unique().alias("n"), pl.col("uid_c").alias("uid")).filter(pl.col("n") > 1)
    d["legacy_ids_merged_into_gsis"] = ident.filter(pl.col("canonical_uid") != pl.col("uid")).select("uid", "canonical_uid", "display_name").to_dicts()
    d["same_name_birthdate_multiple_uids"] = sp.select("display_name", "birth_date", "uid").to_dicts()
    # same name, different people (ambiguous by name alone): shows why joins must use ids, never names
    d["names_shared_by_different_people"] = int(ident.group_by("display_name").agg(pl.col("uid").n_unique().alias("n")).filter(pl.col("n") > 1).height)
    # snap-count rows that cannot be mapped to a uid
    m = set(ident.filter(pl.col("pfr_id").is_not_null())["pfr_id"].to_list())
    s = snaps.filter(pl.col("pfr_player_id").is_not_null())
    d["snap_rows_unmapped"] = int((~s["pfr_player_id"].is_in(list(m))).sum())
    d["snap_rows_null_id"] = int(snaps["pfr_player_id"].is_null().sum())
    return d
