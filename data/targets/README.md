# Target lists

`example_targets.csv` is a **format template**, not real data. Replace it with
your own list.

## Required columns

| Purpose | Accepted names (auto-detected) |
|---|---|
| Source ID | `GaiaDR3`, `gaia_dr3`, `source_id`, `SOURCE_ID` … |
| Right ascension (deg) | `RAdeg`, `ra`, `RA`, `ra_deg` … |
| Declination (deg) | `DEdeg`, `dec`, `DE`, `dec_deg` … |

Keep IDs as text so a spreadsheet does not round a 19-digit number.

## Optional columns

A **grouping column** (`group`, `field`, `sample`, `cluster`, `Name` …) gives
each target a label stored in filenames and metadata and used for `group:` in the config. Any
other column can be used as a filter:

```yaml
group: my_field
filters:
  Quality: good
  SampleSet: 2
```

## Where to get targets

Anything with coordinates works: a cross-match you made yourself, a VizieR
query, a cluster-membership catalogue, or a list of known variables from
VSX, Gaia DR3 or an ATLAS variable catalogue. The pipeline does not care how
the list was built.


The [ATLAS data directory](http://dtn-itc.ifa.hawaii.edu/atlas/atclass/)
is an additional resource for images and detection-classification products.
It is not a direct GROOVE light-curve input. Existing per-source photometry
from an archive or extraction workflow can instead be supplied through
`input_folder` and analysed with `--skip-download`.
