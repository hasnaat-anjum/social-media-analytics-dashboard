"""CSV importers: read the exports every platform already gives you.

Each platform's analytics export has different column names, so import
works by *alias matching*: headers are normalised (lowercased, punctuation
stripped) and matched against the alias lists below.  That means the
tool accepts the real Instagram/Facebook/TikTok/LinkedIn/X exports as
well as hand-made spreadsheets, as long as there is a date column and
at least one metric column.

Platform detection, in order:
1. ``--platform`` on the command line (explicit wins).
2. A "Platform" column in the file.
3. Distinctive headers (e.g. TikTok's "Video views", X's "Tweet ID").
4. "generic" — the file is treated as one platform's data.

Re-importing the same file twice never duplicates posts: a post's
identity is ``platform + post_id`` (or platform + caption + date when
the export has no IDs), and repeats are skipped and counted.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from typing import Optional

from .models import Post, normalise_platform
from .parseutils import normalise_header, parse_date, parse_number

# Field -> list of normalised header aliases.  The normalised form has
# no spaces or punctuation, e.g. "Media type" -> "mediatype".
FIELD_ALIASES = {
    "post_id": ["postid", "id", "videoid", "tweetid", "posturl", "url", "link"],
    "date": ["date", "datetime", "posted", "published", "publisheddate", "postdate", "time"],
    "caption": ["caption", "message", "text", "description", "content", "posttext", "tweettext"],
    "content_type": ["mediatype", "type", "contenttype", "format", "posttype", "mediakind"],
    "likes": ["likes", "like", "reactions", "favourites", "favorites"],
    "comments": ["comments", "comment", "replies"],
    "shares": ["shares", "share", "reposts", "retweets", "repost"],
    "saves": ["saves", "save", "bookmarks"],
    "reach": ["reach", "accountsreached", "uniqueviews", "peopleReached",
              "postreach", "lifetimeposttotalreach"],
    "impressions": ["impressions", "views", "videoviews", "postviews", "seen",
                    "lifetimeposttotalimpressions"],
    "clicks": ["clicks", "linkclicks", "click", "profileclicks", "postclicks"],
    "followers_at_post": ["followers", "followersattime", "audience", "followerscount"],
    "url": ["posturl", "url", "link", "permalink"],
    "platform": ["platform", "channel", "network", "socialnetwork"],
}

# Distinctive headers that identify a platform even without a column.
# Checked in this order: a file matching an earlier platform never
# falls through to a later one (e.g. Facebook's "Reactions" must not
# make it look like LinkedIn — Facebook is checked first).
PLATFORM_SIGNATURES = {
    "tiktok": ["videoviews", "videoid", "videolikes"],
    "x": ["tweetid", "tweettext", "retweets"],
    "instagram": ["saves", "mediatype", "accountsreached"],
    "facebook": ["postclicks", "peoplereached", "lifetimeposttotalreach"],
    "linkedin": ["reactions", "reposts", "posturl"],
}

# A file must have a date column and at least one of these to import.
METRIC_FIELDS = ("likes", "comments", "shares", "saves", "reach", "impressions", "clicks")


class ImportError_(ValueError):
    """Raised when a file cannot be imported at all (bad headers, etc.)."""


class ImportResult:
    """Outcome of one import: what landed, what was skipped, and why."""

    def __init__(self) -> None:
        self.imported: list[Post] = []
        self.skipped_duplicates: int = 0
        self.skipped_bad_rows: int = 0
        self.errors: list[str] = []
        self.platform: str = "generic"
        self.rows_seen: int = 0

    @property
    def total(self) -> int:
        return len(self.imported)


def _map_columns(fieldnames: list[str]) -> dict[str, str]:
    """Map normalised CSV headers onto Post fields.

    Returns {field: original_header}.  A header maps to the first field
    whose alias list contains it; unknown headers are ignored.
    """
    mapping: dict[str, str] = {}
    for header in fieldnames:
        norm = normalise_header(header)
        for field_name, aliases in FIELD_ALIASES.items():
            if norm in aliases and field_name not in mapping:
                mapping[field_name] = header
                break
    return mapping


def _detect_platform(fieldnames: list[str], rows: list[dict]) -> str:
    """Guess the platform from the file.

    A Platform column wins (first non-empty value).  Otherwise the
    distinctive headers decide, in signature order — an earlier
    platform never falls through to a later one.
    """
    for row in rows:
        for header in fieldnames:
            if normalise_header(header) == "platform" and row.get(header):
                return normalise_platform(row[header])
    normalised = {normalise_header(h) for h in fieldnames}
    for platform, signatures in PLATFORM_SIGNATURES.items():
        if any(sig in normalised for sig in signatures):
            return platform
    return "generic"


def read_csv_text(text: str) -> tuple[list[str], list[dict]]:
    """Parse CSV text (handles a UTF-8 BOM and \r\n line endings)."""
    text = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportError_("File has no header row.")
    fieldnames = [h for h in reader.fieldnames if h is not None]
    rows = [row for row in reader if any(
        (v or "").strip() for v in row.values() if v is not None
    )]
    return fieldnames, rows


def import_posts_from_text(
    text: str,
    platform: Optional[str] = None,
    existing_keys: Optional[set] = None,
    default_followers: int = 0,
) -> ImportResult:
    """Import posts from CSV text.  Pure function — easy to test."""
    result = ImportResult()
    fieldnames, rows = read_csv_text(text)
    mapping = _map_columns(fieldnames)
    result.rows_seen = len(rows)

    if "date" not in mapping:
        raise ImportError_(
            "No date column found. Expected one of: Date, Posted, "
            "Published, Publish date."
        )
    if not any(field in mapping for field in METRIC_FIELDS):
        raise ImportError_(
            "No metric column found. Expected at least one of: Likes, "
            "Comments, Shares, Saves, Reach, Impressions, Clicks."
        )

    detected = _detect_platform(fieldnames, rows)
    result.platform = normalise_platform(platform) if platform else detected
    seen = set(existing_keys or set())

    for index, row in enumerate(rows, start=2):  # row 1 is the header
        date_raw = row.get(mapping["date"], "")
        date = parse_date(date_raw)
        if date is None:
            result.skipped_bad_rows += 1
            result.errors.append(f"Row {index}: cannot parse date '{date_raw}'.")
            continue

        def get(field_name: str, default: str = "") -> str:
            header = mapping.get(field_name)
            if header is None:
                return default
            value = row.get(header)
            return default if value is None else value

        # A "Platform" column can override the file-level platform
        # per row (handy for a combined export from several accounts).
        row_platform = result.platform
        if "platform" in mapping and get("platform"):
            row_platform = normalise_platform(get("platform"))

        post = Post(
            platform=row_platform,
            date=date,
            caption=get("caption").strip(),
            content_type=get("content_type"),
            post_id=get("post_id").strip(),
            likes=parse_number(get("likes")),
            comments=parse_number(get("comments")),
            shares=parse_number(get("shares")),
            saves=parse_number(get("saves")),
            reach=parse_number(get("reach")),
            impressions=parse_number(get("impressions")),
            clicks=parse_number(get("clicks")),
            followers_at_post=parse_number(get("followers_at_post")) or default_followers,
            url=get("url").strip(),
        )
        key = post.key()
        if key in seen:
            result.skipped_duplicates += 1
            continue
        seen.add(key)
        result.imported.append(post)

    return result


def import_posts_from_file(
    path: str,
    platform: Optional[str] = None,
    existing_keys: Optional[set] = None,
    default_followers: int = 0,
) -> ImportResult:
    """Import posts from a CSV file on disk."""
    if not os.path.exists(path):
        raise ImportError_(f"File not found: {path}")
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return import_posts_from_text(
            handle.read(), platform, existing_keys, default_followers
        )


def sample_csv(platform: str) -> str:
    """Return a small example export for a platform (used by --example)."""
    samples = {
        "instagram": (
            "Date,Caption,Media type,Likes,Comments,Shares,Saves,Reach,Impressions\n"
            "2026-11-02 19:00,5 free tools every freelancer needs #freelance #tools,Reel,842,96,41,128,12400,15800\n"
            "2026-11-04 12:30,My morning routine as a remote worker,Image,231,18,4,22,3900,4600\n"
            "2026-11-06 19:00,How I price my services (save this) #pricing #freelance,Carousel,517,63,29,204,9800,11200\n"
            "2026-11-09 19:00,The 10-minute content system #freelance #content,Reel,764,88,52,141,11800,14200\n"
            "2026-11-11 12:30,Client win: first $1k month #freelance,Image,402,34,11,47,6100,7300\n"
        ),
        "tiktok": (
            "Video ID,Date,Caption,Video views,Likes,Comments,Shares,Saves\n"
            "7482910031,2026-11-03 18:00,3 Canva tricks nobody tells you,48200,3900,214,980,1500\n"
            "7482910045,2026-11-05 20:00,Day in my life as a freelancer,21500,1200,86,210,340\n"
            "7482910060,2026-11-10 18:00,Stop making this pricing mistake #freelance,31200,2600,178,640,720\n"
        ),
        "linkedin": (
            "Post URL,Date,Impressions,Reactions,Comments,Reposts,Clicks\n"
            "https://www.linkedin.com/posts/example-1,2026-11-02 09:00,8400,312,48,21,96\n"
            "https://www.linkedin.com/posts/example-2,2026-11-05 09:00,5200,198,31,9,54\n"
            "https://www.linkedin.com/posts/example-3,2026-11-12 09:00,9100,402,67,33,121\n"
        ),
        "facebook": (
            "Post ID,Date,Message,Reach,Reactions,Comments,Shares,Post clicks\n"
            "101,2026-11-03 15:00,Weekend offer: 20% off all templates,6200,340,52,18,210\n"
            "102,2026-11-07 11:00,Behind the scenes at our studio,3100,128,21,6,48\n"
            "103,2026-11-10 15:00,New template drop: invoice pack,5400,298,44,15,167\n"
        ),
        "x": (
            "Tweet ID,Date,Text,Impressions,Likes,Retweets,Replies,Link clicks\n"
            "1857000000000000001,2026-11-02 14:00,Hot take: your bio is your landing page,15200,640,88,42,310\n"
            "1857000000000000002,2026-11-04 14:00,5 tools I use every single day,9800,410,51,19,180\n"
            "1857000000000000003,2026-11-09 14:00,Freelancers: charge for the call not the hour,18400,890,121,64,420\n"
        ),
        "generic": (
            "Date,Platform,Caption,Type,Likes,Comments,Shares,Reach,Impressions\n"
            "2026-11-02 19:00,instagram,Launch post,Reel,842,96,41,12400,15800\n"
            "2026-11-03 18:00,tiktok,Quick tips video,Video,3900,214,980,48200,48200\n"
        ),
    }
    return samples[normalise_platform(platform)]


__all__ = [
    "FIELD_ALIASES",
    "ImportError_",
    "ImportResult",
    "import_posts_from_file",
    "import_posts_from_text",
    "sample_csv",
]
