#!/usr/bin/env python3
"""
Immigration News Tracker - scraper

Pulls from RSS feeds, Reddit, and the Federal Register API, filters/tags
items by immigration category (H-1B, F-1/OPT, I-140, PERM, Green Card),
dedupes, and writes docs/data/news.json for the static site to render.

Every item keeps its original source name + link, since the site displays
that as a citation next to every piece of news.

Designed to be forgiving: if one source fails (dead feed, timeout, rate
limit), that source is skipped with a logged warning rather than failing
the whole run.
"""

import json
import re
import sys
import time
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from html import unescape

import requests
import feedparser
from dateutil import parser as dateparser

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.json"
OUTPUT_FILE = ROOT / "docs" / "data" / "news.json"

REQUEST_TIMEOUT = 20
USER_AGENT = "immigration-news-tracker/1.0 (+https://github.com/; personal news aggregator)"
MAX_AGE_DAYS = 60          # drop items older than this
MAX_ITEMS = 400            # cap total items kept in the JSON file
SUMMARY_MAX_CHARS = 320

HEADERS = {"User-Agent": USER_AGENT}

# ---------------------------------------------------------------------------
# Category keyword rules. Each category maps to a list of regex patterns
# (case-insensitive). Edit freely to tune what gets picked up.
# ---------------------------------------------------------------------------
CATEGORY_PATTERNS = {
    "H-1B": [
        r"\bh-?1b\b", r"\bh-?1b1\b", r"h-1b cap", r"h-1b lottery", r"h-1b registration",
        r"specialty occupation",
    ],
    "F-1 / OPT / CPT": [
        r"\bf-?1\b visa", r"\bf-?1 student", r"\bopt\b", r"stem opt", r"\bcpt\b",
        r"student visa", r"\bsevis\b", r"day-1 cpt", r"curricular practical training",
        r"optional practical training",
    ],
    "I-140": [
        r"\bi-?140\b", r"immigrant petition for alien worker", r"eb-1", r"eb-2", r"eb-3",
        r"niw\b", r"national interest waiver",
    ],
    "PERM": [
        r"\bperm\b", r"labor certification", r"prevailing wage", r"\bpwd\b",
        r"program electronic review management",
    ],
    "Green Card": [
        r"green card", r"permanent resident", r"\bi-?485\b", r"adjustment of status",
        r"visa bulletin", r"diversity visa", r"\bdv lottery\b", r"immigrant visa",
    ],
}

ALL_PATTERNS = [(cat, re.compile(p, re.IGNORECASE)) for cat, pats in CATEGORY_PATTERNS.items() for p in pats]


def log(msg):
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", file=sys.stderr)


def strip_html(raw):
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text, n=SUMMARY_MAX_CHARS):
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut + "..."


def categorize(title, summary):
    haystack = f"{title} {summary}"
    found = []
    for cat, pattern in ALL_PATTERNS:
        if pattern.search(haystack) and cat not in found:
            found.append(cat)
    return found


def make_id(url, title):
    return hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()[:16]


def parse_date_safe(value):
    if not value:
        return None
    try:
        dt = dateparser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_rss(source):
    name = source["name"]
    url = source["url"]
    always = source.get("always_include", False)
    label = source.get("always_include_label", name)
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"feedparser could not parse content (bozo={parsed.bozo_exception})")
        for entry in parsed.entries:
            title = strip_html(entry.get("title", "")).strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            raw_summary = entry.get("summary", "") or entry.get("description", "")
            summary = truncate(strip_html(raw_summary))
            published = (
                entry.get("published") or entry.get("updated") or entry.get("pubDate")
            )
            pub_dt = parse_date_safe(published)
            cats = categorize(title, summary)
            if not cats and not always:
                continue
            items.append({
                "id": make_id(link, title),
                "title": title,
                "summary": summary,
                "url": link,
                "source_name": name,
                "published": pub_dt.isoformat() if pub_dt else None,
                "categories": cats if cats else [label],
            })
        log(f"OK   RSS   {name}: {len(items)} matching items ({len(parsed.entries)} total entries)")
    except Exception as e:
        log(f"WARN RSS   {name}: skipped due to error: {e}")
    return items


def fetch_reddit(source):
    name = source["name"]
    url = source["url"]
    always = source.get("always_include", False)
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        children = data.get("data", {}).get("children", [])
        for child in children:
            post = child.get("data", {})
            title = strip_html(post.get("title", "")).strip()
            permalink = post.get("permalink", "")
            link = f"https://www.reddit.com{permalink}" if permalink else post.get("url", "")
            if not title or not link:
                continue
            # skip low-signal posts
            if post.get("stickied"):
                continue
            summary = truncate(strip_html(post.get("selftext", "")) or "Discussion thread on Reddit.")
            created = post.get("created_utc")
            pub_dt = datetime.fromtimestamp(created, tz=timezone.utc) if created else None
            cats = categorize(title, summary)
            if not cats and not always:
                continue
            items.append({
                "id": make_id(link, title),
                "title": title,
                "summary": summary,
                "url": link,
                "source_name": f"Reddit - {name}",
                "published": pub_dt.isoformat() if pub_dt else None,
                "categories": cats if cats else [name],
            })
        log(f"OK   REDDIT {name}: {len(items)} matching items ({len(children)} total posts)")
    except Exception as e:
        log(f"WARN REDDIT {name}: skipped due to error: {e}")
    return items


def fetch_federal_register(config):
    name = config["name"]
    base_url = config["base_url"]
    items = []
    try:
        params = {
            "per_page": config.get("per_page", 40),
            "order": "newest",
            "fields[]": ["title", "html_url", "publication_date", "abstract", "agencies", "type"],
        }
        for agency in config.get("agencies", []):
            params.setdefault("conditions[agencies][]", []).append(agency)

        resp = requests.get(base_url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        for doc in results:
            title = strip_html(doc.get("title", "")).strip()
            link = doc.get("html_url", "")
            if not title or not link:
                continue
            summary = truncate(strip_html(doc.get("abstract", "")) or "Federal Register document.")
            pub_dt = parse_date_safe(doc.get("publication_date"))
            cats = categorize(title, summary)
            label = config.get("always_include_label", name)
            items.append({
                "id": make_id(link, title),
                "title": title,
                "summary": summary,
                "url": link,
                "source_name": f"Federal Register ({doc.get('type', 'Document')})",
                "published": pub_dt.isoformat() if pub_dt else None,
                "categories": cats if cats else [label],
            })
        log(f"OK   FEDREG {name}: {len(items)} items")
    except Exception as e:
        log(f"WARN FEDREG {name}: skipped due to error: {e}")
    return items


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    config = json.loads(SOURCES_FILE.read_text())
    all_items = []

    for src in config.get("rss_sources", []):
        all_items.extend(fetch_rss(src))
        time.sleep(0.5)

    for src in config.get("reddit_sources", []):
        all_items.extend(fetch_reddit(src))
        time.sleep(0.5)

    if config.get("federal_register"):
        all_items.extend(fetch_federal_register(config["federal_register"]))

    # Dedupe by id (url+title hash), keep the first occurrence.
    seen = set()
    deduped = []
    for item in all_items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)

    # Drop items with no parseable date older than cutoff; keep undated items
    # (some feeds omit dates) but sort them to the bottom.
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    def keep(item):
        if item["published"] is None:
            return True
        try:
            return dateparser.parse(item["published"]) >= cutoff
        except Exception:
            return True

    deduped = [i for i in deduped if keep(i)]

    def sort_key(item):
        if item["published"]:
            try:
                return dateparser.parse(item["published"])
            except Exception:
                pass
        return datetime.min.replace(tzinfo=timezone.utc)

    deduped.sort(key=sort_key, reverse=True)
    deduped = deduped[:MAX_ITEMS]

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "item_count": len(deduped),
        "items": deduped,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log(f"DONE Wrote {len(deduped)} items to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
