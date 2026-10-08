# Documentation

Start with the [main README](../README.md) for installation, the demo and a first
analysis. Each guide below has a stable filename and is updated in place.

| Guide | What it covers |
|---|---|
| [Stages](stages.md) | Inputs, outputs and individual analysis stages |
| [Data workflows](data_workflows.md) | Existing photometry, skipping stages and adapting other surveys |
| [Configuration](configuration.md) | Settings, defaults, filters and plot selection |
| [Restarts](restarts.md) | Automatic resume, output repair and deliberate recalculation |
| [Map controls](map_controls.md) | Dataset shapes, highlighting, comparison and zoom |
| [Morphology](morphology_details.md) | Features, rules and saved models |
| [Linux/WSL validation](linux_validation.md) | Practical end-to-end testing commands |
| [Validation evidence](validation.md) | Checks completed and remaining scientific/platform limits |

Use `groove --help` to list commands and, for example, `groove periods --help`
for stage options. Analysis commands use `-c`/`--config`; most scientific
settings belong in YAML.

Version changes are recorded in [CHANGELOG.md](../CHANGELOG.md). Older detailed
release and validation documents remain available in Git history rather than
accumulating in the current documentation tree.
