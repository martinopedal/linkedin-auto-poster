"""CLI entry point for linkedin-auto-poster.

Commands:
  fetch        - Fetch news from RSS feeds, score, deduplicate, save candidates
  draft        - Generate AI post drafts from fetched candidates (standalone + roundup)
  draft-topic  - Generate scheduled opinion/thought-leadership posts from content-topics.yaml
  draft-repo   - Generate showcase posts for newly created GitHub repos
  publish      - Publish approved drafts to LinkedIn (or --dry-run to preview)
  email-digest - Send email digest of scored news items to configured recipients
  preflight    - Validate LinkedIn API credentials and token health
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@click.group()
def main() -> None:
    """LinkedIn Auto-Poster: industry news to LinkedIn post drafts."""
    config_path = Path("config.yaml")
    if not config_path.exists():
        click.echo("Error: config.yaml not found. Run 'python scripts/init.py' first.")
        click.echo("See README.md Quick Start for setup instructions.")
        raise SystemExit(1)


@main.command()
@click.option("--config", default="config.yaml", help="Path to config file.")
def fetch(config: str) -> None:
    """Fetch news from RSS feeds, filter, score, and track lifecycle."""
    from src import StateStore
    from src.feeds import load_config
    from src.feeds.fetcher import fetch_all_feeds
    from src.feeds.filter import filter_and_score
    from src.feeds.tracker import FeatureTracker

    cfg = load_config(config)
    store = StateStore()
    tracker = FeatureTracker()

    # Load seen state
    seen = store.load_seen()
    seen_urls = set(seen.keys())
    seen_hashes = {v["title_hash"] for v in seen.values()}

    # Fetch RSS
    feeds = [{"url": f.url, "name": f.name} for f in cfg.feeds]
    items = fetch_all_feeds(feeds)
    click.echo(f"Fetched {len(items)} items from {len(feeds)} RSS feeds")

    # Fetch GitHub releases
    import yaml
    config_raw = yaml.safe_load(Path(config).read_text(encoding="utf-8"))
    gh_repos = config_raw.get("github_releases", [])
    if gh_repos:
        from src.feeds.github_releases import fetch_github_releases
        gh_items = fetch_github_releases(gh_repos, seen_urls)
        click.echo(
            f"Fetched {len(gh_items)} significant releases "
            f"from {len(gh_repos)} repos"
        )
        items.extend(gh_items)

    # Filter and score
    results = filter_and_score(
        items,
        cfg.filter.include_keywords,
        cfg.filter.exclude_keywords,
        min_score=cfg.filter.min_significance_score,
        max_items=cfg.filter.max_posts_per_run,
        seen_urls=seen_urls,
        seen_title_hashes=seen_hashes,
    )
    click.echo(f"Filtered to {len(results)} significant items")

    # Track lifecycle and apply boost
    boosted_results = []
    for item, score in results:
        event = tracker.track_item(item.title, item.link, item.published.isoformat())
        boost = event.priority_boost if event else 0
        boosted_results.append((item, score + boost, event))

    # Re-sort by boosted score
    boosted_results.sort(key=lambda x: x[1], reverse=True)

    # Save results for draft command (do NOT mark seen yet, that happens after drafts are saved)
    output = []
    for item, score, event in boosted_results:
        entry = {
            "title": item.title,
            "summary": item.summary,
            "link": item.link,
            "published": item.published.isoformat(),
            "categories": item.categories,
            "source_feed": item.source_feed,
            "score": score,
        }
        if event:
            entry["lifecycle"] = {
                "slug": event.slug,
                "stage": event.stage,
                "is_new": event.is_new,
                "is_progression": event.is_progression,
                "previous_stage": event.previous_stage,
                "priority_boost": event.priority_boost,
            }
        output.append(entry)
        click.echo(f"  [{score}] {item.title}")

    # Write candidates to temp file for draft command
    candidates_path = Path("data/candidates.json")
    candidates_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    click.echo(f"Saved {len(output)} candidates to {candidates_path}")


@main.command()
@click.option("--config", default="config.yaml", help="Path to config file.")
@click.option("--output-dir", default="drafts", help="Output directory for drafts.")
def draft(config: str, output_dir: str) -> None:
    """Generate LinkedIn post drafts from fetched candidates.

    High-significance items get standalone posts.
    Lower-significance items on the same topic get consolidated into roundups.
    Single low-significance items are skipped.
    """
    from src.drafts.drafter import (
        generate_draft,
        generate_roundup_draft,
        save_draft_to_file,
        save_roundup_to_file,
    )
    from src.feeds import load_config
    from src.feeds.fetcher import NewsItem
    from src.feeds.filter import is_high_relevance_preview
    from src.feeds.tracker import FeatureEvent, FeatureTracker

    cfg = load_config(config)
    tracker = FeatureTracker()
    candidates_path = Path("data/candidates.json")

    if not candidates_path.exists():
        click.echo("No candidates found. Run 'fetch' first.")
        sys.exit(1)

    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    if not candidates:
        click.echo("No candidates to draft.")
        return

    threshold = cfg.filter.standalone_threshold

    # Split into standalone (high score or high-relevance preview) and roundup
    standalone_entries = []
    roundup_entries = []
    preview_standalone_count = 0

    for entry in candidates:
        if entry["score"] >= threshold:
            standalone_entries.append(entry)
        else:
            # Check for high-relevance preview override
            from datetime import datetime
            item = NewsItem(
                title=entry["title"],
                summary=entry["summary"],
                link=entry["link"],
                published=datetime.fromisoformat(entry["published"]),
                categories=entry.get("categories", []),
                source_feed=entry.get("source_feed", ""),
            )
            if is_high_relevance_preview(item) and preview_standalone_count < 2:
                entry["is_preview_standalone"] = True
                standalone_entries.append(entry)
                preview_standalone_count += 1
                click.echo(
                    f"  Preview override [{entry['score']}]: {entry['title']}"
                )
            else:
                roundup_entries.append(entry)

    click.echo(
        f"Evaluating {len(candidates)} candidates: "
        f"{len(standalone_entries)} standalone (score >= {threshold}), "
        f"{len(roundup_entries)} for roundup"
    )

    drafted = 0
    store = None

    # Generate standalone posts for high-significance items
    for entry in standalone_entries:
        from datetime import datetime

        item = NewsItem(
            title=entry["title"],
            summary=entry["summary"],
            link=entry["link"],
            published=datetime.fromisoformat(entry["published"]),
            categories=entry.get("categories", []),
            source_feed=entry.get("source_feed", ""),
        )

        feature_event = None
        progression_summary = None
        lifecycle = entry.get("lifecycle")
        if lifecycle:
            feature_event = FeatureEvent(
                slug=lifecycle["slug"],
                name=item.title,
                stage=lifecycle["stage"],
                is_new=lifecycle["is_new"],
                is_progression=lifecycle["is_progression"],
                previous_stage=lifecycle.get("previous_stage"),
                first_seen=entry["published"],
                priority_boost=lifecycle["priority_boost"],
            )
            if feature_event.is_progression:
                progression_summary = tracker.get_progression_summary(
                    lifecycle["slug"]
                )

        draft_post = generate_draft(
            item=item,
            score=entry["score"],
            llm_config=cfg.llm.model_dump(),
            feature_event=feature_event,
            progression_summary=progression_summary,
        )

        if draft_post:
            path = save_draft_to_file(draft_post, output_dir)
            click.echo(f"  Standalone [{entry['score']}]: {path.name}")
            drafted += 1
            from src import StateStore

            store = store or StateStore()
            store.mark_seen(
                item.normalized_url, item.title_hash, item.source_feed
            )
        else:
            click.echo(f"  Skipped (generation failed): {item.title}")

    # Consolidate all lower-significance items into a roundup
    if len(roundup_entries) >= 1:
        from datetime import datetime

        roundup_items = []
        for entry in roundup_entries:
            item = NewsItem(
                title=entry["title"],
                summary=entry["summary"],
                link=entry["link"],
                published=datetime.fromisoformat(entry["published"]),
                categories=entry.get("categories", []),
                source_feed=entry.get("source_feed", ""),
            )
            roundup_items.append((item, entry["score"]))

        click.echo(
            f"  Consolidating {len(roundup_items)} items into roundup..."
        )
        roundup = generate_roundup_draft(roundup_items, cfg.llm.model_dump())

        if roundup:
            path = save_roundup_to_file(roundup, output_dir)
            click.echo(f"  Roundup: {path.name}")
            drafted += 1
            from src import StateStore

            store = store or StateStore()
            for item, _ in roundup_items:
                store.mark_seen(
                    item.normalized_url, item.title_hash, item.source_feed
                )
        else:
            click.echo("  Roundup generation failed")

    click.echo(f"Generated {drafted} drafts")


@main.command()
@click.option("--config", default="config.yaml", help="Path to config file.")
@click.option("--drafts-dir", default="drafts", help="Directory containing drafts.")
@click.option("--dry-run", is_flag=True, help="Validate but do not publish.")
def publish(config: str, drafts_dir: str, dry_run: bool) -> None:
    """Publish approved drafts to LinkedIn."""
    import frontmatter

    from src import StateStore
    from src.feeds import load_config
    from src.linkedin.client import LinkedInClient

    cfg = load_config(config)
    store = StateStore()
    client = LinkedInClient()
    effective_dry_run = dry_run or cfg.publish.dry_run

    if not effective_dry_run:
        client.ensure_access_token()

    # Find all draft files with publish: true
    drafts_path = Path(drafts_dir)
    if not drafts_path.exists():
        click.echo("No drafts directory found.")
        return

    published = 0
    skipped = 0

    for md_file in sorted(drafts_path.rglob("*.md")):
        if md_file.name == ".gitkeep":
            continue

        try:
            post = frontmatter.load(str(md_file))
        except Exception:
            logger.warning("Could not parse frontmatter: %s", md_file)
            continue

        draft_id = post.metadata.get("draft_id", md_file.stem)

        # Label-based approval: if the publish workflow was triggered,
        # the PR was merged with approve-post label. All drafts should publish.
        # Frontmatter publish:false is no longer checked.

        # Schedule gate: skip drafts scheduled for the future
        scheduled_for = post.metadata.get("scheduled_for", "")
        if scheduled_for:
            from datetime import date
            try:
                sched_date = date.fromisoformat(str(scheduled_for))
                if sched_date > date.today():
                    click.echo(f"  Not yet scheduled: {draft_id} (scheduled for {sched_date})")
                    skipped += 1
                    continue
            except ValueError:
                pass

        if store.is_published(draft_id):
            click.echo(f"  Already published: {draft_id}")
            skipped += 1
            continue

        # Check freshness
        from datetime import UTC, datetime, timedelta
        generated_at = post.metadata.get("generated_at", "")
        if generated_at:
            try:
                gen_date = datetime.fromisoformat(generated_at)
                if datetime.now(UTC) - gen_date > timedelta(days=cfg.publish.max_age_days):
                    if not post.metadata.get("force_publish", False):
                        click.echo(f"  Skipped (stale): {draft_id}")
                        skipped += 1
                        continue
            except ValueError:
                pass

        text = post.content
        source_url = post.metadata.get("source_url", "")

        # Ensure proper line breaks for LinkedIn rendering
        text = re.sub(r'([.!?])([A-Z])', r'\1\n\n\2', text)
        text = re.sub(r'([^\n])\n(- )', r'\1\n\n\2', text)

        if effective_dry_run:
            click.echo(f"  DRY RUN: {draft_id} ({len(text)} chars)")
            click.echo("  --- Post body ---")
            click.echo(text)
            click.echo("  --- End post body ---")
            published += 1
            continue

        try:
            urn = client.create_post(
                text=text,
                article_url=source_url,
                article_title=post.metadata.get("source_title", ""),
            )
            if urn:
                # Store condensed summary for LLM memory
                title = post.metadata.get("source_title", post.metadata.get("topic_title", draft_id))

                # Extract topic tags and tools from the post body
                hashtags = re.findall(r"#(\w+)", text)
                tools = [t for t in ["AKS", "Terraform", "Bicep", "Kubernetes", "Foundry", "Sentinel", "Defender"]
                         if t.lower() in text.lower()]

                store.mark_published(
                    draft_id, urn, source_url,
                    summary=f"{title}: {text[:150]}",
                    topic_tags=hashtags,
                    tools_mentioned=tools,
                    feature_slug=post.metadata.get("feature_slug", ""),
                )

                # Close lifecycle loop
                from src.feeds.tracker import FeatureTracker
                tracker = FeatureTracker()
                feature_slug = post.metadata.get("feature_slug", "")
                lifecycle_stage = post.metadata.get("lifecycle_stage", "")
                if feature_slug and lifecycle_stage:
                    tracker.mark_posted(feature_slug, lifecycle_stage)

                click.echo(f"  Published: {draft_id} -> {urn}")
                published += 1
        except Exception:
            logger.exception("Failed to publish: %s", draft_id)

    click.echo(f"Published {published} posts, skipped {skipped}")

    if not effective_dry_run and published > 0:
        store.update_token_timestamp()


@main.command(name="draft-topic")
@click.option("--config", default="config.yaml", help="Path to config file.")
@click.option("--topics-file", default="content-topics.yaml", help="Path to content topics file.")
@click.option("--output-dir", default="drafts", help="Output directory for drafts.")
@click.option("--id", "topic_id", default=None, help="Generate draft for a specific topic ID.")
@click.option("--topic", "free_topic", default=None, help="Generate draft from free-text topic.")
@click.option("--days-ahead", default=7, help="Generate drafts for topics scheduled within N days.")
def draft_topic(
    config: str,
    topics_file: str,
    output_dir: str,
    topic_id: str | None,
    free_topic: str | None,
    days_ahead: int,
) -> None:
    """Generate LinkedIn post drafts from content topics."""
    from datetime import date, timedelta

    import yaml

    from src.drafts.drafter import generate_topic_draft, save_topic_draft_to_file
    from src.feeds import load_config

    cfg = load_config(config)

    if free_topic:
        # Ad-hoc topic generation - clean up title for PR/display
        # Use first sentence or first 80 chars as the title
        clean_title = free_topic.split(".")[0].split("\n")[0][:80].strip()
        if not clean_title:
            clean_title = free_topic[:80].strip()
        topic = {
            "id": "adhoc-" + clean_title[:30].lower().replace(" ", "-"),
            "title": clean_title,
            "pattern": "lessons",
            "pillar": "cloud-architecture",
            "scheduled_for": str(date.today()),
            "notes": free_topic,  # Full prompt goes in notes for the LLM
        }
        click.echo(f"Generating draft for: {free_topic}")
        draft = generate_topic_draft(topic, cfg.llm.model_dump())
        if draft:
            path = save_topic_draft_to_file(draft, output_dir)
            click.echo(f"  Drafted: {path.name}")
        else:
            click.echo("  Failed to generate draft")
        return

    # Load content topics
    topics_path = Path(topics_file)
    if not topics_path.exists():
        click.echo(f"Topics file not found: {topics_path}")
        sys.exit(1)

    with open(topics_path, encoding="utf-8") as f:
        topics_data = yaml.safe_load(f)

    topics = topics_data.get("topics", [])
    if not topics:
        click.echo("No topics found in topics file.")
        return

    # Filter to target topics
    if topic_id:
        targets = [t for t in topics if t["id"] == topic_id]
        if not targets:
            click.echo(f"Topic not found: {topic_id}")
            sys.exit(1)
    else:
        # Generate for planned topics within days_ahead
        cutoff = date.today() + timedelta(days=days_ahead)
        targets = []
        for t in topics:
            if t.get("status") != "planned":
                continue
            sched = t.get("scheduled_for", "")
            if sched:
                try:
                    sched_date = date.fromisoformat(str(sched))
                    if sched_date <= cutoff:
                        targets.append(t)
                except ValueError:
                    pass

    if not targets:
        click.echo("No topics to draft (none scheduled within window or all already drafted).")
        return

    click.echo(f"Generating drafts for {len(targets)} topics...")
    drafted = 0

    for topic in targets:
        click.echo(f"  Topic: {topic['title']}")
        draft = generate_topic_draft(topic, cfg.llm.model_dump())
        if draft:
            path = save_topic_draft_to_file(draft, output_dir)
            click.echo(f"    Drafted: {path.name}")
            drafted += 1

            # Update status in topics file
            topic["status"] = "drafted"
            topic["draft_id"] = draft.draft_id
        else:
            click.echo("    Failed to generate draft")

    # Save updated topics file
    if drafted > 0:
        with open(topics_path, "w", encoding="utf-8") as f:
            yaml.dump(topics_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        click.echo(f"Updated {topics_path} with draft statuses")

    click.echo(f"Generated {drafted}/{len(targets)} topic drafts")


def _group_repos_by_week(repos: list[dict]) -> dict[tuple[int, int], list[dict]]:
    """Group repos by (iso_year, iso_week) based on created_at."""
    from datetime import datetime

    groups: dict[tuple[int, int], list[dict]] = {}
    for repo in repos:
        created_str = repo.get("created_at") or ""
        if not created_str:
            continue  # Skip repos with no creation date
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            key = created.isocalendar()[:2]  # (year, week)
        except (ValueError, AttributeError):
            continue  # Skip repos with invalid dates
        groups.setdefault(key, []).append(repo)
    return groups


def _is_current_week_ready(today=None) -> bool:
    """Current week is only ready to draft on Friday or later."""
    from datetime import date as _date

    today = today or _date.today()
    return today.weekday() >= 4  # Friday = 4


def _fetch_readme(full_name: str) -> str:
    """Fetch README excerpt for a repo."""
    import requests as req

    try:
        token = (os.environ.get("COPILOT_GITHUB_TOKEN")
                 or os.environ.get("GH_TOKEN")
                 or os.environ.get("GITHUB_TOKEN"))
        hdrs: dict[str, str] = {"Accept": "application/vnd.github.raw+json"}
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        r2 = req.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers=hdrs,
            timeout=15,
        )
        if r2.status_code == 200:
            return r2.text[:1500]
    except Exception:
        pass
    return ""


@main.command(name="draft-repo")
@click.option("--config", default="config.yaml", help="Path to config file.")
@click.option("--output-dir", default="drafts", help="Output directory.")
@click.option("--repo", default=None, help="Specific repo (owner/name) to draft about.")
def draft_repo(config: str, output_dir: str, repo: str | None) -> None:
    """Generate showcase drafts for newly created GitHub repos.

    When multiple repos are created in the same ISO week, they are consolidated
    into a single weekly showcase post. The current week only drafts on Friday
    or later (Mon-Thu repos are buffered). Use --repo to always draft individually.
    """
    from datetime import date

    import requests as req

    from src.drafts.drafter import generate_topic_draft, save_topic_draft_to_file
    from src.feeds import load_config
    from src.feeds.repo_monitor import check_new_repos, mark_repo_known

    cfg = load_config(config)

    # --repo flag: always draft individually
    if repo:
        token = os.environ.get("COPILOT_GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = req.get(
            f"https://api.github.com/repos/{repo}",
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            click.echo(f"Repo not found: {repo}")
            return
        r = resp.json()
        repo_info = {
            "name": r.get("name", ""),
            "full_name": r.get("full_name", ""),
            "description": r.get("description", "") or "",
            "html_url": r.get("html_url", ""),
            "language": r.get("language", "") or "",
            "created_at": r.get("created_at", ""),
        }
        readme_text = _fetch_readme(repo_info["full_name"])
        topic = {
            "id": f"repo-{repo_info['name']}",
            "title": f"New repo: {repo_info['name']} - {repo_info['description'][:80]}",
            "pattern": "showcase",
            "pillar": "iac-devops",
            "scheduled_for": str(date.today()),
            "notes": (
                f"New GitHub repo: {repo_info['full_name']}\n"
                f"Description: {repo_info['description']}\n"
                f"Language: {repo_info['language']}\n"
                f"URL: {repo_info['html_url']}\n"
                f"README excerpt: {readme_text[:500]}"
            ),
        }
        click.echo(f"  Drafting: {repo_info['full_name']}")
        draft = generate_topic_draft(topic, cfg.llm.model_dump())
        if draft:
            path = save_topic_draft_to_file(draft, output_dir)
            click.echo(f"    Saved: {path.name}")
            mark_repo_known(repo_info["full_name"])
        else:
            click.echo(f"    Failed to generate draft for {repo_info['full_name']}")
        return

    # Auto-detect mode: group by week and consolidate
    new_repos = check_new_repos()
    if not new_repos:
        click.echo("No new repos found.")
        return

    click.echo(f"Found {len(new_repos)} new repo(s)")

    current_week = date.today().isocalendar()[:2]
    week_groups = _group_repos_by_week(new_repos)

    for (year, week), repos_in_week in sorted(week_groups.items()):
        # Buffer current week until Friday
        if (year, week) == current_week and not _is_current_week_ready():
            click.echo(
                f"  Week {year}-W{week:02d}: {len(repos_in_week)} repo(s) buffered"
                " (current week, not Friday yet)"
            )
            continue

        if len(repos_in_week) == 1:
            # Single repo: draft individually
            repo_info = repos_in_week[0]
            readme_text = _fetch_readme(repo_info["full_name"])
            topic = {
                "id": f"repo-{repo_info['name']}",
                "title": f"New repo: {repo_info['name']} - {repo_info['description'][:80]}",
                "pattern": "showcase",
                "pillar": "iac-devops",
                "scheduled_for": str(date.today()),
                "notes": (
                    f"New GitHub repo: {repo_info['full_name']}\n"
                    f"Description: {repo_info['description']}\n"
                    f"Language: {repo_info['language']}\n"
                    f"URL: {repo_info['html_url']}\n"
                    f"README excerpt: {readme_text[:500]}"
                ),
            }
            click.echo(f"  Drafting: {repo_info['full_name']}")
            draft = generate_topic_draft(topic, cfg.llm.model_dump())
            if draft:
                path = save_topic_draft_to_file(draft, output_dir)
                click.echo(f"    Saved: {path.name}")
                mark_repo_known(repo_info["full_name"])
            else:
                click.echo(f"    Failed to generate draft for {repo_info['full_name']}")
        else:
            # 2+ repos: consolidated weekly showcase
            readme_excerpts = []
            for ri in repos_in_week:
                readme = _fetch_readme(ri["full_name"])
                if readme:
                    readme_excerpts.append(f"### {ri['name']}\n{readme[:500]}")

            topic = {
                "id": f"repo-week-{year}-W{week:02d}",
                "title": "Repos I open-sourced this week",
                "pattern": "showcase",
                "pillar": "iac-devops",
                "scheduled_for": str(date.today()),
                "notes": "\n".join([
                    f"- {ri['name']}: {ri['description'][:100]} ({ri['html_url']})"
                    for ri in repos_in_week
                ]) + "\n\nREADME excerpts:\n" + "\n".join(readme_excerpts),
            }

            click.echo(f"  Consolidating {len(repos_in_week)} repos for week {year}-W{week:02d}")
            draft = generate_topic_draft(topic, cfg.llm.model_dump())
            if draft:
                path = save_topic_draft_to_file(draft, output_dir)
                click.echo(f"    Saved: {path.name}")
                for ri in repos_in_week:
                    mark_repo_known(ri["full_name"])
            else:
                click.echo(f"    Failed to generate consolidated draft for week {year}-W{week:02d}")


@main.command(name="email-digest")
@click.option("--config", default="config.yaml", help="Path to config file.")
def email_digest(config: str) -> None:
    """Send email digest of scored news items to configured recipients."""
    from src.email_digest import send_digest

    success = send_digest()
    if success:
        click.echo("Digest sent successfully")
    else:
        click.echo("Digest not sent (check EMAIL_RECIPIENTS and SMTP config)")


@main.command(name="publish-scheduled")
@click.option("--config", default="config.yaml")
@click.option("--drafts-dir", default="drafts")
@click.option("--dry-run", is_flag=True)
def publish_scheduled(config: str, drafts_dir: str, dry_run: bool) -> None:
    """Publish posts that are due from the schedule queue."""
    from src.publish_queue import get_due_posts, mark_failed, mark_published

    due = get_due_posts()
    if not due:
        click.echo("No scheduled posts due.")
        return

    click.echo(f"Found {len(due)} scheduled post(s) due")

    for entry in due:
        draft_path = Path(entry["draft_path"])
        if not draft_path.exists():
            click.echo(f"  Draft not found: {draft_path}")
            mark_failed(entry["draft_id"], "Draft file not found")
            continue

        click.echo(f"  Publishing: {entry['draft_id']}")
        if dry_run:
            click.echo(f"    DRY RUN: would publish {draft_path}")
            continue

        try:
            import frontmatter

            from src import StateStore
            from src.linkedin.client import LinkedInClient

            post = frontmatter.load(str(draft_path))
            body = post.content.strip()

            # Ensure proper line breaks for LinkedIn rendering
            body = re.sub(r'([.!?])([A-Z])', r'\1\n\n\2', body)
            body = re.sub(r'([^\n])\n(- )', r'\1\n\n\2', body)

            client = LinkedInClient()
            client.ensure_access_token()
            urn = client.create_post(body)

            store = StateStore()
            store.mark_published(
                entry["draft_id"],
                urn,
                source_url=post.metadata.get("source_url", ""),
                summary=f"{post.metadata.get('title', '')}: {body[:150]}",
            )
            mark_published(entry["draft_id"])
            click.echo(f"    Published: {urn}")
        except Exception as e:
            mark_failed(entry["draft_id"], str(e))
            click.echo(f"    Failed: {e}")


@main.command()
def preflight() -> None:
    """Validate LinkedIn API access and token semantics."""
    import subprocess
    subprocess.run([sys.executable, "scripts/linkedin_preflight.py"], check=False)


if __name__ == "__main__":
    main()
