"""Reports: terminal dashboard, Markdown, JSON, CSV and HTML.

The HTML report is a single self-contained file (inline CSS, inline
SVG charts, no JavaScript, no external requests) so it can be opened
anywhere and shared with a client as-is.
"""

from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime
from typing import Optional

from .analytics import (
    WEEKDAYS,
    best_posting_times,
    content_type_performance,
    follower_growth,
    hashtag_performance,
    outlier_posts,
    per_platform_summary,
    platform_summary,
    recommendations,
    top_posts,
    weekly_trend,
)
from .models import Post, Snapshot
from .parseutils import format_number, format_pct


def _esc(text: str) -> str:
    return html.escape(text or "")


# ---------------------------------------------------------------- terminal

def terminal_dashboard(
    posts: list[Post],
    snapshots: list[Snapshot],
    followers_map: dict | None = None,
    title: str = "Social Media Analytics",
) -> str:
    """Plain-text dashboard for the terminal."""
    followers_map = followers_map or {}
    lines = [f"\n{title}", "=" * len(title), ""]
    if not posts:
        lines.append("No posts yet. Import a CSV export to get started:")
        lines.append("  python -m smad import exports/instagram.csv")
        return "\n".join(lines)

    summary = platform_summary(posts)
    lines.append(f"Posts analysed:  {summary['posts']}")
    lines.append(f"Total reach:     {format_number(summary['reach'])}")
    lines.append(f"Total engagement:{format_number(summary['engagement'])} "
                 f"(likes {format_number(summary['likes'])}, comments {format_number(summary['comments'])}, "
                 f"shares {format_number(summary['shares'])}, saves {format_number(summary['saves'])})")
    lines.append(f"Avg ER:          {format_pct(summary['avg_er'])}")
    lines.append("")

    lines.append("By platform:")
    for platform, data in per_platform_summary(posts, followers_map).items():
        rate = data["avg_er"]
        lines.append(
            f"  {platform:<10} {data['posts']:>3} posts  "
            f"reach {format_number(data['reach']):>9}  ER {format_pct(rate):>7}  "
            f"avg {data['avg_engagement']:>6} engagements/post"
        )
    lines.append("")

    times = best_posting_times(posts, followers_map)
    if times["top_slots"]:
        lines.append("Best times to post:")
        for slot in times["top_slots"][:5]:
            weekday, hour = slot["key"]
            lines.append(
                f"  {WEEKDAYS[weekday]:<9} {hour:02d}:00  {slot['avg_er']:>5}% ER  ({slot['posts']} posts)"
            )
        lines.append("")

    types = content_type_performance(posts, followers_map)
    if types:
        lines.append("Content types:")
        for row in types:
            lines.append(
                f"  {row['content_type']:<10} {row['posts']:>3} posts  "
                f"ER {format_pct(row['avg_er']):>7}  avg reach {format_number(int(row['avg_reach'])):>9}"
            )
        lines.append("")

    lines.append("Top posts:")
    for post in top_posts(posts, 5):
        rate = post.engagement_rate()
        caption = (post.caption or "(no caption)")[:60]
        lines.append(
            f"  [{post.platform}] {post.date.date()}  {format_number(post.engagement):>6} engagements  "
            f"ER {format_pct(rate):>7}  {caption}"
        )
    lines.append("")

    growth = follower_growth(snapshots)
    if growth:
        lines.append("Follower growth:")
        for platform, data in growth.items():
            lines.append(
                f"  {platform:<10} {format_number(data['from']):>8} → {format_number(data['to']):>8}  "
                f"({data['growth_pct']:+.2f}% over {data['days']} days)"
            )
        lines.append("")

    lines.append("Recommendations:")
    for finding in recommendations(posts, snapshots, followers_map):
        mark = {"tip": "💡", "warning": "⚠️", "info": "ℹ️"}.get(finding["severity"], "•")
        lines.append(f"  {mark} {finding['title']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- markdown

def markdown_report(
    posts: list[Post],
    snapshots: list[Snapshot],
    followers_map: dict | None = None,
    title: str = "Social Media Analytics Report",
) -> str:
    """Markdown report — paste it into a doc, a Notion page or an email."""
    followers_map = followers_map or {}
    lines = [f"# {title}", "", f"_Generated {datetime.now():%Y-%m-%d %H:%M} — "
             f"{len(posts)} posts analysed._", ""]
    if not posts:
        lines.append("No posts yet. Import a CSV export to get started.")
        return "\n".join(lines)

    summary = platform_summary(posts)
    lines += [
        "## Overview",
        "",
        f"- **Posts:** {summary['posts']}",
        f"- **Total reach:** {format_number(summary['reach'])}",
        f"- **Total engagement:** {format_number(summary['engagement'])}",
        f"- **Average ER:** {format_pct(summary['avg_er'])}",
        "",
        "## By platform",
        "",
        "| Platform | Posts | Reach | Engagement | ER | Avg/post |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for platform, data in per_platform_summary(posts, followers_map).items():
        rate = data["avg_er"]
        lines.append(
            f"| {platform} | {data['posts']} | {format_number(data['reach'])} | "
            f"{format_number(data['engagement'])} | {format_pct(rate)} | {data['avg_engagement']} |"
        )
    lines.append("")

    times = best_posting_times(posts, followers_map)
    if times["top_slots"]:
        lines += ["## Best times to post", ""]
        for slot in times["top_slots"][:5]:
            weekday, hour = slot["key"]
            lines.append(f"- **{WEEKDAYS[weekday]} {hour:02d}:00** — {slot['avg_er']}% ER ({slot['posts']} posts)")
        lines.append("")

    types = content_type_performance(posts, followers_map)
    if types:
        lines += ["## Content types", "",
                  "| Type | Posts | ER | Avg reach | Avg engagement |",
                  "|---|---:|---:|---:|---:|"]
        for row in types:
            lines.append(f"| {row['content_type']} | {row['posts']} | {format_pct(row['avg_er'])} | "
                         f"{format_number(int(row['avg_reach']))} | {row['avg_engagement']} |")
        lines.append("")

    lines += ["## Top posts", ""]
    for post in top_posts(posts, 10):
        caption = (post.caption or "(no caption)")[:100]
        lines.append(f"- **{post.platform}** · {post.date.date()} · "
                     f"{format_number(post.engagement)} engagements · ER {format_pct(post.engagement_rate())} — {caption}")
    lines.append("")

    tags = hashtag_performance(posts, followers_map)
    if tags:
        lines += ["## Hashtags", "",
                  "| Hashtag | Uses | Avg ER | Avg reach |",
                  "|---|---:|---:|---:|"]
        for row in tags[:15]:
            lines.append(f"| {row['hashtag']} | {row['uses']} | {format_pct(row['avg_er'])} | {format_number(int(row['avg_reach']))} |")
        lines.append("")

    trend = weekly_trend(posts)
    if len(trend) > 1:
        lines += ["## Weekly trend", "",
                  "| Week | Posts | Reach | Engagement | ER |",
                  "|---|---:|---:|---:|---:|"]
        for row in trend:
            lines.append(f"| {row['label']} | {row['posts']} | {format_number(row['reach'])} | "
                         f"{format_number(row['engagement'])} | {format_pct(row['avg_er'])} |")
        lines.append("")

    lines += ["## Recommendations", ""]
    for finding in recommendations(posts, snapshots, followers_map):
        lines.append(f"- **[{finding['severity']}]** {finding['title']} — {finding['detail']}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- json / csv

def json_report(posts: list[Post], snapshots: list[Snapshot], followers_map: dict | None = None) -> str:
    """Machine-readable report: summaries plus every post."""
    followers_map = followers_map or {}
    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "posts_analysed": len(posts),
        "overall": platform_summary(posts),
        "by_platform": per_platform_summary(posts, followers_map),
        "best_times": best_posting_times(posts, followers_map),
        "content_types": content_type_performance(posts, followers_map),
        "hashtags": hashtag_performance(posts, followers_map),
        "weekly_trend": weekly_trend(posts),
        "follower_growth": follower_growth(snapshots),
        "recommendations": recommendations(posts, snapshots, followers_map),
        "top_posts": [p.to_dict() for p in top_posts(posts, 10)],
        "posts": [p.to_dict() for p in posts],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def csv_export(posts: list[Post]) -> str:
    """All posts as CSV, with engagement and ER columns added."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "platform", "date", "caption", "content_type", "post_id", "likes",
        "comments", "shares", "saves", "reach", "impressions", "clicks",
        "followers_at_post", "engagement", "engagement_rate", "url",
    ])
    for post in sorted(posts, key=lambda p: p.date):
        writer.writerow([
            post.platform, post.date.isoformat(), post.caption, post.content_type,
            post.post_id, post.likes, post.comments, post.shares, post.saves,
            post.reach, post.impressions, post.clicks, post.followers_at_post,
            post.engagement, post.engagement_rate() or "", post.url,
        ])
    return buffer.getvalue()


# ---------------------------------------------------------------- html

def _svg_bars(rows: list[dict], width: int = 640, height: int = 180) -> str:
    """Simple SVG bar chart of weekly reach (no JavaScript needed)."""
    if not rows:
        return "<p>No weekly data yet.</p>"
    max_reach = max(r["reach"] for r in rows) or 1
    bar_width = width / len(rows)
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Weekly reach chart">']
    for i, row in enumerate(rows):
        bar_h = max(2, int(row["reach"] / max_reach * (height - 30)))
        x = i * bar_width + 4
        y = height - 22 - bar_h
        parts.append(
            f'<rect x="{x:.1f}" y="{y}" width="{bar_width - 8:.1f}" height="{bar_h}" rx="3" fill="#2563eb">'
            f'<title>{row["label"]}: {format_number(row["reach"])} reach, {row["posts"]} posts</title></rect>'
        )
        parts.append(
            f'<text x="{x + (bar_width - 8) / 2:.1f}" y="{height - 6}" font-size="10" text-anchor="middle" fill="#475569">{row["label"][5:]}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _heatmap_table(times: dict) -> str:
    """Weekday x hour heatmap of average ER (coloured cells)."""
    slots = {(s["key"][0], s["key"][1]): s["avg_er"] for s in times["top_slots"]}
    # Rebuild the full grid from the raw slot data is not possible here,
    # so the table shows the ranked slots; full grid lives in the CLI.
    if not slots:
        return "<p>Not enough posts with timestamps to build a heatmap yet (need 2+ posts per slot).</p>"
    max_er = max(slots.values()) or 1
    rows = ['<table class="heatmap"><tr><th></th>' + "".join(f"<th>{h:02d}</th>" for h in range(24)) + "</tr>"]
    for weekday in range(7):
        cells = [f"<td class='day'>{WEEKDAYS[weekday][:3]}</td>"]
        for hour in range(24):
            value = slots.get((weekday, hour))
            if value is None:
                cells.append("<td></td>")
            else:
                alpha = 0.15 + 0.85 * (value / max_er)
                cells.append(
                    f"<td style='background:rgba(37,99,235,{alpha:.2f});color:#fff'>{value}%</td>"
                )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    rows.append("</table>")
    return "".join(rows)


def html_report(
    posts: list[Post],
    snapshots: list[Snapshot],
    followers_map: dict | None = None,
    title: str = "Social Media Analytics Report",
) -> str:
    """Self-contained HTML dashboard (inline CSS + SVG, no JS)."""
    followers_map = followers_map or {}
    summary = platform_summary(posts)
    per_platform = per_platform_summary(posts, followers_map)
    times = best_posting_times(posts, followers_map)
    types = content_type_performance(posts, followers_map)
    tags = hashtag_performance(posts, followers_map)
    trend = weekly_trend(posts)
    findings = recommendations(posts, snapshots, followers_map)
    outliers = outlier_posts(posts)

    def stat(label: str, value: str) -> str:
        return f"<div class='stat'><div class='stat-value'>{_esc(value)}</div><div class='stat-label'>{_esc(label)}</div></div>"

    platform_rows = "".join(
        f"<tr><td>{_esc(platform)}</td><td>{data['posts']}</td>"
        f"<td>{format_number(data['reach'])}</td><td>{format_number(data['engagement'])}</td>"
        f"<td>{format_pct(data['avg_er'])}</td>"
        f"<td>{data['avg_engagement']}</td></tr>"
        for platform, data in per_platform.items()
    )
    type_rows = "".join(
        f"<tr><td>{_esc(row['content_type'])}</td><td>{row['posts']}</td>"
        f"<td>{format_pct(row['avg_er'])}</td><td>{format_number(int(row['avg_reach']))}</td>"
        f"<td>{row['avg_engagement']}</td></tr>"
        for row in types
    )
    tag_rows = "".join(
        f"<tr><td>{_esc(row['hashtag'])}</td><td>{row['uses']}</td>"
        f"<td>{format_pct(row['avg_er'])}</td><td>{format_number(int(row['avg_reach']))}</td></tr>"
        for row in tags[:15]
    )
    top_rows = "".join(
        f"<tr><td>{_esc(post.platform)}</td><td>{post.date.date()}</td>"
        f"<td>{format_number(post.engagement)}</td><td>{format_pct(post.engagement_rate())}</td>"
        f"<td>{_esc((post.caption or '(no caption)')[:90])}</td></tr>"
        for post in top_posts(posts, 10)
    )
    finding_items = "".join(
        f"<li class='{finding['severity']}'><strong>{_esc(finding['title'])}</strong><br>{_esc(finding['detail'])}</li>"
        for finding in findings
    )
    outlier_items = "".join(
        f"<li>{_esc(item['post'].platform)} · {item['post'].date.date()} · "
        f"<strong>{item['multiple']}x</strong> median engagement — {_esc(item['post'].caption[:90])}</li>"
        for item in outliers[:5]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; background: #f1f5f9; color: #0f172a; }}
header {{ background: #0f172a; color: #fff; padding: 28px 32px; }}
header h1 {{ margin: 0 0 6px; font-size: 26px; }}
header p {{ margin: 0; color: #94a3b8; }}
main {{ max-width: 960px; margin: 0 auto; padding: 24px; }}
section {{ background: #fff; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
h2 {{ margin-top: 0; font-size: 18px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 12px; }}
.stat {{ flex: 1 1 140px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; }}
.stat-value {{ font-size: 24px; font-weight: 700; }}
.stat-label {{ color: #64748b; font-size: 13px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th, td {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid #e2e8f0; }}
th {{ color: #64748b; font-weight: 600; }}
td:nth-child(n+2), th:nth-child(n+2) {{ text-align: right; }}
td:first-child, th:first-child {{ text-align: left; }}
.heatmap td {{ text-align: center; font-size: 11px; padding: 4px 2px; }}
.heatmap .day {{ font-weight: 600; }}
li.tip {{ border-left: 4px solid #2563eb; }}
li.warning {{ border-left: 4px solid #dc2626; }}
li.info {{ border-left: 4px solid #64748b; }}
ul.findings {{ list-style: none; padding: 0; }}
ul.findings li {{ padding: 10px 12px; margin-bottom: 8px; background: #f8fafc; border-radius: 6px; }}
footer {{ color: #64748b; font-size: 13px; text-align: center; padding-bottom: 24px; }}
</style>
</head>
<body>
<header><h1>{_esc(title)}</h1><p>Generated {datetime.now():%Y-%m-%d %H:%M} · {len(posts)} posts analysed</p></header>
<main>
<section><div class="stats">
{stat("Posts", str(summary["posts"]))}
{stat("Total reach", format_number(summary["reach"]))}
{stat("Total engagement", format_number(summary["engagement"]))}
{stat("Avg ER", format_pct(summary["avg_er"]))}
</div></section>
<section><h2>By platform</h2>
<table><tr><th>Platform</th><th>Posts</th><th>Reach</th><th>Engagement</th><th>ER</th><th>Avg/post</th></tr>
{platform_rows}</table></section>
<section><h2>Weekly reach</h2>{_svg_bars(trend)}</section>
<section><h2>Best times to post (avg ER)</h2>{_heatmap_table(times)}</section>
<section><h2>Content types</h2>
<table><tr><th>Type</th><th>Posts</th><th>ER</th><th>Avg reach</th><th>Avg engagement</th></tr>
{type_rows}</table></section>
<section><h2>Top posts</h2>
<table><tr><th>Platform</th><th>Date</th><th>Engagement</th><th>ER</th><th>Caption</th></tr>
{top_rows}</table></section>
<section><h2>Hashtags</h2>
<table><tr><th>Hashtag</th><th>Uses</th><th>Avg ER</th><th>Avg reach</th></tr>
{tag_rows}</table></section>
<section><h2>Outlier posts (1.5x+ median engagement)</h2><ul class="findings">{outlier_items or "<li>No outliers yet — import more posts.</li>"}</ul></section>
<section><h2>Recommendations</h2><ul class="findings">{finding_items}</ul></section>
</main>
<footer>Built with Social Media Analytics Dashboard — free, local, no API key.</footer>
</body>
</html>
"""
