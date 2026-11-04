# SCORPION_flight_safety

Experimental code to include object avoidance in SCORPION flight plan optimization.

`rank_leo.py` creates a ranked listing of on-orbit "objects to avoid" in low Earth orbit (LEO). Its purpose is to generate an up-to-date list of objects that the SCORPION flight planning solution should avoid. This demonstrates the ability for SCORPION to include flight safety considerations in its multi-rendezvous flight plan optimization, as a precursor to full integration into NASA's flight plan safety verification procedure.

Contact: Graham Mackintosh, graham.mackintosh@nasa.gov

## Repository layout

| Path | Contents |
|---|---|
| `rank_leo.py` | The ranking utility |
| `data/exclusion_zones.csv` | Hand-maintained exclusion-zone table |
| `references/` | Internet shortcuts (`.url`) to NASA Conjunction Assessment Risk Analysis (CARA) resources; further references are linked at the end of this README |

CelesTrak downloads (`data/active.json`, `data/satcat.csv`) and the generated outputs are not tracked; see `.gitignore`.

## Quick start

Requires Python 3.10 or later.

```
python -m pip install requests pandas numpy
python rank_leo.py                  # download from CelesTrak, rank, write the top 100
python rank_leo.py --data-dir data  # rerun from the saved files
```

A run with no options downloads today's active satellites from CelesTrak, ranks every object in LEO, and writes the top 100 to `ranked_leo.csv` and `ranked_leo.json` in the current folder.

## Data sources

| Data | Source | Used for |
|---|---|---|
| General perturbations (GP) orbital elements, OMM JSON, active group | `https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json` | Orbits, perigee, element-set age, output elements |
| Satellite catalog (SATCAT) | `https://celestrak.org/satcat/records.php` (active payloads), falling back to `https://celestrak.org/pub/satcat.csv` | Object type, owner, launch date, radar cross section (RCS) |
| Exclusion-zone table (optional) | `data/exclusion_zones.csv`, maintained by hand | Class, users label, size, exclusion zone and tier per object or family |

CelesTrak updates GP data every 2 hours and refuses a repeat download of the same group within that window. A download run saves `active.json` and `satcat.csv` to `data/` (see `--save-dir`) so you can rerun with `--data-dir data`.

If the download is blocked on your network, fetch the files by hand and use `--data-dir`:

```
data/active.json  <- https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json
data/satcat.csv   <- https://celestrak.org/pub/satcat.csv
```

Only objects with perigee at or below 2,000 km and eccentricity below 0.25 are ranked, matching the LEO regimes of the Spaceflight Safety Handbook.

## How the ranking works

Each object gets a tier, an exclusion-zone volume, a size bin and a score. Objects are sorted by:

1. `TIER` ascending
2. `SCORE` descending, where `SCORE = log10(V_exclusion) + w * log10(D_rep^2)` and `D_rep` is the representative dimension of the object's size bin
3. SFSH box volume descending (orbit-regime-driven prediction uncertainty)
4. Perigee ascending (more drag, faster growth of in-track error)
5. Element-set age descending

### Tiers and classes

Inhabitable objects (the ISS, 25544, and Tiangong, 48274, by default) are tier 0; everything else is tier 1 unless the table says otherwise. Docked station modules that share a station's exact orbital elements are folded into the station row and counted in the `MODULES` column.

### Exclusion zones

Unless the table sets a shape, exclusion zones follow the FAA launch and reentry collision-avoidance criteria in 14 CFR 450.169:

| Class | Default zone |
|---|---|
| inhabitable | Ellipsoid, semi-axes 50 km radial, 200 km in-track, 50 km cross-track |
| active | Sphere, 25 km radius |
| debris | Sphere, 2.5 km radius |

With `--volume-basis sfsh`, active objects instead get the screening box for their perigee band from the 18th and 19th Space Defense Squadrons' Spaceflight Safety Handbook (half-widths in radial / in-track / cross-track):

| Band | Perigee | Half-widths (km) |
|---|---|---|
| LEO1 | up to 500 km | 0.4 / 44 / 51 |
| LEO2 | 500 to 750 km | 0.4 / 25 / 25 |
| LEO3 | 750 to 1,200 km | 0.4 / 12 / 12 |
| LEO4 | 1,200 to 2,000 km | 0.4 / 2 / 2 |

### Size bins

Size is a coarse bin by maximum dimension, solar arrays included:

| Bin | Max dimension | Representative dimension used in the score |
|---|---|---|
| XS | under 1 m | 0.5 m |
| S | 1 to 4 m | 2 m |
| M | 4 to 12 m | 6.9 m |
| L | 12 to 40 m | 21.9 m |
| XL | over 40 m | 63 m |

Each object's bin comes from the first available source:

1. `SIZE_BIN` in the table
2. `MAX_DIM_M` in the table, converted with the edges above
3. Catalog RCS, converted to an equivalent dimension with `d = 2.2 * 2 * sqrt(RCS / pi)`
4. The majority bin of the object's name family, when at least 5 members have an RCS
5. `--default-bin` (S unless changed)

The output column `SIZE_SOURCE` records which source was used.

## The exclusion-zone table: `data/exclusion_zones.csv`

The table is optional. Each row describes one object or a family of objects. For each object, the script tries all `ID` rows first, then the `NAME_REGEX` rows in file order, and uses the first row that matches. A matched object takes every non-blank value from that row and ignores later rows, even for columns the winning row leaves blank. Anything still unset falls back to the defaults above. The output column `TABLE_ROW` gives the CSV line number of the row each object matched.

| Column | Meaning |
|---|---|
| `MATCH_TYPE` | How the row selects objects: `ID` or `NAME_REGEX`, in any case. A row with any other value is skipped. |
| `MATCH` | For `ID` rows, a NORAD catalog number such as `25544`. For `NAME_REGEX` rows, a regular expression searched within the object name, ignoring case. It matches anywhere in the name, so anchor with `^` to match only at the start: `^STARLINK-` matches `STARLINK-30239` but not `XSTARLINK`. |
| `LAUNCHED_FROM` | Optional earliest launch date (YYYY-MM-DD), inclusive, compared against the SATCAT launch date. An object with no launch date in the SATCAT never matches a row that sets either launch bound. |
| `LAUNCHED_TO` | Optional latest launch date, inclusive. Use with `LAUNCHED_FROM` to split one family by generation, such as Starlink V1.5 and V2 Mini. |
| `CLASS` | `inhabitable`, `active` or `debris`, in any case. Defaults to `active`, except for the built-in station IDs. An inhabitable object gets tier 0 and the inhabitable FAA zone by default, and has docked modules folded in. |
| `USERS` | Free-text label such as `commercial` or `military (open-source reporting)`. Copied to the output; does not affect ranking. No public catalog carries this attribute, so the label is only as good as its source. |
| `TIER` | Optional integer; lower tiers rank first. Defaults to 0 for inhabitable and 1 otherwise. Use it to promote or demote an object or family regardless of size or zone volume. |
| `SIZE_BIN` | `XS`, `S`, `M`, `L` or `XL` (see Size bins). Must be uppercase: a lowercase value is silently ignored and the object falls back to its other size sources. Takes priority over every other size source. |
| `MAX_DIM_M` | Maximum dimension in meters, used only when `SIZE_BIN` is blank. When both are filled, the bin wins. |
| `SIZE_BASIS` | Free-text note on where the size came from. Not used by the script. |
| `SHAPE` | `SPHERE`, `ELLIPSOID` or `BOX`, in any case. Leave blank for the default zone. Any other value gives an undefined volume, and the object will not rank correctly. |
| `R_KM` | Radial dimension in km, required whenever `SHAPE` is set. Sphere radius, ellipsoid semi-axis or box half-width. |
| `I_KM` | In-track semi-axis or half-width in km. If blank, `R_KM` is used. |
| `C_KM` | Cross-track semi-axis or half-width in km. If blank, `R_KM` is used. |
| `SOURCE` | Citation or URL for the row's values. Not used by the script. |
| `NOTES` | Free-text caveats. Not used by the script. |

All three dimensions are measured from the object's center, so a `BOX` with 2 / 25 / 25 is 4 x 50 x 50 km overall. Volume is 4/3·π·R³ for a sphere, 4/3·π·R·I·C for an ellipsoid and 8·R·I·C for a box.

## Command-line options

`python rank_leo.py [options]`

### Where the data comes from

- **`--data-dir FOLDER`**: use files already saved in FOLDER instead of downloading. FOLDER must hold `active.json` and `satcat.csv`; if it also holds `exclusion_zones.csv`, that table is used too. With this option set, `--save-dir` is ignored.
- **`--save-dir FOLDER`** (default `data`): when downloading, also save `active.json` and `satcat.csv` here for reuse with `--data-dir`. Existing copies are overwritten, and the saved `satcat.csv` contains active payloads only.
- **`--table FILE`**: use a specific exclusion-zone table. By default the script looks for `exclusion_zones.csv` inside `--data-dir`. On a download run (no `--data-dir`), no table is used unless you name one here.

### How objects are scored

- **`--volume-basis faa|sfsh`** (default `faa`): the exclusion zone for active objects that have no shape in the table. With `faa`, every active object gets a 25 km sphere, so size bin decides their order. With `sfsh`, each gets the Spaceflight Safety Handbook box for its perigee band, so lower objects rank higher. Inhabitable objects always get the FAA ellipsoid unless the table sets a shape.
- **`--default-bin XS|S|M|L|XL`** (default `S`): the size bin for objects with no table entry, no catalog RCS and too few measured family members. Must be uppercase.
- **`--w NUMBER`** (default `0.5`): how much size counts against exclusion-zone volume in the score. `0` ignores size. Under the default `faa` basis every active object has the same volume, so `w` only matters when volumes differ: with `--volume-basis sfsh`, or for objects with a table shape.

### What gets written

- **`--list-length N`** (default `100`): how many top-ranked objects to write; `0` writes all of them. The full set is always ranked first, so the top N does not depend on N.
- **`--omit ITEM [ITEM ...]`**: leave whole groups out of the ranking. Choose from `inhabitable`, `starlink`, `iridium`, `oneweb`, `kuiper`, `qianfan`, `hulianwang` and `yaogan`. Case does not matter, and items can be separated by spaces, commas or both. Ranks are renumbered over what remains. Omitted objects still count when the script borrows sizes from family members.

### Examples

```
python rank_leo.py                                                # download, rank, write top 100
python rank_leo.py --data-dir data                                # reuse saved files
python rank_leo.py --data-dir data --volume-basis faa --w 0.5     # the defaults, stated explicitly
python rank_leo.py --data-dir data --list-length 0                # write every ranked object
python rank_leo.py --data-dir data --omit starlink --volume-basis sfsh
python rank_leo.py --data-dir data --omit Starlink oneweb         # or: --omit starlink,oneweb
```

## Outputs

Both files hold the top `--list-length` objects (default 100) in the same rank order.

- **`ranked_leo.json`**: CelesTrak OMM orbital elements for each ranked object. OMM is used rather than TLE because new catalog numbers above 99999 cannot be written in TLE format.
- **`ranked_leo.csv`**: ranking attributes for each object, including `RANK`, `TIER`, `CLASS`, `USERS`, `MODULES`, `PERIGEE_KM`, the exclusion zone (`EXCLUSION_SHAPE`, `EXCLUSION_RIC_KM`, `EXCLUSION_KM3`, `EXCLUSION_SOURCE`), size (`SIZE_BIN_USED`, `DIM_REP_M`, `SIZE_SOURCE`, `RCS`), `V_SFSH_KM3`, `SCORE`, `ELSET_AGE_D`, `EPOCH` and `TABLE_ROW`.

## Runtime considerations

CelesTrak queries have no sort order or ranking, so the full active set (about 7 MB of GP data) is always downloaded and ranked; `--list-length` only trims the outputs.

## Known limitations

- **Size data is sparse.** Public catalog RCS covers only about 3% of active LEO objects and nothing launched after March 2017. Most sizes come from family rows in the table, and several of those (OneWeb, Kuiper, Guowang) are estimates because dimensions are not published. Qianfan and about 2,500 other objects use the default bin.
- **The RCS-to-dimension factor (2.2) is calibrated on a single object**, the Hubble Space Telescope. Treat RCS-derived bins near a bin edge as uncertain.
- **The FAA zones come from a launch and reentry rule**, not from on-orbit conjunction screening. The SFSH boxes are on-orbit screening volumes, and the ISS's own debris-avoidance box is smaller than the FAA ellipsoid.
- **The Starlink generation split is by launch date** and is approximate.
- **`USERS` labels are not from any official catalog field.**

## References

- [14 CFR 450.169, Launch and reentry collision avoidance analysis requirements](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450/subpart-C/section-450.169)
- [18th and 19th Space Defense Squadrons, Spaceflight Safety Handbook for Satellite Operators](https://www.space-track.org/documents/SFS_Handbook_For_Operators_V1.7.pdf)
- [Office of Space Commerce, Conjunction Screening Test Set User's Guide (SFSH volume table)](https://space.commerce.gov/wp-content/uploads/2026/03/Conjunction_Screening_Testset_Users_Guide.pdf)
- [CelesTrak GP data formats and queries](https://celestrak.org/NORAD/documentation/gp-data-formats.php)
- [CelesTrak SATCAT format and queries](https://celestrak.org/satcat/satcat-format.php)
- [NASA Conjunction Assessment Risk Analysis (CARA)](https://www.nasa.gov/conjunction-assessment/)
- [Publicly available CARA software](https://www.nasa.gov/cara/publicly-available-cara-software/)
- [NASA CARA Analysis Tools on GitHub](https://github.com/nasa/CARA_Analysis_Tools)
