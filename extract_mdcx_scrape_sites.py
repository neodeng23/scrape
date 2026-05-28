from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
URL_RE = re.compile(r"https?://[^\s\"'`<>]+")
ROOT_RE = re.compile(r"^(https?://[^/\s\"'`<>{}]+)")
TEMPLATE_HINTS = (
    "search",
    "detail",
    "video",
    "movie",
    "movies",
    "scene",
    "scenes",
    "player",
    "product",
    "article",
    "works",
    "graphql",
    "api/",
    "vl_searchbyid.php",
    "search.php?",
    "search_result?",
    "result_published",
    "playon.aspx",
)


@dataclass(frozen=True)
class CrawlerSite:
    website: str
    enum_name: str
    module_name: str
    file_path: Path


def render_joined_str(node: ast.JoinedStr) -> str:
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            expr = ast.unparse(value.value) if hasattr(ast, "unparse") else "expr"
            parts.append("{" + expr + "}")
    return "".join(parts)


def string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return render_joined_str(node)
    return None


def normalize_url(url: str) -> str:
    return url.rstrip(")").rstrip("]").rstrip(",").rstrip(".")


def category_for_url(url: str) -> str:
    lowered = url.lower()
    if "graphql" in lowered or "/api/" in lowered or "api." in lowered:
        return "api"
    if any(token in lowered for token in ["preview", "sample", "trailer", ".m3u8", ".mp4"]):
        return "media"
    if any(
        token in lowered
        for token in [
            "search",
            "keyword=",
            "query=",
            "?q=",
            "searchstr=",
            "search_text=",
            "bysearch",
            "result_published",
        ]
    ):
        return "search"
    if any(
        token in lowered
        for token in [
            "detail",
            "movie",
            "video",
            "product",
            "works",
            "article",
            "albums",
            "scene",
            "scenes",
            "movies",
            "item",
            "soft.phtml",
            "/v/",
            "playon.aspx",
        ]
    ):
        return "detail"
    return "other"


def looks_like_selector(value: str) -> bool:
    stripped = value.strip()
    if stripped.startswith(("//", ".//", "./", "../")):
        return True
    selector_tokens = (
        "@href",
        "@src",
        "text(",
        "contains(@",
        "[@",
        "following-sibling::",
        "::",
    )
    return any(token in stripped for token in selector_tokens)


def is_path_like_template(value: str) -> bool:
    stripped = value.strip()
    if not stripped or not stripped.isascii():
        return False
    if " " in stripped:
        return False
    return bool(re.fullmatch(r"[\w{}:/?&.=+\-#%]+", stripped))


def extract_string_urls(tree: ast.AST) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        value = string_value(node)
        if not value or "http://" not in value and "https://" not in value:
            continue
        urls: list[str] = []
        if value.startswith(("http://", "https://")) and ROOT_RE.match(value):
            urls = [normalize_url(value)]
        else:
            urls = [normalize_url(match.group(0)) for match in URL_RE.finditer(value)]
        if not urls and value.startswith(("http://", "https://")):
            continue
        for url in urls:
            lineno = getattr(node, "lineno", 0)
            key = (lineno, url)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "line": lineno,
                    "template": url,
                    "category": category_for_url(url),
                }
            )
    items.sort(key=lambda item: (item["line"], item["template"]))
    return items


def extract_dynamic_templates(tree: ast.AST) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        value = string_value(node)
        if not value:
            continue
        lowered = value.lower()
        if not any(token in lowered for token in TEMPLATE_HINTS):
            continue
        if value.startswith(("http://", "https://")):
            continue
        if looks_like_selector(value):
            continue
        if not is_path_like_template(value):
            continue
        lineno = getattr(node, "lineno", 0)
        template = normalize_url(value)
        key = (lineno, template)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "line": lineno,
                "template": template,
                "category": category_for_url(template),
            }
        )
    items.sort(key=lambda item: (item["line"], item["template"]))
    return items


def extract_default_base_urls(tree: ast.AST, enum_name: str) -> list[str]:
    urls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "get_site_url":
            continue
        if len(node.args) < 2:
            continue
        website_arg = node.args[0]
        default_arg = node.args[1]
        if not (
            isinstance(website_arg, ast.Attribute)
            and isinstance(website_arg.value, ast.Name)
            and website_arg.value.id == "Website"
            and website_arg.attr == enum_name
        ):
            continue
        default_url = string_value(default_arg)
        if default_url and default_url.startswith(("http://", "https://")):
            urls.add(default_url)
    return sorted(urls)


def extract_website_enum(repo_root: Path) -> dict[str, str]:
    file_path = repo_root / "mdcx" / "config" / "enums.py"
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    websites: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "Website":
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign) or len(item.targets) != 1:
                continue
            target = item.targets[0]
            if not isinstance(target, ast.Name):
                continue
            value = string_value(item.value)
            if value:
                websites[target.id] = value
    return websites


def extract_crawler_sites(repo_root: Path, websites: dict[str, str]) -> list[CrawlerSite]:
    init_path = repo_root / "mdcx" / "crawlers" / "__init__.py"
    tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    sites: list[CrawlerSite] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        for element in node.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
                continue
            left, right = element.elts
            if not (
                isinstance(left, ast.Attribute)
                and isinstance(left.value, ast.Name)
                and left.value.id == "Website"
                and left.attr in websites
            ):
                continue
            if not isinstance(right, ast.Attribute):
                continue
            if not isinstance(right.value, ast.Name):
                continue
            module_name = right.value.id
            enum_name = left.attr
            site_path = repo_root / "mdcx" / "crawlers" / f"{module_name}.py"
            if not site_path.exists():
                continue
            sites.append(
                CrawlerSite(
                    website=websites[enum_name],
                    enum_name=enum_name,
                    module_name=module_name,
                    file_path=site_path,
                )
            )

    sites.append(
        CrawlerSite(
            website=websites["DMM"],
            enum_name="DMM",
            module_name="dmm_new",
            file_path=repo_root / "mdcx" / "crawlers" / "dmm_new" / "__init__.py",
        )
    )
    sites.append(
        CrawlerSite(
            website=websites["JAVDB"],
            enum_name="JAVDB",
            module_name="javdb_new",
            file_path=repo_root / "mdcx" / "crawlers" / "javdb_new.py",
        )
    )

    unique: dict[str, CrawlerSite] = {site.website: site for site in sites}
    return sorted(unique.values(), key=lambda item: item.website)


def roots_from_urls(urls: list[str]) -> list[str]:
    roots: set[str] = set()
    for url in urls:
        match = ROOT_RE.match(url)
        if match:
            roots.add(match.group(1))
    return sorted(roots)


def group_urls(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in items:
        grouped[item["category"]].append(item["template"])
    for key in list(grouped):
        grouped[key] = sorted(dict.fromkeys(grouped[key]))
    return {key: grouped[key] for key in sorted(grouped)}


def extract_official_sites(repo_root: Path) -> list[dict[str, Any]]:
    manual_path = repo_root / "mdcx" / "manual.py"
    tree = ast.parse(manual_path.read_text(encoding="utf-8"), filename=str(manual_path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "ManualConfig":
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign) or len(item.targets) != 1:
                continue
            target = item.targets[0]
            if not isinstance(target, ast.Name) or target.id != "OFFICIAL":
                continue
            if not isinstance(item.value, ast.Dict):
                raise ValueError("ManualConfig.OFFICIAL is not a dict literal")
            entries: list[dict[str, Any]] = []
            for key_node, value_node in zip(item.value.keys, item.value.values, strict=True):
                key = string_value(key_node)
                value = string_value(value_node)
                if not key or not value:
                    continue
                prefixes = [part.strip() for part in value.split("|") if part.strip()]
                entries.append(
                    {
                        "base_url": key,
                        "prefixes": prefixes,
                        "prefix_count": len(prefixes),
                    }
                )
            return sorted(entries, key=lambda item: item["base_url"])
    return []


def build_manifest(repo_root: Path) -> dict[str, Any]:
    websites = extract_website_enum(repo_root)
    crawler_sites = extract_crawler_sites(repo_root, websites)
    supplemental_files = {
        "iqqtv": [repo_root / "mdcx" / "crawlers" / "iqqtv.py"],
        "javlibrary": [repo_root / "mdcx" / "crawlers" / "javlibrary.py"],
        "getchu_dmm": [repo_root / "mdcx" / "crawlers" / "getchu.py"],
    }
    supplemental_raw_urls = {
        "avsox": ["https://tellme.pw/avsox", "https://avsox.click"],
    }

    site_entries: list[dict[str, Any]] = []
    for site in crawler_sites:
        trees: list[tuple[Path, ast.AST]] = [
            (site.file_path, ast.parse(site.file_path.read_text(encoding="utf-8"), filename=str(site.file_path)))
        ]
        for extra_file in supplemental_files.get(site.website, []):
            trees.append((extra_file, ast.parse(extra_file.read_text(encoding="utf-8"), filename=str(extra_file))))

        raw_items: list[dict[str, Any]] = []
        dynamic_items: list[dict[str, Any]] = []
        default_base_urls: set[str] = set()
        scanned_files: list[str] = []
        for file_path, tree in trees:
            scanned_files.append(str(file_path))
            raw_items.extend(extract_string_urls(tree))
            dynamic_items.extend(extract_dynamic_templates(tree))
            default_base_urls.update(extract_default_base_urls(tree, site.enum_name))
        for raw_url in supplemental_raw_urls.get(site.website, []):
            raw_items.append(
                {
                    "line": 0,
                    "template": raw_url,
                    "category": category_for_url(raw_url),
                }
            )

        grouped = group_urls(raw_items)
        dynamic_grouped = group_urls(dynamic_items)
        raw_urls = [item["template"] for item in raw_items]
        domains = roots_from_urls(sorted(default_base_urls) + raw_urls)
        site_entries.append(
            {
                "website": site.website,
                "enum_name": site.enum_name,
                "module_name": site.module_name,
                "file": str(site.file_path),
                "scanned_files": scanned_files,
                "customizable_base_url": bool(default_base_urls),
                "default_base_urls": sorted(default_base_urls),
                "domains": domains,
                "categorized_urls": grouped,
                "dynamic_templates": dynamic_grouped,
                "raw_urls": sorted(dict.fromkeys(raw_urls)),
            }
        )

    official_sites = extract_official_sites(repo_root)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "format_version": 1,
        "crawler_sites": site_entries,
        "official_sites": official_sites,
        "summary": {
            "crawler_site_count": len(site_entries),
            "official_site_count": len(official_sites),
            "official_prefix_count": sum(item["prefix_count"] for item in official_sites),
        },
    }


def main() -> None:
    repo_root = Path(r"D:\tools\mdcx")
    output_path = Path(r"D:\tools\scrape\mdcx_scrape_sites.json")
    manifest = build_manifest(repo_root)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")
    print(
        json.dumps(
            {
                "crawler_site_count": manifest["summary"]["crawler_site_count"],
                "official_site_count": manifest["summary"]["official_site_count"],
                "official_prefix_count": manifest["summary"]["official_prefix_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
