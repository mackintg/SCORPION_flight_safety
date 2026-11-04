"""
graham.mackintosh@nasa.gov
11/3/2026

This utility creates a ranked JSON listing of on orbit "objects to avoid". Its purpose is to 
generate an up-to-date list of objects that should be avoided by the SCORPION flight planning
solution. This will demonstrate the ability for SCORPION to include flight safety considerations
in its multi-rendezvous flight plan optimization, as a precursor to full integration into NASAs
flight plan safety verification procedure.

The "importance to avoid" ranking is explained below.

Per-object attributes optionally come from a manually constructed table (data/exclusion_zones.csv) 
in the cases where the object has a match in that table, and from class/regime rules where it does not.
Table is optional. Fallback rules are explained below.

Columns of the exclusion_zones.csv file are:

-----------------------------
MATCH_TYPE: how the row selects objects: ID or NAME_REGEX, in any case. A row with any other value is skipped.

MATCH: what to select.

For ID rows, a NORAD catalog number, such as 25544.

For NAME_REGEX rows, a regular expression searched within the object name, ignoring case. The search matches 
anywhere in the name, so anchor with ^ to match only at the start: ^STARLINK- matches STARLINK-30239 but not XSTARLINK.

LAUNCHED_FROM: optional earliest launch date (YYYY-MM-DD), inclusive, compared against the SATCAT launch date. 
Leave blank for no lower bound. An object with no launch date in the SATCAT never matches a row that sets either launch bound.

LAUNCHED_TO: optional latest launch date, inclusive. Used with LAUNCHED_FROM to split one family by generation, 
such as Starlink V1.5 and V2 Mini.

CLASS: inhabitable, active or debris, in any case. Defaults to active, except that the ISS (25544) and Tiangong (48274) 
are inhabitable even without a table. An inhabitable object gets tier 0 by default, the FAA inhabitable exclusion zone by default, 
and has any docked modules sharing its exact orbital elements folded into its row (counted in the output MODULES column).

USERS: free-text label such as commercial or military (open-source reporting). Informational only: it is copied to 
the output and does not affect ranking. No public catalog carries this attribute, so the label is only as good as its source.

TIER: optional integer that orders objects before anything else; lower tiers rank first. Defaults to 0 for 
inhabitable and 1 for everything else. Setting it lets you promote or demote an object or family regardless 
of size or exclusion-zone volume.

SIZE_BIN: coarse size class by maximum dimension, solar arrays included:
Bin	Max dimension	Representative dimension used in the score
XS	under 1 m	0.5 m
S	1 to 4 m	2 m
M	4 to 12 m	6.9 m
L	12 to 40 m	21.9 m
XL	over 40 m	63 m
This column must be uppercase. A lowercase value such as m is silently ignored, and the object falls back to its RCS, 
its family majority or the default bin. When set, this column takes priority over every other size source.

MAX_DIM_M: maximum dimension in meters, used only when SIZE_BIN is blank; the script converts it to a bin with 
the edges above. When both are filled (as for the ISS), the bin wins and this value is documentation.

SIZE_BASIS: free-text comment on where the size came from, such as solar array span of V2 Mini. 
Not used by the script and not copied to the output.

SHAPE: SPHERE, ELLIPSOID or BOX.
Leave blank to use the default: the FAA class zone, which is inhabitable: 
50 × 200 × 50 km ellipsoid; active: 25 km sphere; debris: 2.5 km sphere.
With --volume-basis sfsh, active objects default to the SFSH box for their perigee band instead.
Any other value gives an undefined volume, and the object will not rank correctly.

R_KM: radial dimension in km. Required whenever SHAPE is set; if it is missing, the volume is 
undefined and the object will not rank correctly.
For SPHERE, the radius, and the other two columns are ignored.
For ELLIPSOID, the radial semi-axis.
For BOX, the radial half-width.

I_KM: in-track semi-axis (ellipsoid) or half-width (box), in km. If blank, R_KM is used.
C_KM: cross-track semi-axis or half-width, in km. If blank, R_KM is used. All three are measured 
from the object’s center, so a BOX with 2 / 25 / 25 is 4 × 50 × 50 km overall. 
Volume is 4/3·π·R³ for a sphere, 4/3·π·R·I·C for an ellipsoid, and 8·R·I·C for a box.

SOURCE: citation or URL for the row’s values. Not used by the script.

NOTES: free-text caveats, such as approximate launch-date splits or unpublished dimensions. 
Not used by the script.
---------------------------------

Note that if a matched row sets neither SIZE_BIN nor MAX_DIM_M, the object’s size comes from:
its catalog RCS, converted with d = 2.2 × 2√(RCS/π);
otherwise, the majority bin of its name family, when at least 5 members have an RCS;
otherwise, --default-bin (S unless you change it).

The "importance to avoid" ranking is implemented as:
  1. TIER ascending
  2. SCORE descending, SCORE = log10(V_exclusion) + w * log10(D_rep^2), D_rep = bin midpoint
  3. SFSH box volume descending (regime-driven prediction uncertainty)
  4. perigee ascending (more drag, faster growth of in-track error)
  5. element-set age descending

COMMAND LINE ARGUMENTS

Usage: python rank_leo.py [options]

Run with no options, the script downloads today’s active satellites from CelesTrak, ranks every object in LEO, and writes the top 100 to ranked_leo.csv and ranked_leo.json in the current folder.

Where the data comes from

--data-dir FOLDER: use files already saved in FOLDER instead of downloading. FOLDER must hold active.json and satcat.csv; if it also holds exclusion_zones.csv, that table is used too. Use this to rerun within CelesTrak’s 2-hour update window, which refuses repeat downloads. With this option set, --save-dir is ignored.
Example: --data-dir data
--save-dir FOLDER (default data): when downloading, also save active.json and satcat.csv here so you can rerun later with --data-dir. Existing copies are overwritten, and the saved satcat.csv contains active payloads only. Has no effect when --data-dir is set.
--table FILE: use a specific exclusion-zone table. By default the script looks for exclusion_zones.csv inside --data-dir. Without --data-dir (a fresh download), no table is used unless you name one here.
Example: --table data/exclusion_zones.csv

How objects are scored

--volume-basis faa|sfsh (default faa): the exclusion zone given to active objects that have no shape in the table.
faa: a 25 km sphere for every active object, from the FAA launch collision-avoidance rule (14 CFR 450.169). Since every active object then gets the same volume, size bin decides their order.
sfsh: the screening box from the Spaceflight Safety Handbook for the object’s perigee band. Boxes are larger at lower altitude, so low objects rank higher.
Inhabitable objects always get the FAA ellipsoid (50 × 200 × 50 km) unless the table sets a shape.
--default-bin XS|S|M|L|XL (default S): the size bin for an object the table doesn’t cover, that has no catalog RCS, and whose family has too few measured members to borrow a size from. Must be uppercase. About 2,500 objects in today’s catalog fall back to this.
--w NUMBER (default 0.5): how much size counts against exclusion-zone volume in the score. The score is log₁₀(volume) + w × log₁₀(dimension²).
0 ignores size.
Larger values let size outweigh differences in zone volume.
Under the default faa basis every active object has the same volume, so w only matters when volumes differ: with --volume-basis sfsh, or for objects with a table shape.

What gets written

--list-length N (default 100): how many top-ranked objects to write. 0 writes all of them. The full set is always ranked first, so the top N is the same whether you write 10 or 10,000.
--omit ITEM [ITEM ...]: leave whole groups out of the ranking. Choose from inhabitable, starlink, iridium, oneweb, kuiper, qianfan, hulianwang and yaogan. Case doesn’t matter, and items can be separated by spaces, commas or both. Ranks are renumbered over what remains. Omitted objects still count when the script borrows sizes from family members, so omitting one family doesn’t change anyone else’s size bin.
Example: --omit starlink oneweb or --omit Starlink,OneWeb

Other

-h, --help: show the built-in summary and exit.

Examples

python rank_leo.py                                  # the basic run... download, rank, write top 100
python rank_leo.py --data-dir data                  # reuse saved files
python rank_leo.py --data-dir data  --volume-basis faa --w 0.5    # FAA basis, the 0.5 weight on size score calc
python rank_leo.py --data-dir data --list-length 0  # write every ranked object
python rank_leo.py --data-dir data --omit starlink --volume-basis sfsh
python rank_leo.py --data-dir data --omit Starlink oneweb   # or: --omit starlink,oneweb

Local data files can be manually downloaded if you run into problems running rank_leo.py 
with the Celestrak firewall:

  data/active.json  <- https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json
  data/satcat.csv   <- https://celestrak.org/pub/satcat.csv
  
OUPUT

The output is the ranked_leo.csv (ranking attributes) and ranked_leo.json (CelesTrak OMM elements),
each holding the top --list-length objects (default 100) in rank order.

RUNTIME CONSIDERATONS

CelesTrak queries have no sort order, so the full active set is always downloaded and
ranked; --list-length only trims the outputs.
"""

import argparse
import io
import math
import os

import numpy as np
import pandas as pd
import requests

GP = "https://celestrak.org/NORAD/elements/gp.php"
SATCAT_CSV = "https://celestrak.org/pub/satcat.csv"
SATCAT_QUERY = "https://celestrak.org/satcat/records.php"
OMM_FIELDS = ["OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY",
              "INCLINATION", "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY",
              "EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO",
              "REV_AT_EPOCH", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"]
MU, RE = 398600.4418, 6378.137

# Fallback station list when no table is supplied.
INHABITABLE = {25544: "ISS", 48274: "CSS TIANHE"}

# SFSH Table 3 LEO regimes: (max perigee km, U, V, W half-widths km)
SFSH_LEO = [(500, 0.4, 44.0, 51.0), (750, 0.4, 25.0, 25.0),
            (1200, 0.4, 12.0, 12.0), (2000, 0.4, 2.0, 2.0)]

# FAA 14 CFR 450.169 defaults: (shape, radial, in-track, cross-track)
FAA_DEFAULT = {"inhabitable": ("ELLIPSOID", 50.0, 200.0, 50.0),
               "active": ("SPHERE", 25.0, 25.0, 25.0),
               "debris": ("SPHERE", 2.5, 2.5, 2.5)}

# Coarse size bins by maximum dimension (deployed arrays included), the quantity a
# hard-body radius is built from. (name, upper edge m, representative dimension m)
SIZE_BINS = [("XS", 1.0, 0.5), ("S", 4.0, 2.0), ("M", 12.0, 6.9), ("L", 40.0, 21.9),
             ("XL", np.inf, 63.0)]
BIN_REP_M = {b: rep for b, _, rep in SIZE_BINS}
BIN_ORDER = {b: i for i, (b, _, _) in enumerate(SIZE_BINS)}
# RCS to equivalent dimension: d = K * 2 * sqrt(RCS / pi). Radar return understates the
# extent of spacecraft with arrays; K = 2.2 is calibrated on one object, HST
# (RCS 28 m^2, 13.2 m long). A single calibration point: treat bins near edges as uncertain.
RCS_K = 2.2
# Space-Track RCS_SIZE categories, if that column is supplied (SMALL < 0.1, MEDIUM 0.1 to 1,
# LARGE > 1 m^2, commonly cited); mapped through the same RCS conversion at a mid value.
RCS_SIZE_M2 = {"SMALL": 0.05, "MEDIUM": 0.3, "LARGE": 3.0}
MIN_FAMILY_N = 5
ELSET_KEY = ["EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE"]
TABLE_FIELDS = ["CLASS", "USERS", "SIZE_BIN", "MAX_DIM_M", "SIZE_BASIS", "SHAPE", "R_KM",
                "I_KM", "C_KM", "TIER"]


def add_orbit_columns(df):
    n = df["MEAN_MOTION"].astype(float)
    e = df["ECCENTRICITY"].astype(float)
    a = (MU / (n * 2 * math.pi / 86400.0) ** 2) ** (1.0 / 3.0)
    df["PERIGEE_KM"] = a * (1 - e) - RE
    df["APOGEE_KM"] = a * (1 + e) - RE
    return df


def sfsh_box(perigee_km):
    for pmax, u, v, w in SFSH_LEO:
        if perigee_km <= pmax:
            return ("BOX", u, v, w)
    return ("BOX", np.nan, np.nan, np.nan)


def shape_volume(shape, r, i, c):
    if shape == "SPHERE":
        return 4.0 / 3.0 * math.pi * r**3
    if shape == "ELLIPSOID":
        return 4.0 / 3.0 * math.pi * r * i * c
    if shape == "BOX":
        return 8.0 * r * i * c
    return np.nan


def name_family(name):
    """Name family for RCS imputation, e.g. 'STARLINK-1234' -> 'STARLINK'."""
    s = str(name).upper().replace("-", " ").split()
    return s[0] if s else ""


def apply_table(df, table):
    """First matching row wins; ID rows are tried before NAME_REGEX rows, then file order."""
    for c in TABLE_FIELDS + ["TABLE_ROW"]:
        df[c] = np.nan
    for c in ("USERS", "CLASS", "SHAPE", "SIZE_BIN", "SIZE_BASIS"):
        df[c] = df[c].astype(object)
    if table is None or table.empty:
        return df
    t = table.copy()
    t["_order"] = np.where(t["MATCH_TYPE"].str.upper() == "ID", 0, 1)
    t = t.reset_index().sort_values(["_order", "index"])
    launched = pd.to_datetime(df.get("LAUNCH_DATE"), errors="coerce")
    free = pd.Series(True, index=df.index)
    for _, row in t.iterrows():
        kind = str(row["MATCH_TYPE"]).upper()
        if kind == "ID":
            m = df["NORAD_CAT_ID"] == int(row["MATCH"])
        elif kind == "NAME_REGEX":
            m = df["OBJECT_NAME"].astype(str).str.contains(str(row["MATCH"]), case=False,
                                                           regex=True)
        else:
            continue
        if pd.notna(row.get("LAUNCHED_FROM")):
            m &= launched >= pd.Timestamp(row["LAUNCHED_FROM"])
        if pd.notna(row.get("LAUNCHED_TO")):
            m &= launched <= pd.Timestamp(row["LAUNCHED_TO"])
        m &= free
        for c in TABLE_FIELDS:
            if c in row and pd.notna(row[c]):
                df.loc[m, c] = row[c]
        df.loc[m, "TABLE_ROW"] = row["index"] + 2  # line number in the CSV
        free &= ~m
    return df


def collapse_stations(df, station_ids):
    """Fold docked modules that share a station's exact element set into the station row."""
    df["MODULES"] = 0
    drop = []
    for sid in station_ids:
        st = df[df["NORAD_CAT_ID"] == sid]
        if st.empty:
            continue
        same = (df[ELSET_KEY] == st[ELSET_KEY].iloc[0].values).all(axis=1)
        members = df.index[same & (df["NORAD_CAT_ID"] != sid)]
        df.loc[st.index, "MODULES"] = len(members)
        drop.extend(members)
    return df.drop(index=drop)


def dim_to_bin(d):
    for b, edge, _ in SIZE_BINS:
        if d < edge:
            return b
    return SIZE_BINS[-1][0]


def rcs_to_dim(rcs):
    return RCS_K * 2.0 * np.sqrt(rcs / np.pi)


def size_bins(df, default_bin="S"):
    """Size bin and provenance. Table bin > table dimension > RCS > RCS_SIZE >
    family majority (at least MIN_FAMILY_N members with RCS) > default."""
    out = pd.Series(np.nan, index=df.index, dtype=object)
    src = pd.Series("", index=df.index, dtype=object)

    def fill(values, label):
        m = out.isna() & values.notna()
        out[m] = values[m]
        src[m] = label

    fill(df["SIZE_BIN"].where(df["SIZE_BIN"].isin(BIN_ORDER)), "TABLE_BIN")
    fill(pd.to_numeric(df["MAX_DIM_M"], errors="coerce").dropna().map(dim_to_bin)
         .reindex(df.index), "TABLE_DIM")
    rcs = pd.to_numeric(df["RCS"], errors="coerce").where(lambda s: s > 0)
    rcs_bin = rcs.dropna().map(lambda v: dim_to_bin(rcs_to_dim(v))).reindex(df.index)
    fill(rcs_bin, "RCS")
    if "RCS_SIZE" in df.columns:
        cat = df["RCS_SIZE"].astype(str).str.upper().map(RCS_SIZE_M2)
        fill(cat.dropna().map(lambda v: dim_to_bin(rcs_to_dim(v))).reindex(df.index),
             "RCS_SIZE")
    fam = df["OBJECT_NAME"].map(name_family)
    known = rcs_bin.where(df["TIER"] > 0).dropna()
    g = known.groupby(fam[known.index])
    mode = g.agg(lambda s: s.value_counts().index[0]).where(g.size() >= MIN_FAMILY_N)
    fill(fam.map(mode), "FAMILY_MAJORITY")
    fill(pd.Series(default_bin, index=df.index), "DEFAULT")
    return out, src


OMIT_CLASSES = ("inhabitable",)
OMIT_FAMILIES = {"starlink": r"^STARLINK", "iridium": r"^IRIDIUM", "oneweb": r"^ONEWEB",
                    "kuiper": r"^KUIPER", "qianfan": r"^QIANFAN",
                    "hulianwang": r"^HULIANWANG", "yaogan": r"^YAOGAN"}
OMIT_CHOICES = OMIT_CLASSES + tuple(OMIT_FAMILIES)


def omit_mask(df, omit):
    """True for rows removed by --omit (classes by CLASS, families by name prefix)."""
    m = pd.Series(False, index=df.index)
    for x in omit or ():
        if x in OMIT_CLASSES:
            m |= df["CLASS"] == x
        else:
            m |= df["OBJECT_NAME"].astype(str).str.upper().str.contains(OMIT_FAMILIES[x],
                                                                         regex=True)
    return m


def rank(df, w=0.5, ref_time=None, table=None, basis="faa", default_bin="S", omit=None):
    df = add_orbit_columns(df.copy())
    df = df[(df["PERIGEE_KM"] <= 2000) & (df["ECCENTRICITY"].astype(float) < 0.25)].copy()
    df = apply_table(df, table)

    is_station_id = df["NORAD_CAT_ID"].isin(INHABITABLE) & df["CLASS"].isna()
    df.loc[is_station_id, "CLASS"] = "inhabitable"
    df["CLASS"] = df["CLASS"].fillna("active").str.lower()
    stations = df.loc[df["CLASS"] == "inhabitable", "NORAD_CAT_ID"].tolist()
    df = collapse_stations(df, stations)

    df["TIER"] = pd.to_numeric(df["TIER"], errors="coerce")
    df["TIER"] = df["TIER"].fillna((df["CLASS"] != "inhabitable").astype(int)).astype(int)

    sfsh = df["PERIGEE_KM"].map(sfsh_box)
    df["V_SFSH_KM3"] = [shape_volume(*b) for b in sfsh]

    shapes = []
    for (_, r), box in zip(df.iterrows(), sfsh):
        if pd.notna(r["SHAPE"]):
            shapes.append((str(r["SHAPE"]).upper(), float(r["R_KM"]),
                           float(r["I_KM"]) if pd.notna(r["I_KM"]) else float(r["R_KM"]),
                           float(r["C_KM"]) if pd.notna(r["C_KM"]) else float(r["R_KM"]),
                           "TABLE"))
        elif basis == "sfsh" and r["CLASS"] == "active":
            shapes.append(box + ("SFSH",))
        else:
            shapes.append(FAA_DEFAULT.get(r["CLASS"], FAA_DEFAULT["active"]) + ("FAA",))
    df["EXCLUSION_SHAPE"] = [s[0] for s in shapes]
    df["EXCLUSION_RIC_KM"] = [f"{s[1]:g}/{s[2]:g}/{s[3]:g}" for s in shapes]
    df["EXCLUSION_SOURCE"] = [s[4] for s in shapes]
    df["EXCLUSION_KM3"] = [shape_volume(*s[:4]) for s in shapes]

    df["SIZE_BIN_USED"], df["SIZE_SOURCE"] = size_bins(df, default_bin)
    df["DIM_REP_M"] = df["SIZE_BIN_USED"].map(BIN_REP_M)
    # area scales as dimension squared
    df["SCORE"] = np.log10(df["EXCLUSION_KM3"]) + w * 2.0 * np.log10(df["DIM_REP_M"])

    ref = ref_time or pd.Timestamp.utcnow().tz_localize(None)
    df["ELSET_AGE_D"] = (ref - pd.to_datetime(df["EPOCH"])).dt.total_seconds() / 86400.0
    # The --omit filter is applied after sizing, so family
    # majorities still see every object, and before numbering, so ranks run 1..N.
    df = df[~omit_mask(df, omit)]
    df = df.sort_values(["TIER", "SCORE", "V_SFSH_KM3", "PERIGEE_KM", "ELSET_AGE_D"],
                        ascending=[True, False, False, True, False])
    df["RANK"] = np.arange(1, len(df) + 1)
    return df


def fetch(data_dir=None, save_dir=None):
    """Download from CelesTrak, or read active.json and satcat.csv from data_dir.
    When downloading, save_dir (if given) receives active.json and satcat.csv so a rerun
    within CelesTrak's 2-hour window can use --data-dir instead."""
    if data_dir:
        import json
        with open(os.path.join(data_dir, "active.json"), encoding="utf-8") as f:
            omm = pd.DataFrame(json.load(f))
        sat = pd.read_csv(os.path.join(data_dir, "satcat.csv"))
    else:
        r = requests.get(GP, params={"GROUP": "active", "FORMAT": "json"}, timeout=60)
        r.raise_for_status()
        try:
            omm = pd.DataFrame(r.json())
        except ValueError:
            # CelesTrak answers with plain text when it refuses, e.g. a repeat download
            # of the same group within its 2-hour update interval
            raise SystemExit("CelesTrak did not return GP data:\n" + r.text.strip()[:500])
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            with open(os.path.join(save_dir, "active.json"), "w", encoding="utf-8") as f:
                f.write(r.text)
        # Only active payloads are ranked, so ask the SATCAT query for those rather than the
        # full catalog; fall back to the full file if the reply lacks needed columns.
        sat = None
        try:
            r = requests.get(SATCAT_QUERY, params={"GROUP": "active", "FORMAT": "CSV"},
                             timeout=120)
            r.raise_for_status()
            sat = pd.read_csv(io.StringIO(r.text))
            if not {"NORAD_CAT_ID", "RCS", "LAUNCH_DATE"} <= set(sat.columns):
                sat = None
        except (requests.RequestException, pd.errors.ParserError):
            sat = None
        if sat is None:
            r = requests.get(SATCAT_CSV, timeout=120)
            r.raise_for_status()
            sat = pd.read_csv(io.StringIO(r.text))
        if save_dir:
            sat.to_csv(os.path.join(save_dir, "satcat.csv"), index=False)
    keep = ("NORAD_CAT_ID", "OBJECT_TYPE", "OWNER", "LAUNCH_DATE", "RCS", "RCS_SIZE")
    sat = sat[[c for c in keep if c in sat]]
    return omm.merge(sat, on="NORAD_CAT_ID", how="left")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=float, default=0.5, help="area weight in SCORE (default 0.5)")
    ap.add_argument("--data-dir", default=None,
                    help="folder with active.json, satcat.csv and optional "
                         "exclusion_zones.csv (skips the download)")
    ap.add_argument("--table", default=None, help="exclusion-zone table CSV (default: "
                    "<data-dir>/exclusion_zones.csv if present)")
    ap.add_argument("--volume-basis", choices=["faa", "sfsh"], default="faa",
                    help="default exclusion zone for active objects without a table shape")
    ap.add_argument("--default-bin", choices=list(BIN_ORDER), default="S",
                    help="size bin for objects with no table entry, RCS or family majority")
    ap.add_argument("--list-length", type=int,
                    default=100, help="number of ranked objects written to the outputs "
                    "(default 100; 0 means no limit). Ranking always uses the full set.")
    ap.add_argument("--save-dir", default="data",
                    help="when downloading, save active.json and satcat.csv here "
                         "(default: data) for reuse with --data-dir")
    ap.add_argument("--omit", nargs="+", default=[], metavar="ITEM",
                    help="leave out one or more of: " + ", ".join(OMIT_CHOICES) +
                    " (case-insensitive; space- or comma-separated). Default: nothing")
    args = ap.parse_args()
    if args.list_length < 0:
        ap.error("--list-length must be 0 or a positive integer")
    omit = [x.strip().lower() for item in args.omit for x in item.split(",")
               if x.strip()]
    bad = sorted(set(omit) - set(OMIT_CHOICES))
    if bad:
        ap.error(f"--omit: unknown item(s) {', '.join(bad)}; "
                 f"choose from {', '.join(OMIT_CHOICES)}")
    omit = sorted(set(omit), key=OMIT_CHOICES.index)

    df = fetch(args.data_dir, None if args.data_dir else args.save_dir)
    tpath = args.table or (os.path.join(args.data_dir, "exclusion_zones.csv")
                           if args.data_dir else None)
    table = pd.read_csv(tpath) if tpath and os.path.exists(tpath) else None
    ranked = rank(df, args.w, table=table, basis=args.volume_basis,
                  default_bin=args.default_bin, omit=omit)

    cols = ["RANK", "NORAD_CAT_ID", "OBJECT_NAME", "TIER", "CLASS", "USERS", "OWNER",
            "MODULES", "PERIGEE_KM", "EXCLUSION_SHAPE", "EXCLUSION_RIC_KM", "EXCLUSION_KM3",
            "EXCLUSION_SOURCE", "SIZE_BIN_USED", "DIM_REP_M", "SIZE_SOURCE", "RCS",
            "V_SFSH_KM3", "SCORE", "ELSET_AGE_D", "EPOCH", "TABLE_ROW"]
    out = ranked.head(args.list_length) if args.list_length else ranked
    out[cols].to_csv("ranked_leo.csv", index=False)
    # Orbital elements for the same objects, in rank order, as CelesTrak OMM JSON
    omm_cols = [c for c in OMM_FIELDS if c in out.columns]
    out[omm_cols].to_json("ranked_leo.json", orient="records", indent=1)

    print(f"table: {tpath if table is not None else 'none'}; basis: {args.volume_basis}; "
          f"w = {args.w}; omitted: {', '.join(omit) if omit else 'nothing'}")
    print(f"{len(ranked)} LEO objects ranked; wrote {len(out)}")
    print("size source:", ranked["SIZE_SOURCE"].value_counts().to_dict())
    print("size bin:", ranked["SIZE_BIN_USED"].value_counts().reindex(list(BIN_ORDER))
          .fillna(0).astype(int).to_dict())
    print("exclusion-zone source:", ranked["EXCLUSION_SOURCE"].value_counts().to_dict())
    print("users (table):", ranked["USERS"].value_counts().to_dict())
    show = ["RANK", "NORAD_CAT_ID", "OBJECT_NAME", "TIER", "CLASS", "MODULES",
            "EXCLUSION_SHAPE", "EXCLUSION_KM3", "SIZE_BIN_USED", "SIZE_SOURCE", "PERIGEE_KM"]
    print(ranked[show].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
