"""Analytics: turn a pile of posts into answers.

Everything here is a pure function over a list of Post objects, so it
is easy to test and easy to reuse from the CLI and the reports.

Metrics used throughout:
- Engagement = likes + comments + shares + saves.
- ER by reach = engagement / reach (the honest rate — what the
  platform actually showed the post to).
- ER by followers = engagement / followers (useful when reach is
  missing, e.g. some LinkedIn exports).
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from .models import Post, Snapshot

_HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]{2,60})")

# A slot needs at least this many posts before it can be called "best".
MIN_POSTS_FOR_SLOT = 2
MIN_POSTS_FOR_TYPE = 3


def median(values: list[float]) -> float:
    """Median of a list of numbers (0 for an empty list)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def filter_posts(
    posts: list[Post],
    platform: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> list[Post]:
    """Filter by platform and/or date range (inclusive)."""
    out = posts
    if platform:
        out = [p for p in out if p.platform == platform]
    if since:
        out = [p for p in out if p.date >= since]
    if until:
        out = [p for p in out if p.date <= until]
    return out


def post_rate(post: Post, followers: int = 0) -> Optional[float]:
    """The best engagement rate available for one post.

    Reach first, then impressions (views), then followers recorded on
    the post, then the account's current follower count.
    """
    rate = post.engagement_rate()
    if rate is not None:
        return rate
    if followers > 0:
        return round(post.engagement / followers * 100, 2)
    return None


def platform_summary(posts: list[Post], followers: int = 0) -> dict:
    """Totals and averages for one group of posts.

    Each average rate only counts the posts that actually have that
    denominator — a TikTok video with views but no reach must not drag
    the reach-based average down.  ``avg_er`` is the best rate
    available: reach, then impressions, then followers.
    """
    if not posts:
        return {
            "posts": 0, "reach": 0, "impressions": 0, "engagement": 0,
            "likes": 0, "comments": 0, "shares": 0, "saves": 0, "clicks": 0,
            "avg_er_reach": None, "avg_er_impressions": None,
            "avg_er_followers": None, "avg_er": None, "avg_engagement": 0.0,
        }
    engagement = sum(p.engagement for p in posts)
    with_reach = [p for p in posts if p.reach > 0]
    with_impressions = [p for p in posts if p.impressions > 0]
    with_followers = [p for p in posts if p.followers_at_post > 0]
    avg_er_reach = (
        round(sum(p.engagement for p in with_reach) / sum(p.reach for p in with_reach) * 100, 2)
        if with_reach else None
    )
    avg_er_impressions = (
        round(sum(p.engagement for p in with_impressions) / sum(p.impressions for p in with_impressions) * 100, 2)
        if with_impressions else None
    )
    if with_followers:
        avg_er_followers = round(
            sum(p.engagement for p in with_followers) / sum(p.followers_at_post for p in with_followers) * 100, 2
        )
    elif followers > 0:
        avg_er_followers = round(engagement / (followers * len(posts)) * 100, 2)
    else:
        avg_er_followers = None
    return {
        "posts": len(posts),
        "reach": sum(p.reach for p in posts),
        "impressions": sum(p.impressions for p in posts),
        "engagement": engagement,
        "likes": sum(p.likes for p in posts),
        "comments": sum(p.comments for p in posts),
        "shares": sum(p.shares for p in posts),
        "saves": sum(p.saves for p in posts),
        "clicks": sum(p.clicks for p in posts),
        "avg_er_reach": avg_er_reach,
        "avg_er_impressions": avg_er_impressions,
        "avg_er_followers": avg_er_followers,
        "avg_er": avg_er_reach or avg_er_impressions or avg_er_followers,
        "avg_engagement": round(engagement / len(posts), 1),
    }


def per_platform_summary(posts: list[Post], followers_map: dict | None = None) -> dict:
    """platform_summary() for every platform present, best first."""
    followers_map = followers_map or {}
    grouped: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        grouped[post.platform].append(post)
    summaries = {
        platform: platform_summary(group, followers_map.get(platform, 0))
        for platform, group in grouped.items()
    }
    # Sort by engagement rate (best available denominator first).
    def sort_key(item: tuple[str, dict]) -> float:
        rate = item[1]["avg_er"]
        return rate if rate is not None else -1.0

    return dict(sorted(summaries.items(), key=sort_key, reverse=True))


def best_posting_times(
    posts: list[Post], followers_map: dict | None = None
) -> dict:
    """When to post: average engagement rate by weekday+hour slot.

    Returns the top slots (weekday 0=Mon, hour 0-23), plus the best
    hour overall and the best weekday overall.  A slot only ranks with
    at least MIN_POSTS_FOR_SLOT posts in it — one lucky post is not a
    pattern.
    """
    followers_map = followers_map or {}
    slots: dict[tuple[int, int], list[float]] = defaultdict(list)
    hours: dict[int, list[float]] = defaultdict(list)
    weekdays: dict[int, list[float]] = defaultdict(list)
    for post in posts:
        rate = post_rate(post, followers_map.get(post.platform, 0))
        if rate is None:
            continue
        key = (post.date.weekday(), post.date.hour)
        slots[key].append(rate)
        hours[post.date.hour].append(rate)
        weekdays[post.date.weekday()].append(rate)

    def ranked(groups: dict, minimum: int) -> list[dict]:
        rows = []
        for key, rates in groups.items():
            if len(rates) < minimum:
                continue
            rows.append({"key": key, "posts": len(rates), "avg_er": round(sum(rates) / len(rates), 2)})
        return sorted(rows, key=lambda r: r["avg_er"], reverse=True)

    slot_rows = ranked(slots, MIN_POSTS_FOR_SLOT)
    return {
        "top_slots": slot_rows[:10],
        "best_hour": ranked(hours, MIN_POSTS_FOR_SLOT)[:5],
        "best_weekday": ranked(weekdays, MIN_POSTS_FOR_SLOT)[:5],
        "slots_with_data": len(slots),
    }


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def top_posts(posts: list[Post], count: int = 10, by: str = "engagement") -> list[Post]:
    """Best posts, by engagement (default), reach, or engagement rate."""
    if by == "reach":
        return sorted(posts, key=lambda p: p.reach, reverse=True)[:count]
    if by == "rate":
        return sorted(
            posts, key=lambda p: (post_rate(p) is not None, post_rate(p) or 0), reverse=True
        )[:count]
    return sorted(posts, key=lambda p: p.engagement, reverse=True)[:count]


def outlier_posts(posts: list[Post], factor: float = 1.5) -> list[dict]:
    """Posts that beat their platform's median engagement by `factor`x.

    Outliers are the closest thing to a recipe: whatever those posts
    did is worth repeating.
    """
    grouped: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        grouped[post.platform].append(post)
    out = []
    for platform, group in grouped.items():
        if len(group) < 3:
            continue
        med = median([float(p.engagement) for p in group])
        if med <= 0:
            continue
        for post in group:
            if post.engagement >= med * factor:
                out.append({
                    "post": post,
                    "platform": platform,
                    "multiple": round(post.engagement / med, 1),
                    "median_engagement": med,
                })
    return sorted(out, key=lambda r: r["multiple"], reverse=True)


def content_type_performance(posts: list[Post], followers_map: dict | None = None) -> list[dict]:
    """Average engagement rate per content type (reels vs images...)."""
    followers_map = followers_map or {}
    grouped: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        grouped[post.content_type].append(post)
    rows = []
    for ctype, group in grouped.items():
        if len(group) < MIN_POSTS_FOR_TYPE:
            continue
        rates = [r for r in (post_rate(p, followers_map.get(p.platform, 0)) for p in group) if r is not None]
        rows.append({
            "content_type": ctype,
            "posts": len(group),
            "avg_er": round(sum(rates) / len(rates), 2) if rates else None,
            "avg_reach": round(sum(p.reach for p in group) / len(group), 1),
            "avg_engagement": round(sum(p.engagement for p in group) / len(group), 1),
        })
    return sorted(rows, key=lambda r: (r["avg_er"] is not None, r["avg_er"] or 0), reverse=True)


def hashtag_performance(posts: list[Post], followers_map: dict | None = None) -> list[dict]:
    """Per-hashtag stats: how often used, average engagement rate."""
    followers_map = followers_map or {}
    stats: dict[str, dict] = defaultdict(lambda: {"uses": 0, "rates": [], "reach": 0})
    for post in posts:
        tags = {tag.lower() for tag in _HASHTAG_RE.findall(post.caption)}
        rate = post_rate(post, followers_map.get(post.platform, 0))
        for tag in tags:
            stats[tag]["uses"] += 1
            stats[tag]["reach"] += post.reach
            if rate is not None:
                stats[tag]["rates"].append(rate)
    rows = []
    for tag, data in stats.items():
        if data["uses"] < 2:
            continue
        rates = data["rates"]
        rows.append({
            "hashtag": f"#{tag}",
            "uses": data["uses"],
            "avg_er": round(sum(rates) / len(rates), 2) if rates else None,
            "avg_reach": round(data["reach"] / data["uses"], 1),
        })
    return sorted(rows, key=lambda r: (r["avg_er"] is not None, r["avg_er"] or 0), reverse=True)


def weekly_trend(posts: list[Post]) -> list[dict]:
    """One row per ISO week: posts, reach, engagement, average ER."""
    grouped: dict[tuple[int, int], list[Post]] = defaultdict(list)
    for post in posts:
        iso = post.date.isocalendar()
        grouped[(iso.year, iso.week)].append(post)
    rows = []
    for (year, week), group in sorted(grouped.items()):
        reach = sum(p.reach for p in group)
        engagement = sum(p.engagement for p in group)
        rows.append({
            "year": year,
            "week": week,
            "label": f"{year}-W{week:02d}",
            "posts": len(group),
            "reach": reach,
            "engagement": engagement,
            "avg_er": round(engagement / reach * 100, 2) if reach > 0 else None,
        })
    return rows


def follower_growth(snapshots: list[Snapshot]) -> dict:
    """Growth between the earliest and latest snapshot per platform."""
    grouped: dict[str, list[Snapshot]] = defaultdict(list)
    for snap in snapshots:
        grouped[snap.platform].append(snap)
    result = {}
    for platform, snaps in grouped.items():
        ordered = sorted(snaps, key=lambda s: s.date)
        first, last = ordered[0], ordered[-1]
        days = max((last.date - first.date).days, 1)
        growth = last.followers - first.followers
        result[platform] = {
            "from": first.followers,
            "to": last.followers,
            "growth": growth,
            "growth_pct": round(growth / first.followers * 100, 2) if first.followers > 0 else None,
            "per_day": round(growth / days, 1),
            "days": (last.date - first.date).days,
            "snapshots": len(ordered),
        }
    return result


def posting_gaps(posts: list[Post], gap_days: int = 7) -> list[dict]:
    """Gaps of `gap_days`+ days with no post, per platform."""
    grouped: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        grouped[post.platform].append(post)
    gaps = []
    for platform, group in grouped.items():
        dates = sorted({p.date.date() for p in group})
        for earlier, later in zip(dates, dates[1:]):
            gap = (later - earlier).days
            if gap > gap_days:
                gaps.append({
                    "platform": platform,
                    "from": earlier.isoformat(),
                    "to": later.isoformat(),
                    "days": gap,
                })
    return sorted(gaps, key=lambda g: g["days"], reverse=True)


def recommendations(posts: list[Post], snapshots: list[Snapshot], followers_map: dict | None = None) -> list[dict]:
    """Plain-language findings, each with the evidence behind it.

    Every recommendation has a severity (info / tip / warning) and a
    one-line reason with real numbers — no generic advice.
    """
    followers_map = followers_map or {}
    findings: list[dict] = []
    if not posts:
        return [{"severity": "info", "title": "No posts yet",
                 "detail": "Import a platform export to get your first report."}]

    summary = platform_summary(posts)
    per_platform = per_platform_summary(posts, followers_map)

    # 1. Best content type.
    types = content_type_performance(posts, followers_map)
    if len(types) >= 2 and types[0]["avg_er"] and types[-1]["avg_er"]:
        best, worst = types[0], types[-1]
        if best["avg_er"] >= worst["avg_er"] * 1.5:
            findings.append({
                "severity": "tip",
                "title": f"Post more {best['content_type']}s — they earn {best['avg_er']}% ER vs {worst['avg_er']}% for {worst['content_type']}s",
                "detail": f"Based on {best['posts']} {best['content_type']} posts and {worst['posts']} {worst['content_type']} posts.",
            })

    # 2. Best posting slot.
    times = best_posting_times(posts, followers_map)
    if times["top_slots"]:
        slot = times["top_slots"][0]
        weekday, hour = slot["key"]
        findings.append({
            "severity": "tip",
            "title": f"Your best slot is {WEEKDAYS[weekday]} at {hour:02d}:00 ({slot['avg_er']}% avg ER across {slot['posts']} posts)",
            "detail": "Schedule your strongest content into this slot first.",
        })

    # 3. Weakest platform.
    if len(per_platform) >= 2:
        items = list(per_platform.items())
        best_name, best_sum = items[0]
        worst_name, worst_sum = items[-1]
        best_rate = best_sum["avg_er"]
        worst_rate = worst_sum["avg_er"]
        if best_rate and worst_rate and best_rate >= worst_rate * 2:
            findings.append({
                "severity": "warning",
                "title": f"{worst_name.title()} lags badly: {worst_rate}% ER vs {best_rate}% on {best_name.title()}",
                "detail": f"{worst_name.title()} has {worst_sum['posts']} posts averaging {worst_sum['avg_engagement']} engagements each. "
                          f"Repurpose your best {best_name.title()} posts there instead of posting less.",
            })

    # 4. Outliers worth repeating.
    outliers = outlier_posts(posts)
    if outliers:
        top = outliers[0]
        findings.append({
            "severity": "tip",
            "title": f"{len(outliers)} post(s) outperformed your median by 1.5x or more — study the top one",
            "detail": f"Top outlier ({top['platform']}): {top['multiple']}x median engagement — "
                      f"\"{top['post'].caption[:80]}\". Repeat its format and hook.",
        })

    # 5. Posting gaps.
    gaps = posting_gaps(posts)
    if gaps:
        worst_gap = gaps[0]
        findings.append({
            "severity": "warning",
            "title": f"Longest silence: {worst_gap['days']} days with no post on {worst_gap['platform'].title()} ({worst_gap['from']} to {worst_gap['to']})",
            "detail": "Algorithms reward consistency. A simple weekly schedule closes most gaps.",
        })

    # 6. Reach without engagement = hook problem.
    if summary["reach"] > 0:
        low_er = [p for p in posts if (p.engagement_rate_by_reach() or 99) < 1.0 and p.reach >= 1000]
        if len(low_er) >= 3:
            findings.append({
                "severity": "warning",
                "title": f"{len(low_er)} posts reached 1,000+ people but earned under 1% engagement",
                "detail": "People see them but scroll past — the hook or first line needs work, not the reach.",
            })

    # 7. High engagement, low reach = distribution problem.
    high_er_low_reach = [
        p for p in posts
        if (p.engagement_rate_by_reach() or 0) >= 8.0 and p.reach < 1000 and p.reach > 0
    ]
    if len(high_er_low_reach) >= 2:
        findings.append({
            "severity": "tip",
            "title": f"{len(high_er_low_reach)} posts earned 8%+ engagement but reached under 1,000 people",
            "detail": "The content works — it just needs distribution: repost, pin, or boost the best one.",
        })

    # 8. Hashtag stuffing.
    tag_counts = [len(_HASHTAG_RE.findall(p.caption)) for p in posts]
    avg_tags = sum(tag_counts) / len(tag_counts) if tag_counts else 0
    if avg_tags > 10:
        findings.append({
            "severity": "info",
            "title": f"You average {avg_tags:.1f} hashtags per post — most platforms reward 3–5 relevant ones",
            "detail": "Cut the weakest tags (see the hashtag table) and keep the ones with the best ER.",
        })

    # 9. Missing reach data.
    missing_reach = sum(1 for p in posts if p.reach <= 0)
    if missing_reach and missing_reach / len(posts) > 0.5:
        findings.append({
            "severity": "info",
            "title": f"{missing_reach} of {len(posts)} posts have no reach data — engagement rates use followers instead",
            "detail": "Re-export with reach/impressions columns for more accurate rates.",
        })

    # 10. Follower growth.
    growth = follower_growth(snapshots)
    for platform, data in growth.items():
        if data["snapshots"] >= 2 and data["growth_pct"] is not None:
            direction = "grew" if data["growth"] >= 0 else "shrank"
            findings.append({
                "severity": "info",
                "title": f"{platform.title()} {direction} by {data['growth_pct']}% ({data['from']:,} → {data['to']:,}) over {data['days']} days",
                "detail": f"About {data['per_day']:+.1f} followers per day.",
            })

    if not findings:
        findings.append({
            "severity": "info",
            "title": "No strong patterns yet — import more posts for sharper advice",
            "detail": f"Only {len(posts)} post(s) analysed. Best-time and content-type advice needs at least 3 posts per group.",
        })
    return findings
