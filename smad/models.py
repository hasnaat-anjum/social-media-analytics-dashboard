"""Data models for Social Media Analytics Dashboard.

A Post is one published post on one platform, with the metrics that
platform exports give you (likes, comments, shares, saves, reach,
impressions, clicks).  A Snapshot is a follower count recorded on a
date, used to track growth over time.  Both serialise to plain JSON
so the store stays human-readable and editable by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Platforms we know how to import.  "generic" is the fallback for any
# CSV that has a date column and at least one metric column.
PLATFORMS = ("instagram", "facebook", "tiktok", "linkedin", "x", "generic")

# Content types, normalised by the importers.  Unknown values become
# "post" rather than being dropped, so nothing is lost on import.
CONTENT_TYPES = (
    "reel", "video", "image", "carousel", "text", "link", "story", "post",
)

_TYPE_ALIASES = {
    "photo": "image",
    "picture": "image",
    "pic": "image",
    "short": "video",
    "clip": "video",
    "reels": "reel",
    "videos": "video",
    "images": "image",
    "photos": "image",
    "carousels": "carousel",
    "album": "carousel",
    "status": "text",
    "tweet": "text",
    "article": "link",
    "story": "story",
    "stories": "story",
}


def normalise_content_type(raw: Optional[str]) -> str:
    """Map a free-text media-type value onto a known content type."""
    if not raw:
        return "post"
    value = raw.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    if value in CONTENT_TYPES:
        return value
    return _TYPE_ALIASES.get(value, "post")


def normalise_platform(raw: Optional[str]) -> str:
    """Map a free-text platform name onto a known platform slug."""
    if not raw:
        return "generic"
    value = raw.strip().lower()
    aliases = {
        "ig": "instagram",
        "insta": "instagram",
        "fb": "facebook",
        "meta": "facebook",
        "tt": "tiktok",
        "tik tok": "tiktok",
        "li": "linkedin",
        "twitter": "x",
        "x (twitter)": "x",
    }
    if value in PLATFORMS:
        return value
    return aliases.get(value, "generic")


@dataclass
class Post:
    """One published post and its metrics."""

    platform: str
    date: datetime
    caption: str = ""
    content_type: str = "post"
    post_id: str = ""
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    reach: int = 0
    impressions: int = 0
    clicks: int = 0
    followers_at_post: int = 0
    url: str = ""

    def __post_init__(self) -> None:
        self.platform = normalise_platform(self.platform)
        self.content_type = normalise_content_type(self.content_type)
        # Never let a negative metric through (exports sometimes use -1
        # for "not available"); treat it as missing.
        for name in (
            "likes", "comments", "shares", "saves", "reach",
            "impressions", "clicks", "followers_at_post",
        ):
            if getattr(self, name) < 0:
                setattr(self, name, 0)

    @property
    def engagement(self) -> int:
        """Total interactions: likes + comments + shares + saves."""
        return self.likes + self.comments + self.shares + self.saves

    @property
    def views(self) -> int:
        """Best available view count: impressions first, reach second."""
        return self.impressions or self.reach

    def engagement_rate_by_reach(self) -> Optional[float]:
        """Engagement as a percentage of reach, or None if no reach."""
        if self.reach <= 0:
            return None
        return round(self.engagement / self.reach * 100, 2)

    def engagement_rate_by_impressions(self) -> Optional[float]:
        """Engagement as a percentage of impressions (views)."""
        if self.impressions <= 0:
            return None
        return round(self.engagement / self.impressions * 100, 2)

    def engagement_rate_by_followers(self) -> Optional[float]:
        """Engagement as a percentage of followers, or None if unknown."""
        if self.followers_at_post <= 0:
            return None
        return round(self.engagement / self.followers_at_post * 100, 2)

    def engagement_rate(self) -> Optional[float]:
        """Best engagement rate available: reach, then impressions, then followers."""
        for rate in (
            self.engagement_rate_by_reach(),
            self.engagement_rate_by_impressions(),
            self.engagement_rate_by_followers(),
        ):
            if rate is not None:
                return rate
        return None

    def key(self) -> str:
        """Stable identity used for de-duplication on re-import."""
        base = self.post_id or f"{self.caption[:60]}|{self.date.date().isoformat()}"
        return f"{self.platform}::{base}"

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "date": self.date.isoformat(),
            "caption": self.caption,
            "content_type": self.content_type,
            "post_id": self.post_id,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "saves": self.saves,
            "reach": self.reach,
            "impressions": self.impressions,
            "clicks": self.clicks,
            "followers_at_post": self.followers_at_post,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Post":
        return cls(
            platform=data.get("platform", "generic"),
            date=datetime.fromisoformat(data["date"]),
            caption=data.get("caption", ""),
            content_type=data.get("content_type", "post"),
            post_id=data.get("post_id", ""),
            likes=int(data.get("likes", 0) or 0),
            comments=int(data.get("comments", 0) or 0),
            shares=int(data.get("shares", 0) or 0),
            saves=int(data.get("saves", 0) or 0),
            reach=int(data.get("reach", 0) or 0),
            impressions=int(data.get("impressions", 0) or 0),
            clicks=int(data.get("clicks", 0) or 0),
            followers_at_post=int(data.get("followers_at_post", 0) or 0),
            url=data.get("url", ""),
        )


@dataclass
class Snapshot:
    """A follower count for one platform on one date."""

    platform: str
    date: datetime
    followers: int

    def __post_init__(self) -> None:
        self.platform = normalise_platform(self.platform)
        if self.followers < 0:
            self.followers = 0

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "date": self.date.isoformat(),
            "followers": self.followers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        return cls(
            platform=data.get("platform", "generic"),
            date=datetime.fromisoformat(data["date"]),
            followers=int(data.get("followers", 0) or 0),
        )


@dataclass
class Store:
    """Everything the tool remembers: posts, snapshots, settings."""

    posts: list = field(default_factory=list)
    snapshots: list = field(default_factory=list)
    # Followers per platform, used as the fallback denominator for
    # engagement rate when a post has no reach figure.
    followers: dict = field(default_factory=dict)
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "followers": self.followers,
            "posts": [p.to_dict() for p in self.posts],
            "snapshots": [s.to_dict() for s in self.snapshots],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Store":
        return cls(
            posts=[Post.from_dict(p) for p in data.get("posts", [])],
            snapshots=[Snapshot.from_dict(s) for s in data.get("snapshots", [])],
            followers=dict(data.get("followers", {})),
            version=int(data.get("version", 1)),
        )
