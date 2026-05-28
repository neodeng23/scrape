# Development Plan

## Goal

Build an independent headless media scraper in `d:\tools\scrape`.

The tool must:

- read fixed constants from a local config file
- scan a configured source directory
- identify supported media files
- scrape metadata using locally implemented logic
- create one output folder per media item
- place the media file and scraped assets into the output folder
- run without GUI or web UI

## Phase 0: Correct The Direction

1. Remove the current runtime dependence on `mdcx`.
2. Replace the wrapper-style startup flow with a fully local implementation.
3. Keep only reference artifacts that are still useful, such as extracted site lists or notes.

## Phase 1: Local Project Skeleton

1. Define local package structure under this workspace.
2. Keep constants in a dedicated local config module.
3. Add local logging, exceptions, and basic runtime bootstrap.

Planned modules:

- `config.py`
- `main.py`
- `scanner.py`
- `models.py`
- `logging_utils.py`
- `writers/`
- `sources/`
- `parsers/`

## Phase 2: Media Discovery

1. Recursively scan `SOURCE_DIR`.
2. Filter by supported media extensions.
3. Ignore output and failed directories to avoid self-rescan.
4. Extract candidate identifiers from filenames.
5. Build a normalized media task list.

## Phase 3: Scrape Source Abstraction

1. Define a local source adapter interface.
2. Add local request utilities.
3. Start with a minimal number of practical sources.
4. Use local site configuration or extracted site data only as input data, not as imported code.

Expected outcome:

- one local request layer
- one local source registry
- one local normalization pipeline for source results

## Phase 4: Metadata Model And Merge

1. Define a local metadata model.
2. Normalize fields from different sources into one schema.
3. Merge competing results by local priority rules.
4. Preserve source attribution for debugging.

Core fields to support first:

- id / number
- title
- release date
- runtime
- studio / maker / label
- series
- actors
- tags
- cover / poster / fanart URLs
- trailer URL when available
- outline / plot

## Phase 5: Output Builder

1. Build target folder names.
2. Move or copy the media file into its output folder.
3. Download artwork into the folder.
4. Generate NFO locally.
5. Write a structured result summary log.

Initial output target:

- media file
- `.nfo`
- poster
- thumb
- fanart
- optional trailer

## Phase 6: Failure Handling

1. Route failed items into `FAILED_DIR` or a failure log flow.
2. Record failure reason per file.
3. Keep rerun behavior deterministic.

## Phase 7: Verification

1. Test filename parsing with representative samples.
2. Test task generation from nested directories.
3. Test one full scrape path on a small sample set.
4. Confirm output folder structure matches expectations.

## Implementation Order

1. Remove the current `mdcx` runtime wrapper logic.
2. Establish local data models and scanner.
3. Implement local scraping source abstraction.
4. Implement the first usable source adapters.
5. Implement output writing and file organization.
6. Run sample verification and refine.

## Definition Of Done

The project is considered usable when:

1. `main.py` runs without importing `mdcx`
2. constants are read only from the local config file
3. media files are discovered from `SOURCE_DIR`
4. metadata is scraped by locally implemented code
5. each successful item is organized into an output folder under `OUTPUT_DIR`
6. each folder contains the media file and metadata assets
7. failures are recorded clearly and do not block the whole run
