"""Command-line interface.

Subcommands:
    import      read a platform CSV export into the local store
    add         add one post by hand
    dashboard   print the terminal dashboard
    report      write a Markdown / HTML / JSON / CSV report
    best-times  show the best posting slots
    top         list the best posts
    hashtags    rank hashtags by engagement rate
    snapshot    record today's follower count for a platform
    snapshots   show follower growth
    list        list stored posts
    remove      delete a post by its ID
    example     print a sample CSV for a platform (try the importer on it)

Data lives in ``social-data.json`` in the current directory by default
(``--data`` overrides).  Nothing leaves your machine: no accounts,
no API keys, no uploads.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from typing import Optional

from . import __version__
from .analytics import (
    WEEKDAYS,
    best_posting_times,
    follower_growth,
    hashtag_performance,
    top_posts,
)
from .importers import ImportError_, import_posts_from_file, sample_csv
from .models import Post, Snapshot, normalise_platform
from .parseutils import format_number, format_pct, parse_date, parse_number
from .reports import csv_export, html_report, json_report, markdown_report, terminal_dashboard
from .store import DEFAULT_DATA_FILE, existing_keys, load_store, save_store


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", default=DEFAULT_DATA_FILE,
                        help=f"data file (default: {DEFAULT_DATA_FILE})")


def _add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--platform", default=None,
                        help="only this platform (instagram, facebook, tiktok, linkedin, x)")
    parser.add_argument("--days", type=int, default=None,
                        help="only posts from the last N days")


def _filter(args, posts: list[Post]) -> list[Post]:
    out = posts
    if args.platform:
        out = [p for p in out if p.platform == normalise_platform(args.platform)]
    if getattr(args, "days", None):
        since = datetime.now() - timedelta(days=args.days)
        out = [p for p in out if p.date >= since]
    return out


def _followers_map(store) -> dict:
    return {k: int(v) for k, v in store.followers.items()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smad",
        description="Social Media Analytics Dashboard — free, local analytics "
                    "from the CSV exports your platforms already give you.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="import a platform CSV export")
    p.add_argument("file", help="CSV file to import")
    p.add_argument("--platform", default=None, help="force the platform (auto-detected otherwise)")
    _add_common(p)

    p = sub.add_parser("add", help="add one post by hand")
    p.add_argument("--platform", required=True)
    p.add_argument("--date", required=True, help="e.g. 2026-11-20 or 2026-11-20 19:00")
    p.add_argument("--caption", default="")
    p.add_argument("--type", default="post", dest="content_type")
    p.add_argument("--id", default="", dest="post_id")
    p.add_argument("--likes", type=int, default=0)
    p.add_argument("--comments", type=int, default=0)
    p.add_argument("--shares", type=int, default=0)
    p.add_argument("--saves", type=int, default=0)
    p.add_argument("--reach", type=int, default=0)
    p.add_argument("--impressions", type=int, default=0)
    p.add_argument("--clicks", type=int, default=0)
    p.add_argument("--followers", type=int, default=0)
    p.add_argument("--url", default="")
    _add_common(p)

    p = sub.add_parser("dashboard", help="print the terminal dashboard")
    _add_common(p)
    _add_filters(p)

    p = sub.add_parser("report", help="write a report file")
    p.add_argument("--format", choices=["md", "html", "json", "csv"], default="md")
    p.add_argument("--out", default=None, help="output file (default: report.<ext>)")
    _add_common(p)
    _add_filters(p)

    p = sub.add_parser("best-times", help="show the best posting slots")
    _add_common(p)
    _add_filters(p)

    p = sub.add_parser("top", help="list the best posts")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--by", choices=["engagement", "reach", "rate"], default="engagement")
    _add_common(p)
    _add_filters(p)

    p = sub.add_parser("hashtags", help="rank hashtags by engagement rate")
    _add_common(p)
    _add_filters(p)

    p = sub.add_parser("snapshot", help="record today's follower count")
    p.add_argument("--platform", required=True)
    p.add_argument("--followers", type=int, required=True)
    p.add_argument("--date", default=None, help="default: today")
    _add_common(p)

    p = sub.add_parser("snapshots", help="show follower growth")
    _add_common(p)

    p = sub.add_parser("list", help="list stored posts")
    p.add_argument("--limit", type=int, default=20)
    _add_common(p)
    _add_filters(p)

    p = sub.add_parser("remove", help="delete a post by its ID")
    p.add_argument("--id", required=True, dest="post_id")
    p.add_argument("--platform", default=None)
    _add_common(p)

    p = sub.add_parser("example", help="print a sample CSV for a platform")
    p.add_argument("platform", nargs="?", default="instagram",
                   help="instagram, facebook, tiktok, linkedin, x, generic")

    p = sub.add_parser("set-followers", help="set the follower count used for ER by followers")
    p.add_argument("--platform", required=True)
    p.add_argument("--followers", type=int, required=True)
    _add_common(p)

    return parser


def cmd_import(args) -> int:
    store = load_store(args.data)
    platform = normalise_platform(args.platform) if args.platform else None
    default_followers = 0
    if platform and platform in store.followers:
        default_followers = int(store.followers[platform])
    try:
        result = import_posts_from_file(
            args.file, platform, existing_keys(store), default_followers
        )
    except ImportError_ as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    store.posts.extend(result.imported)
    store.posts.sort(key=lambda p: p.date)
    save_store(store, args.data)
    print(f"Imported {len(result.imported)} posts from {args.file} "
          f"(platform: {result.platform}, {result.rows_seen} rows seen).")
    if result.skipped_duplicates:
        print(f"Skipped {result.skipped_duplicates} duplicate(s) already in the store.")
    if result.skipped_bad_rows:
        print(f"Skipped {result.skipped_bad_rows} row(s) with unparseable dates.")
        for error in result.errors[:5]:
            print(f"  {error}")
    return 0


def cmd_add(args) -> int:
    date = parse_date(args.date)
    if date is None:
        print(f"Cannot parse date: {args.date}", file=sys.stderr)
        return 1
    store = load_store(args.data)
    post = Post(
        platform=args.platform, date=date, caption=args.caption,
        content_type=args.content_type, post_id=args.post_id,
        likes=args.likes, comments=args.comments, shares=args.shares,
        saves=args.saves, reach=args.reach, impressions=args.impressions,
        clicks=args.clicks, followers_at_post=args.followers, url=args.url,
    )
    if post.key() in existing_keys(store):
        print("That post is already in the store.", file=sys.stderr)
        return 1
    store.posts.append(post)
    store.posts.sort(key=lambda p: p.date)
    save_store(store, args.data)
    print(f"Added {post.platform} post from {post.date.date()} "
          f"({format_number(post.engagement)} engagements).")
    return 0


def cmd_dashboard(args) -> int:
    store = load_store(args.data)
    posts = _filter(args, store.posts)
    print(terminal_dashboard(posts, store.snapshots, _followers_map(store)))
    return 0


def cmd_report(args) -> int:
    store = load_store(args.data)
    posts = _filter(args, store.posts)
    fmt = args.format
    if fmt == "md":
        content = markdown_report(posts, store.snapshots, _followers_map(store))
        default_name = "report.md"
    elif fmt == "html":
        content = html_report(posts, store.snapshots, _followers_map(store))
        default_name = "report.html"
    elif fmt == "json":
        content = json_report(posts, store.snapshots, _followers_map(store))
        default_name = "report.json"
    else:
        content = csv_export(posts)
        default_name = "report.csv"
    out = args.out or default_name
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(f"Wrote {fmt.upper()} report for {len(posts)} post(s) to {out}")
    return 0


def cmd_best_times(args) -> int:
    store = load_store(args.data)
    posts = _filter(args, store.posts)
    times = best_posting_times(posts, _followers_map(store))
    if not times["top_slots"]:
        print("Not enough data yet — need at least 2 posts in the same weekday+hour slot.")
        return 0
    print("Best times to post (average engagement rate):")
    for slot in times["top_slots"]:
        weekday, hour = slot["key"]
        print(f"  {WEEKDAYS[weekday]:<9} {hour:02d}:00  {slot['avg_er']:>5}% ER  ({slot['posts']} posts)")
    return 0


def cmd_top(args) -> int:
    store = load_store(args.data)
    posts = _filter(args, store.posts)
    for post in top_posts(posts, args.count, by=args.by):
        rate = post.engagement_rate()
        caption = (post.caption or "(no caption)")[:70]
        print(f"{post.date.date()}  [{post.platform}]  {format_number(post.engagement):>6} eng  "
              f"ER {format_pct(rate):>7}  {caption}")
    return 0


def cmd_hashtags(args) -> int:
    store = load_store(args.data)
    posts = _filter(args, store.posts)
    rows = hashtag_performance(posts, _followers_map(store))
    if not rows:
        print("No hashtag used twice or more yet.")
        return 0
    print(f"{'Hashtag':<22}{'Uses':>6}{'Avg ER':>10}{'Avg reach':>12}")
    for row in rows:
        print(f"{row['hashtag']:<22}{row['uses']:>6}{format_pct(row['avg_er']):>10}"
              f"{format_number(int(row['avg_reach'])):>12}")
    return 0


def cmd_snapshot(args) -> int:
    date = parse_date(args.date) if args.date else datetime.now()
    if date is None:
        print(f"Cannot parse date: {args.date}", file=sys.stderr)
        return 1
    store = load_store(args.data)
    platform = normalise_platform(args.platform)
    store.snapshots.append(Snapshot(platform=platform, date=date, followers=args.followers))
    store.followers[platform] = args.followers
    store.snapshots.sort(key=lambda s: s.date)
    save_store(store, args.data)
    print(f"Recorded {format_number(args.followers)} followers on {platform} ({date.date()}).")
    return 0


def cmd_snapshots(args) -> int:
    store = load_store(args.data)
    growth = follower_growth(store.snapshots)
    if not growth:
        print("No snapshots yet. Record one with: smad snapshot --platform instagram --followers 1250")
        return 0
    for platform, data in growth.items():
        print(f"{platform:<10} {format_number(data['from']):>8} → {format_number(data['to']):>8}  "
              f"({data['growth_pct']:+.2f}% over {data['days']} days, {data['per_day']:+.1f}/day)")
    return 0


def cmd_list(args) -> int:
    store = load_store(args.data)
    posts = _filter(args, store.posts)
    posts = sorted(posts, key=lambda p: p.date, reverse=True)[: args.limit]
    if not posts:
        print("No posts stored yet.")
        return 0
    for post in posts:
        caption = (post.caption or "(no caption)")[:60]
        print(f"{post.date.date()}  [{post.platform}]  id={post.post_id or '-'}  "
              f"{format_number(post.engagement):>6} eng  {caption}")
    print(f"\nShowing {len(posts)} of {len(store.posts)} stored post(s).")
    return 0


def cmd_remove(args) -> int:
    store = load_store(args.data)
    before = len(store.posts)
    platform = normalise_platform(args.platform) if args.platform else None
    store.posts = [
        p for p in store.posts
        if not (p.post_id == args.post_id and (platform is None or p.platform == platform))
    ]
    removed = before - len(store.posts)
    if removed == 0:
        print(f"No post with id '{args.post_id}' found.", file=sys.stderr)
        return 1
    save_store(store, args.data)
    print(f"Removed {removed} post(s).")
    return 0


def cmd_example(args) -> int:
    print(sample_csv(args.platform), end="")
    return 0


def cmd_set_followers(args) -> int:
    store = load_store(args.data)
    platform = normalise_platform(args.platform)
    store.followers[platform] = args.followers
    save_store(store, args.data)
    print(f"{platform}: {format_number(args.followers)} followers.")
    return 0


_COMMANDS = {
    "import": cmd_import,
    "add": cmd_add,
    "dashboard": cmd_dashboard,
    "report": cmd_report,
    "best-times": cmd_best_times,
    "top": cmd_top,
    "hashtags": cmd_hashtags,
    "snapshot": cmd_snapshot,
    "snapshots": cmd_snapshots,
    "list": cmd_list,
    "remove": cmd_remove,
    "example": cmd_example,
    "set-followers": cmd_set_followers,
}


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return _COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
