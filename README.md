# LinkedIn Auto-Poster

Automatically generate and publish LinkedIn posts from industry news, powered by AI.

> Built by a cloud architect who wanted to share Azure news without spending hours writing posts.
> This tool fetches news from RSS feeds, generates human-sounding drafts using AI, and publishes
> them through a GitHub PR approval workflow — so you stay in control of what gets posted.

## How It Works

```
RSS Feeds ──┐
             ├─→ Fetch & Score ──→ Research Agent ──→ AI Draft ──→ Critic Review
GitHub      ─┘       │                  │                │              │
Releases              │            (Learn search,   (Claude Opus)  (GPT-5.4)
                      │          Terraform verify)       │              │
                      │                                  └──────┬───────┘
                      │                                         │
                      └──→ Sanitize & Validate ←────────────────┘
                                    │
                              GitHub PR
                                    │
                           Human Approval
                          (approve-post label)
                                    │
                              LinkedIn API
```

### Example Use Case

I built this to automatically track Azure and cloud infrastructure news and draft LinkedIn posts
in my voice. Here's what a typical day looks like:

1. **06:00 UTC** — GitHub Actions fetches latest Azure Updates, Kubernetes blog, Terraform releases
2. **Scoring** — Each item scored by relevance (AKS, Landing Zones, IaC = high score for me)
3. **Research** — AI agent fetches source articles, verifies claims against Microsoft Learn docs
4. **Drafting** — Claude Opus generates a post in my writing style; GPT-5.4 critiques it
5. **Validation** — Banned AI phrases removed, PII checked, technical claims verified
6. **PR created** — One PR per draft with full preview. I review on my phone.
7. **Approve & Post** — Add `approve-post` label, merge → auto-publishes to LinkedIn

### Adapting for Your Use Case

This isn't Azure-specific — you can adapt it for any industry:

| Use Case | Feeds | Scoring Keywords |
|----------|-------|-----------------|
| Azure/Cloud (default example) | Azure Blog, K8s, Terraform | AKS, Landing Zone, Bicep |
| Frontend Dev | React Blog, CSS-Tricks, Smashing | React, Next.js, CSS |
| Data Science | Towards Data Science, Papers With Code | PyTorch, LLM, MLOps |
| Security | Krebs on Security, The Hacker News | CVE, Zero-day, SIEM |
| DevOps | DORA blog, DevOps.com, CNCF | CI/CD, GitOps, Platform |

Just update `config.yaml` with your feeds and `src/drafts/voice_profile.md` with your writing style.

## Prerequisites

| Requirement | Why | How to Get |
|-------------|-----|------------|
| Python 3.12+ | Runtime | [python.org](https://python.org) |
| GitHub account | PR workflow, Actions | [github.com](https://github.com) |
| GitHub Copilot subscription | AI model access (Claude, GPT) | [GitHub Copilot](https://github.com/features/copilot) |
| LinkedIn Developer App | Post to LinkedIn | [LinkedIn Developer Portal](https://developer.linkedin.com) |

### LinkedIn Developer App Setup

1. Go to [LinkedIn Developer Portal](https://developer.linkedin.com/apps)
2. Create a new app (company page required)
3. Under **Auth**, add redirect URL: `http://localhost:8080/callback`
4. Under **Products**, request access to **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**
5. Note your Client ID and Client Secret

> ⚠️ LinkedIn's API access can be restrictive. The "Share on LinkedIn" product is required for
> posting. Approval may take a few days.

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/your-username/linkedin-auto-poster.git
cd linkedin-auto-poster

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Initialize workspace (copies example configs)
python scripts/init.py
```

### 2. Configure your settings

Edit `config.yaml`:
- Set `author_name` to your name
- Add RSS feeds for your industry
- Adjust scoring keywords and thresholds
- Optionally add GitHub repos to monitor for releases

Edit `.env`:
- Add your LinkedIn credentials
- Add your GitHub token

### 3. Customize your voice

Edit `src/drafts/voice_profile.md`:
- Replace `[YOUR NAME]` with your name
- Replace `[YOUR ROLE]` with your job title
- Replace `[YOUR COMPANY]` with your employer
- Add your writing quirks, favorite phrases, typical post structure
- The more specific, the more human your posts will sound

### 4. Get LinkedIn access token

```bash
python scripts/linkedin_setup.py
```

Follow the browser prompts to authorize. The token will be saved to your `.env`.

### 5. Test it

```bash
# Fetch news (dry run — no posts created)
python main.py fetch

# Generate drafts (creates markdown files, no LinkedIn posting)
python main.py draft

# Check LinkedIn auth
python main.py preflight

# Preview what would be posted
python main.py publish --dry-run
```

### 6. Set up GitHub Actions (optional)

For automated daily runs:

1. Push to GitHub
2. Add secrets in repo Settings → Secrets:
   - `LINKEDIN_CLIENT_ID`
   - `LINKEDIN_CLIENT_SECRET`
   - `LINKEDIN_ACCESS_TOKEN`
3. Enable the `fetch-and-draft` workflow
4. Uncomment the cron schedule in `.github/workflows/fetch-and-draft.yml`

## Architecture

```
├── src/
│   ├── feeds/           # News fetching & scoring
│   │   ├── fetcher.py         # RSS feed fetcher with retry
│   │   ├── filter.py          # Relevance scoring & dedup
│   │   ├── article_fetcher.py # Full article content extraction
│   │   ├── research_agent.py  # AI research agent (Copilot SDK)
│   │   ├── research_tools.py  # Article fetch, Learn search, Terraform verify
│   │   ├── github_releases.py # GitHub Releases tracking
│   │   ├── repo_monitor.py    # New repo detection
│   │   └── tracker.py         # Feature lifecycle tracking
│   ├── drafts/          # Post generation
│   │   ├── drafter.py         # Dual-model AI pipeline
│   │   ├── copilot_client.py  # GitHub Copilot SDK wrapper
│   │   ├── validator.py       # Content safety & anti-AI detection
│   │   └── voice_profile.md   # Your writing style guide (customize!)
│   └── linkedin/        # Publishing
│       └── client.py          # LinkedIn API client
├── main.py              # CLI entry point
├── config.example.yaml  # Configuration template
├── content-topics.example.yaml  # Content calendar template
├── scripts/
│   ├── linkedin_setup.py    # OAuth setup helper
│   ├── linkedin_preflight.py # Auth validation
│   ├── preview_drafts.py    # PR preview generator
│   └── init.py              # Workspace initializer
└── .github/workflows/
    ├── fetch-and-draft.yml     # Daily news → draft pipeline
    ├── publish-approved.yml    # Label-approved → LinkedIn
    ├── preflight.yml           # Auth health check
    └── token-reminder.yml      # Token expiry alerts
```

## Configuration Reference

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LINKEDIN_CLIENT_ID` | Yes | LinkedIn app client ID |
| `LINKEDIN_CLIENT_SECRET` | Yes | LinkedIn app client secret |
| `LINKEDIN_ACCESS_TOKEN` | Yes | OAuth access token |
| `LINKEDIN_REFRESH_TOKEN` | No | Refresh token (if app tier supports) |
| `GITHUB_TOKEN` | Yes | GitHub PAT for API access |
| `GITHUB_USER` | No | Override GitHub username for repo monitoring |
| `AUTHOR_NAME` | No | Override author name (default: from config.yaml) |

### CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py fetch` | Fetch and score news from configured feeds |
| `python main.py draft` | Generate AI drafts for top-scoring items |
| `python main.py draft-topic` | Generate scheduled topic/opinion posts |
| `python main.py draft-repo` | Draft posts about new repos |
| `python main.py publish` | Publish approved posts to LinkedIn |
| `python main.py publish --dry-run` | Preview without posting |
| `python main.py preflight` | Check LinkedIn auth status |

## Security

- No secrets in code — everything via environment variables
- Content validation catches PII, customer names, monetary amounts
- SSRF protection on article fetching (private IP blocking)
- SHA-pinned GitHub Actions for supply chain security
- Prompt injection protection with data delimiters
- URL domain allowlist for linked content

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
