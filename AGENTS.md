# Project Constraints

## Core Rule

`D:\tools\mdcx` is a reference repository only.

It may be read to understand ideas, flow, site coverage, field structure, and useful functions, but it must not be used as this project's runtime engine.

## Non-Negotiable Constraints

1. Do not import project code from `D:\tools\mdcx` at runtime.
2. Do not build a wrapper, shell, launcher, adapter, or thin facade around `mdcx`.
3. Do not copy the architecture blindly from `mdcx`; only reference behavior and useful ideas.
4. Do not inherit Python version requirements from `mdcx`.
5. Do not inherit dependency choices from `mdcx` unless they are independently justified for this project.
6. All runnable code for this project must live in the current workspace: `d:\tools\scrape`.
7. This project is headless only. No GUI and no web UI are required.
8. Runtime constants must be managed locally in a dedicated config file in this workspace.
9. The tool must accept a fixed source directory and a fixed output directory from local config.
10. The tool must scan media files from the source directory, scrape metadata, and write organized output to the output directory.
11. The output for each media item should be a folder containing the media file plus scraped metadata assets such as NFO and images.
12. If a capability is not implemented locally in this workspace, implement it here rather than delegating execution to `mdcx`.

## Reference Usage Policy

Allowed reference usage:

- Study scraper flow and file organization ideas
- Study site lists and endpoint patterns
- Study metadata field naming and output structure
- Study parsing strategy for media filenames
- Study how different scrape sources may be prioritized or merged

Not allowed:

- Importing `mdcx.*`
- Calling `mdcx` as a library
- Reusing `mdcx` as the active scrape engine
- Treating `mdcx` dependency or Python version as this project's requirement

## Current Correction

The current `mdcx`-based prototype in this workspace is considered a temporary wrong direction and should be replaced by an independent implementation.
