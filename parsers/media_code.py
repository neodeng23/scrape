from __future__ import annotations

import re
import unicodedata
from pathlib import Path


BRACKETED_TEXT_RE = re.compile(r"\[[^\]]*]|\([^)]*\)|\{[^}]*}")
CD_RE = re.compile(r"(?<![A-Z0-9])(CD|DISC|PART|PT)[-_. ]?\d{1,2}(?![A-Z0-9])")
DATE_RE = re.compile(r"\b20\d{2}[-_. ]\d{1,2}[-_. ]\d{1,2}\b")
WESTERN_DATE_RE = re.compile(r"\b([A-Z0-9-]{2,})[-_. ](\d{2}[.-]\d{2}[.-]\d{2})\b")
GENERAL_HYPHEN_RE = re.compile(r"\b([A-Z]{2,10})[-_ ]?(\d{2,6}[A-Z]?)\b")
# Handles cases like "259LUXU-1886" where digits precede the letter prefix.
LEADING_DIGITS_HYPHEN_RE = re.compile(r"\b(\d{2,6})([A-Z]{2,10})[-_ ]?(\d{2,6}[A-Z]?)\b")
COMPACT_RE = re.compile(r"\b([A-Z]{2,10})(\d{3,6}[A-Z]?)\b")
PREFIXED_DATE_CODE_RE = re.compile(r"\b(CARIB|CARIBBEANCOM|1PONDO|10MU|PACO)-?(\d{6})[-_ ]?(\d{2,4})\b")
NUMERIC_HYPHEN_RE = re.compile(r"\b(\d{6})[-_](\d{2,4})\b")

NOISE_TOKENS = {
    "4K",
    "8K",
    "FHD",
    "UHD",
    "HD",
    "HEVC",
    "X264",
    "X265",
    "H264",
    "H265",
    "AAC",
    "HDR",
    "DVDRIP",
    "BLURAY",
    "WEB",
    "SAMPLE",
    "SUB",
    "CHS",
    "CHT",
    "CNDUB",
}
PREFIX_BLACKLIST = NOISE_TOKENS | {"MP4", "MKV", "AVI", "MOV", "WMV", "ISO"}


def _normalize_filename(name: str) -> str:
    stem = Path(name).stem
    stem = unicodedata.normalize("NFC", stem).upper()
    stem = BRACKETED_TEXT_RE.sub(" ", stem)
    stem = DATE_RE.sub(" ", stem)
    stem = CD_RE.sub(" ", stem)
    stem = stem.replace("FC2PPV", "FC2-PPV")
    stem = stem.replace("FC2 PPV", "FC2-PPV")
    stem = stem.replace("FC2_PPV", "FC2-PPV")
    stem = stem.replace("_", "-").replace(".", "-")
    for token in NOISE_TOKENS:
        stem = re.sub(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", " ", stem)
    stem = re.sub(r"\s+", " ", stem)
    stem = re.sub(r"-{2,}", "-", stem)
    return stem.strip(" -")


def _normalize_general_code(prefix: str, digits: str) -> str | None:
    prefix = prefix.upper().strip("-_ ")
    digits = digits.upper().strip("-_ ")
    if prefix in PREFIX_BLACKLIST:
        return None
    normalized_digits = digits.rstrip("-_ ")
    trimmed_digits = normalized_digits.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    suffix = normalized_digits[len(trimmed_digits) :]
    trimmed_digits = trimmed_digits.lstrip("0") or trimmed_digits or "0"
    return f"{prefix}-{trimmed_digits}{suffix}"


def extract_media_code(name: str) -> str | None:
    normalized = _normalize_filename(name)
    if not normalized:
        return None

    western = WESTERN_DATE_RE.search(normalized)
    if western:
        prefix = western.group(1).strip("-_. ")
        if prefix not in PREFIX_BLACKLIST:
            return f"{prefix.lower()}.{western.group(2).replace('-', '.').lower()}".capitalize()

    fc2 = re.search(r"\bFC2[-_ ]?(?:PPV[-_ ]?)?(\d{5,7})\b", normalized)
    if fc2:
        return f"FC2-{fc2.group(1)}"

    heyzo = re.search(r"\bHEYZO[-_ ]?(\d{3,5})\b", normalized)
    if heyzo:
        return f"HEYZO-{heyzo.group(1)}"

    prefixed_date_code = PREFIXED_DATE_CODE_RE.search(normalized)
    if prefixed_date_code:
        return f"{prefixed_date_code.group(1)}-{prefixed_date_code.group(2)}-{prefixed_date_code.group(3)}"

    caribbean = NUMERIC_HYPHEN_RE.search(normalized)
    if caribbean:
        return f"{caribbean.group(1)}-{caribbean.group(2)}"

    leading = LEADING_DIGITS_HYPHEN_RE.search(normalized)
    if leading:
        # Skip the leading digit group; use (prefix, number) as code.
        return _normalize_general_code(leading.group(2), leading.group(3))

    general = GENERAL_HYPHEN_RE.search(normalized)
    if general:
        return _normalize_general_code(general.group(1), general.group(2))

    compact = COMPACT_RE.search(normalized)
    if compact:
        return _normalize_general_code(compact.group(1), compact.group(2))

    return None
