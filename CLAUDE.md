# Project Constraints

## Core Info

This is a headless JAV metadata scraper for Emby/Jellyfin/Kodi.

**What it does**: scan video files → extract media codes (番号) → scrape metadata from multiple sources → generate Emby-compatible NFO + images → organize into output folders.

## Architecture

9 Python files, no deep nesting:

```
scrape.py            # Entry point + main loop + CLI (--dry-run, --config)
config.py            # Load config.yaml with required-field validation
config.yaml          # User config (paths, network, output behavior, proxy)
sites.yaml           # Scraping source URLs and cookies (separate from user config)
models.py            # Movie dataclass (only one model)
parser.py            # Filename → media code extraction (regex)
providers.py         # Provider registry + sites.yaml loader + HTTP + merge
provider_javdb.py    # JavDB scraper
provider_javbus.py   # JavBus scraper
nfo.py               # Emby-compatible NFO XML generation
output.py            # Folder creation + image download + media placement
requirements.txt
tests/
```

## Key Design Decisions

1. **Provider = one module** exposing `search(code, session, config) -> Movie | None`, no ABC/base class. Self-registers via `providers.register()` at module level.
2. **Config split**: `config.yaml` for user settings, `sites.yaml` for site URLs/cookies. Changing a site URL doesn't touch user config.
3. **Only one dataclass** (`Movie`). Everything else uses plain dicts/tuples at point of use.
4. **NFO naming**: `{video_filename}.nfo` (matches video name, better Emby compatibility than `movie.nfo`).
5. **retries=2** means 3 total attempts (1 initial + 2 retries).

## How to Add a New Provider

1. Create `provider_xxx.py` with `search(code, session, config) -> Movie | None`
2. Add `providers.register("xxx", sys.modules[__name__])` at bottom
3. Add xxx entry in `sites.yaml`
4. Add `"xxx"` to `provider_order` in `config.yaml`
5. Add `import provider_xxx` in `scrape.py`

## Known Issues

### JavDB
- Connection timeout from mainland China (Cloudflare + DNS). Need proxy (`proxy_url` in config.yaml) or browser cookies.
- May also trigger Cloudflare JS Challenge even with proxy — `cloudscraper` is in requirements.txt but not integrated yet.

### JavBus
- Server requires **age verification quiz** (traffic law questions), not bypassable programmatically.
- User must pass quiz in browser, then export cookies to `sites.yaml` (`cookies` field).
- CSS selectors are based on common JavBus HTML structure but **NOT verified against real pages** yet (couldn't get past verification). May need adjustment:
  - Title: `h3`
  - Cover: `a.bigImage` href + inner `img` src
  - Info fields: `.info p` → `span.header`
  - Actors: `a.avatar-box` → `img` title/alt
  - Genres: `.info p` containing "類別"/"类别" → `a[href]`
  - Samples: `#sample-waterfall a.sample-box`

## Output Structure (Emby-compatible)

```
OUTPUT_DIR/
  .scrape/
    success.txt        # Processed file paths (incremental)
    failed.jsonl       # Failure records
    scrape.log
  SSIS-001 Title/
    SSIS-001.mp4
    SSIS-001.nfo
    metadata.json
    poster.jpg
    fanart.jpg
    thumb.jpg
    extrafanart/
      fanart1.jpg
```

## Commands

```powershell
python scrape.py              # Run
python scrape.py --dry-run    # Preview only
python -m pytest tests/ -v   # Tests
```

## Reference Projects (design inspiration)

- **MetaTube** (Go, 4.2k stars): https://github.com/metatube-community/metatube-sdk-go — provider interface, self-registration, priority ranking, 34 providers
- **JavSP** (Python): https://github.com/Yuukiy/JavSP — convention-based providers, first-wins merge, YAML config, cloudscraper
- **Emby NFO spec**: https://kodi.wiki/view/NFO_files/Movies
