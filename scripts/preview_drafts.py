"""Generate markdown previews of draft posts for PR descriptions."""

from __future__ import annotations

import sys
from pathlib import Path

import frontmatter


def generate_preview(drafts_dir: str = "drafts") -> str:
    """Generate a markdown preview of all draft posts."""
    drafts_path = Path(drafts_dir)
    if not drafts_path.exists():
        return "No drafts found."

    sections = []
    draft_count = 0

    for md_file in sorted(drafts_path.rglob("*.md")):
        if md_file.name == ".gitkeep":
            continue

        try:
            post = frontmatter.load(str(md_file))
        except Exception:
            continue

        draft_count += 1
        meta = post.metadata
        content_type = meta.get("content_type", "news")
        scheduled = meta.get("scheduled_for", "")
        publish = meta.get("publish", False)
        status = "\u2705 Approved" if publish else "\u23f3 Pending review"

        if content_type == "topic":
            title = meta.get("topic_title", meta.get("draft_id", md_file.stem))
            pillar = meta.get("pillar", "")
            badge = "\U0001f4dd Content Strategy"
            source_line = f"**Pillar:** {pillar}" if pillar else ""
        else:
            title = meta.get("source_title", meta.get("draft_id", md_file.stem))
            source_url = meta.get("source_url", "")
            badge = "\U0001f4f0 News"
            source_line = f"**Source:** [{source_url}]({source_url})" if source_url else ""

        pattern = meta.get("pattern", "")
        schedule_line = f"\U0001f4c5 Scheduled for **{scheduled}**" if scheduled else ""

        section = f"""---

### {badge} {title}

{status} | Pattern: `{pattern}` | File: `{md_file.relative_to(drafts_path)}`
{schedule_line}
{source_line}

<blockquote>

{post.content.strip()}

</blockquote>

> **To approve:** Edit `{md_file.relative_to(drafts_path.parent)}` and change `publish: false` to `publish: true`
"""
        sections.append(section)

    if not sections:
        return "No draft posts found."

    header = f"""## \U0001f4cb LinkedIn Draft Preview

**{draft_count} draft(s)** generated. Review each post below and approve the ones you want published.

Posts with a `scheduled_for` date will not be published until that date arrives, even after approval.
"""

    return header + "\n".join(sections)


def generate_single_preview(draft_path: str) -> str:
    """Generate a preview for a single draft file."""
    md_file = Path(draft_path)
    try:
        post = frontmatter.load(str(md_file))
    except Exception:
        return "Could not parse draft file."

    meta = post.metadata
    content_type = meta.get("content_type", "news")

    if content_type == "topic":
        title = meta.get("topic_title", meta.get("draft_id", md_file.stem))
        pillar = meta.get("pillar", "")
        badge = "\U0001f4dd Content Strategy"
        source_line = f"**Pillar:** {pillar}" if pillar else ""
    elif content_type == "roundup":
        title = "Azure News Roundup"
        count = meta.get("source_count", 0)
        badge = "\U0001f4f0 Roundup"
        source_line = f"**{count} items** consolidated"
    else:
        title = meta.get("source_title", meta.get("draft_id", md_file.stem))
        source_url = meta.get("source_url", "")
        badge = "\U0001f4f0 News"
        source_line = f"**Source:** [{source_url}]({source_url})" if source_url else ""

    pattern = meta.get("pattern", "")
    scheduled = meta.get("scheduled_for", "")
    schedule_line = f"\U0001f4c5 Scheduled for **{scheduled}**" if scheduled else ""

    return f"""## {badge} {title}

**Pattern:** `{pattern}` | **File:** `{draft_path}`
{schedule_line}
{source_line}

---

### What will be posted to LinkedIn

> **Note:** Only the text between the lines below is posted.
> Everything else in this PR (metadata, instructions) stays on GitHub.

---

{post.content.strip()}

---

### How to approve, edit, or reject

| Action | How |
|---|---|
| **Approve as-is** | Add the `approve-post` label, then merge |
| **Edit the post** | Click **Files changed**, pencil icon on `.md` file, edit post body, commit, then approve |
| **Reject** | Close this PR |

### When does it post?

- **Immediately on merge** if no `scheduled_for` date or date has passed
- **Held until date arrives** if `scheduled_for` is in the future
- The `approve-post` label + merge together trigger publishing
"""


def get_title(draft_path: str) -> str:
    """Get a single-line PR title for a draft file."""
    md_file = Path(draft_path)
    try:
        post = frontmatter.load(str(md_file))
    except Exception:
        return md_file.stem

    meta = post.metadata
    content_type = meta.get("content_type", "news")
    if content_type == "topic":
        title = str(meta.get("topic_title", md_file.stem))
        prefix = "\U0001f4dd"
    elif content_type == "roundup":
        count = meta.get("source_count", 0)
        title = f"Azure News Roundup ({count} items)"
        prefix = "\U0001f4f0"
    else:
        title = str(meta.get("source_title", md_file.stem))
        prefix = "\U0001f4f0"

    # Ensure single line, no shell-breaking chars
    title = title.replace("\n", " ").replace("\r", "").strip()
    return f"{prefix} {title}"


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "single":
        draft_path = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else None
        preview = generate_single_preview(draft_path)
    elif len(sys.argv) >= 3 and sys.argv[1] == "title":
        print(get_title(sys.argv[2]))
        sys.exit(0)
    else:
        output_file = sys.argv[1] if len(sys.argv) > 1 else None
        preview = generate_preview()

    if output_file:
        Path(output_file).write_text(preview, encoding="utf-8")
    else:
        print(preview)
