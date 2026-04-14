# LinkedIn Auto-Poster

Automatically generate and publish LinkedIn posts from industry news, powered by AI.

I built this because I wanted to stay active on LinkedIn without spending hours writing posts. As a cloud architect, I follow dozens of Azure, Kubernetes, and Terraform feeds daily  - this tool turns that firehose into polished, human-sounding LinkedIn posts that go through a PR-based approval workflow before anything gets published.

It was built for Azure/cloud news, but the feeds, scoring keywords, and voice profile are all configurable. You can adapt it for frontend development, data science, security, DevOps, or any other niche.

## How It Works

```
        RSS Feeds / GitHub Releases
                    |
              Fetch & Score
                    |
             Research Agent
     (article fetch, Learn search,
          Terraform verify)
                    |
        AI Draft  (Claude Opus)
                    |
       Critic Review  (GPT-5.4)
                    |
          Sanitize & Validate
    (banned phrases, PII, anti-AI)
                    |
               GitHub PR
        (one per draft, preview)
                    |
            Human Approval
     (approve-post label + merge)
                    |
              LinkedIn API
```

### Example Use Case

Here's how I use it for Azure news:

1. **06:00 UTC**  - GitHub Actions fetches the latest Azure Updates, Kubernetes blog, Terraform releases
2. **Scoring**  - Each item is scored by relevance (AKS, Landing Zones, IaC = high score for me)
3. **Research**  - An AI agent fetches source articles and verifies claims against Microsoft Learn docs
4. **Drafting**  - Claude Opus generates a post in my writing style; GPT-5.4 critiques it
5. **Validation**  - Banned AI phrases removed, PII checked, technical claims verified
6. **PR created**  - One PR per draft with full preview. I review on my phone
7. **Approve & Post**  - Add `approve-post` label, merge → auto-publishes to LinkedIn

### Adapting for Your Use Case

This is not Azure-specific. Update `config.yaml` with your feeds and keywords, and `src/drafts/voice_profile.md` with your writing style.

| Use Case | Example Feeds | Scoring Keywords |
|---|---|---|
| Azure/Cloud (default) | Azure Blog, K8s, Terraform | AKS, Landing Zone, Bicep |
| Frontend Dev | React Blog, CSS-Tricks, Smashing | React, Next.js, CSS |
| Data Science | Papers With Code, Towards DS | PyTorch, LLM, MLOps |
| Security | Krebs on Security, The Hacker News | CVE, Zero-day, SIEM |
| DevOps | DORA blog, CNCF, DevOps.com | CI/CD, GitOps, Platform |

## Prerequisites

| Requirement | Why | How to Get | Notes |
|---|---|---|---|
| Python 3.12+ | Runtime | [python.org](https://python.org) | 3.13+ also works |
| GitHub account | PR workflow, Actions, API | [github.com](https://github.com) | Free tier works |
| GitHub Copilot subscription | AI model access via Copilot SDK | [github.com/features/copilot](https://github.com/features/copilot) | Required for Claude/GPT access. Individual, Business, or Enterprise plan. |
| LinkedIn Developer App | Posting to LinkedIn | [developer.linkedin.com](https://developer.linkedin.com) | Requires a LinkedIn company page. "Share on LinkedIn" product must be approved. |
| Git | Version control | [git-scm.com](https://git-scm.com) | |

> **Note:** The AI models (Claude Opus, GPT-5.4) are accessed through the GitHub Copilot SDK  - you do not need separate OpenAI or Anthropic API keys.

## LinkedIn Developer App Setup

Setting up a LinkedIn developer app is the most involved step. Here's a walkthrough:

1. **Create the app** at [developer.linkedin.com/apps](https://developer.linkedin.com/apps). Click "Create app."
2. **Company page required**  - LinkedIn requires every developer app to be associated with a company page. If you don't have one, create a LinkedIn company page first (you can use your personal brand name).
3. **Auth tab**  - After creating the app, go to the **Auth** tab and add `http://localhost:8080/callback` as an authorized redirect URL.
4. **Products tab**  - Request access to:
   - **Share on LinkedIn** (required for posting)
   - **Sign In with LinkedIn using OpenID Connect** (required for authentication)
5. **Wait for approval**  - Product access can take a few hours to a few days. You can check the status on the Products tab.
6. **Copy credentials**  - From the **Auth** tab, copy your **Client ID** and **Client Secret**. You'll need these for the `.env` file.

> **Warning:** LinkedIn's API access can be restrictive. The "Share on LinkedIn" product is required for posting. If your app doesn't have it approved, the publish step will fail with a 403 error.

## Quick Start

### 1. Fork and clone

> **First:** Click the **Fork** button at the top-right of this repo to create your own copy. All commands below assume you're working from your fork.

**Linux / macOS:**
```bash
git clone https://github.com/<your-github-username>/linkedin-auto-poster.git
cd linkedin-auto-poster
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```powershell
git clone https://github.com/<your-github-username>/linkedin-auto-poster.git
cd linkedin-auto-poster
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Replace `<your-github-username>` with your actual GitHub username (the one you see at `github.com/<your-github-username>`).

### 2. Initialize workspace

```bash
python scripts/init.py
```

This copies the example configs to their working locations:
- `config.example.yaml` → `config.yaml`
- `.env.example` → `.env`
- `content-topics.example.yaml` → `content-topics.yaml`

### 3. Configure your settings

Edit `config.yaml`:
- Set `author_name` to your name
- Add RSS feeds for your industry
- Adjust `filter.include_keywords` and `filter.exclude_keywords`
- Set `filter.standalone_threshold` (default 12  - lower for more standalone posts)
- Optionally add GitHub repos to monitor under `github_releases`

Edit `.env`:
- Add your LinkedIn credentials (`LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`)
- Add your GitHub token (`GITHUB_TOKEN`)
- Set `GITHUB_USER` to your GitHub username (for repo monitoring)

### 4. Customize your voice

Edit `src/drafts/voice_profile.md`:
- Replace all `[YOUR NAME]` placeholders with your name
- Replace `[YOUR ROLE]` with your job title
- Replace `[YOUR COMPANY]` with your employer
- Replace `[X]` years with your actual experience
- Update the topic pillars, hashtags, and technical examples
- Add your own writing quirks and patterns

**Minimum changes to get started (change these 8 things first):**
1. `[YOUR NAME]`  - your actual name (appears ~15 times)
2. `[YOUR ROLE]`  - your job title
3. `[YOUR COMPANY]`  - your employer
4. `[X]` years  - your experience
5. Hashtags list (line 102)  - pick tags for YOUR niche
6. Topic pillars (line 117-120)  - YOUR content areas
7. Technical examples (line 82-84)  - tools YOU actually use
8. CTA patterns (line 109-112)  - YOUR repo URL

Everything else can stay as-is for your first draft. Refine later.

The more specific you are, the more human your posts will sound. Study your own emails, messages, and existing posts for patterns.

### 5. Get LinkedIn access token

```bash
python scripts/linkedin_setup.py
```

This opens your browser for LinkedIn authorization, captures the callback, exchanges the auth code for an access token, verifies it works, and updates your `.env` file.

To also set the GitHub Actions secret automatically:
```bash
python scripts/linkedin_setup.py --set-secret
```

### 6. Authenticate for AI (local development)

The Copilot SDK needs authentication to generate drafts. For local development, choose one:

**Option A: GitHub CLI (recommended)**
```bash
gh auth login
copilot auth login
```

**Option B: Environment variable**
Add to your `.env`:
```
COPILOT_GITHUB_TOKEN=your_fine_grained_pat_here
```
See the [PAT creation steps](#a-add-secrets) for how to create this token.

**Option C: Copilot CLI login**
```bash
copilot auth login
```
Follow the browser prompts.

Without authentication, `python main.py draft` will fail with "All models failed".

### 7. Test it

```bash
# Fetch and score news (creates data/candidates.json)
python main.py fetch

# Generate AI drafts (creates files in drafts/)
python main.py draft

# Check LinkedIn auth health
python main.py preflight

# Preview what would be posted (shows full post body)
python main.py publish --dry-run
```

### 8. Set up GitHub Actions (optional but recommended)

GitHub Actions automates the full pipeline  - fetch, draft, PR creation, and publishing. Here's how to set it up:

#### a. Add secrets

Go to your repo on GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**. Add these three:

| Secret name | Value | Where to find it |
|---|---|---|
| `LINKEDIN_CLIENT_ID` | Your LinkedIn app client ID | LinkedIn Developer Portal → Auth tab |
| `LINKEDIN_CLIENT_SECRET` | Your LinkedIn app client secret | LinkedIn Developer Portal → Auth tab |
| `LINKEDIN_ACCESS_TOKEN` | Your OAuth access token | Output of `python scripts/linkedin_setup.py` |
| `COPILOT_GITHUB_TOKEN` | A GitHub PAT with `copilot` scope | [github.com/settings/tokens](https://github.com/settings/tokens) |

> **Important: Copilot SDK authentication.** The automatic `GITHUB_TOKEN` provided by Actions does NOT have Copilot API access. You must create a Personal Access Token (PAT) and store it as `COPILOT_GITHUB_TOKEN`. The SDK reads this env var automatically. See [Copilot SDK auth docs](https://docs.github.com/en/copilot/how-tos/copilot-sdk/authenticate-copilot-sdk/authenticate-copilot-sdk) for details.
>
> **How to create the token (fine-grained PAT):**
> 1. Go to [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)
> 2. **Token name:** e.g. `linkedin-poster-copilot`
> 3. **Expiration:** choose your preference (90 days recommended, or no expiration)
> 4. **Repository access:** "Only select repositories" and pick your fork of this repo
> 5. **Account permissions** (NOT repository permissions):
>    - **GitHub Copilot** section: enable **Copilot Requests** (Read access)
> 6. Click **Generate token** and copy the `github_pat_...` value
> 7. In your repo: **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**
>    - Name: `COPILOT_GITHUB_TOKEN`
>    - Value: paste the token
>
> **Requirements:** You must have an active GitHub Copilot subscription (Individual, Business, or Enterprise).

#### b. (Optional) Add blocked names

If you want content safety to block specific company/customer names from appearing in posts:
- Go to **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
- Name: `BLOCKED_NAMES`, Value: one name per line

#### c. Enable the daily schedule

Open `.github/workflows/fetch-and-draft.yml` and uncomment the cron line:

```yaml
on:
  schedule:
    - cron: '0 6 * * 1-5'  # Weekdays at 06:00 UTC  - uncomment this
  workflow_dispatch:         # Manual trigger always available
```

Push the change. The workflow will now run automatically on weekday mornings.

> **Tip:** Before enabling the schedule, test with a manual run first. Go to **Actions** → **Fetch and Draft** → **Run workflow** → **Run workflow**. Check the output to make sure feeds are fetched and drafts are generated correctly.

#### d. Create the `approve-post` label

Go to your repo → **Issues** → **Labels** → **New label**:
- Name: `approve-post`
- Color: pick any (green suggested)
- Description: "Approve this draft for LinkedIn publishing"

This label is what triggers the publish workflow when you merge a PR.

#### e. Create the `linkedin-draft` label

Go to your repo → **Issues** → **Labels** → **New label**:
- Name: `linkedin-draft`
- Color: pick any (blue suggested)
- Description: "Auto-generated LinkedIn draft PR"

This label is automatically added to draft PRs by the workflow.

#### f. How the automation works once set up

```
Daily at 06:00 UTC (or manual trigger)
        ↓
fetch-and-draft.yml runs:
  1. Fetches RSS feeds + GitHub releases
  2. Scores and filters items
  3. Generates AI drafts
  4. Creates one PR per draft (with full preview in PR body)
        ↓
You review PRs on your phone/desktop:
  - Read the preview
  - Edit if needed (pencil icon on the draft file)
  - Add 'approve-post' label
  - Merge the PR
        ↓
publish-approved.yml triggers:
  1. Checks PR has 'approve-post' label
  2. File guard: verifies only drafts/*.md changed
  3. Posts to LinkedIn via API
  4. On failure: creates a GitHub issue alert
```

#### g. Which workflows run by default

Two workflows run on every push/PR without any configuration:
- **tests.yml**  - runs pytest and ruff linting
- **security.yml**  - runs pip-audit for dependency vulnerabilities

All other workflows require secrets or manual setup (see the table below).

### Troubleshooting your first run

| What you see | What's wrong | Fix |
|---|---|---|
| `config.yaml not found` | Didn't run init | `python scripts/init.py` |
| `All models failed` | No Copilot auth | Run `gh auth login` or set `COPILOT_GITHUB_TOKEN` in `.env` |
| `No candidates to draft` | No matching news items | Lower `standalone_threshold` in config.yaml or check your `include_keywords` |
| `Missing LINKEDIN_ACCESS_TOKEN` | Didn't run OAuth setup | `python scripts/linkedin_setup.py` |

## How Scoring Works

Every news item from RSS feeds goes through a scoring pipeline before drafting:

1. **Exclude keywords**  - Any match → item is immediately dropped (score 0)
2. **Include keywords**  - Count how many include keywords appear in the title + summary + categories. Zero matches → dropped.
3. **Update type weight**  - Classified from the text:
   - GA / "generally available" / "launched" → weight 3
   - Public preview → weight 2
   - Retirement / deprecated → weight 2
   - Private preview → weight 1
   - Blog / notice → weight 1
4. **Category double-weighting**  - Keywords found in RSS categories are counted separately and added again (categories are more reliable signals than free text)
5. **Final score** = `type_weight + include_hits + category_hits`
6. **Standalone threshold**  - Items scoring ≥ `standalone_threshold` (default: 12) get their own dedicated post. Items below that go into a weekly roundup post.
7. **High-relevance preview override**  - Public previews matching high-relevance keywords (AKS, Landing Zone, Terraform, AI Foundry, etc.) are promoted to standalone even if below threshold (max 2 per run).
8. **Dedup**  - Items are deduplicated by normalized URL and title hash against the seen state in `data/seen.json`.
9. **Age cutoff**  - Items older than `dedup_window_days` (default: 7) are skipped.

Tune these settings in `config.yaml` under the `filter:` section.

## How the Approval Workflow Works

The approval workflow ensures you review every post before it goes to LinkedIn:

1. **Draft generation**  - The `fetch-and-draft` workflow (or manual `python main.py draft`) generates markdown draft files in the `drafts/` directory.
2. **PR creation**  - One PR is created per draft, with a rich preview in the PR body showing exactly what will be posted.
3. **Review**  - You review the PR. The full post text is visible in the PR description. You can edit the draft by clicking "Files changed" and using the pencil icon.
4. **Approve**  - Add the `approve-post` label to the PR.
5. **Merge**  - Merge the PR into `main`.
6. **Publish**  - The `publish-approved.yml` workflow triggers automatically on merge. It checks that the PR has the `approve-post` label and that only files in `drafts/` were changed (security guard).
7. **File guard**  - If the PR contains changes to any file outside `drafts/`, publishing is blocked and a security issue is created.

Drafts that are not approved within 7 days are automatically closed by the workflow.

## Content Calendar

The content calendar (`content-topics.yaml`) lets you schedule opinion and thought-leadership posts on specific dates, separate from the news pipeline.

### Fields

| Field | Required | Description |
|---|---|---|
| `id` | Yes | Unique identifier (used in filenames and status tracking) |
| `title` | Yes | Post topic  - passed to the AI as the writing subject |
| `scheduled_for` | Yes | Date to generate draft (YYYY-MM-DD) |
| `status` | Yes | `planned` / `drafted` / `posted`  - only `planned` topics are drafted |
| `pattern` | Yes | Writing pattern from voice profile: `observation`, `lessons`, `share`, `showcase`, `reflection` |
| `pillar` | Yes | Content category: `cloud-architecture`, `career`, `iac-devops`, `security`, etc. |
| `notes` | No | Free-text guidance for the AI  - describe the angle, key points, or context |

### Usage

```bash
# Draft all planned topics within the next 7 days
python main.py draft-topic

# Draft a specific topic by ID
python main.py draft-topic --id iac-best-practices

# Draft from a free-text topic (no topics file needed)
python main.py draft-topic --topic "Why I switched from Helm to Kustomize"
```

## Voice Profile

The file `src/drafts/voice_profile.md` controls how the AI writes. It defines:

- **Writing patterns**  - How to structure different post types (observation, lessons, share, showcase, reflection)
- **Technical depth**  - What level of specificity to use
- **Formatting rules**  - No emoji, no em dashes, hashtag limits, character counts
- **Banned patterns**  - AI-sounding phrases that trigger validation failures
- **Anti-uniformity rules**  - Prevent every post from having the same 4-paragraph structure

The `pattern` field in content topics maps to a section in the voice profile. The AI uses that section to decide the post's structure.

The validator (`src/drafts/validator.py`) enforces these rules programmatically. It catches:
- Banned phrases (50+ AI-sounding patterns)
- Emoji and em/en dashes
- PII (emails, phone numbers, IP addresses, credentials)
- Customer/company names (from `data/blocked-names.txt`)
- URLs from unapproved domains

## Architecture

```
linkedin-auto-poster/
├── src/
│   ├── __init__.py            # StateStore: seen/published state with file locking
│   ├── feeds/                 # News fetching, scoring, research
│   │   ├── __init__.py        # Pydantic config model (AppConfig)
│   │   ├── fetcher.py         # RSS feed fetcher with retry + normalization
│   │   ├── filter.py          # Relevance scoring, dedup, threshold routing
│   │   ├── article_fetcher.py # Full article content extraction via HTTP
│   │   ├── research_agent.py  # Copilot SDK agentic research (tools enabled)
│   │   ├── research_tools.py  # Tool definitions: article fetch, Learn search, Terraform verify
│   │   ├── github_releases.py # GitHub Releases tracking (new versions)
│   │   ├── repo_monitor.py    # New repo detection (for showcase posts)
│   │   └── tracker.py         # Feature lifecycle tracking (preview → GA → deprecated)
│   ├── drafts/                # Post generation and validation
│   │   ├── __init__.py
│   │   ├── drafter.py         # Dual-model AI pipeline (draft + critique + validate)
│   │   ├── copilot_client.py  # Copilot SDK wrapper (raw generation, no tools)
│   │   ├── validator.py       # Content safety: banned phrases, PII, anti-AI detection
│   │   └── voice_profile.md   # Your writing style guide (customize this!)
│   └── linkedin/              # Publishing
│       ├── __init__.py
│       └── client.py          # LinkedIn API client: OAuth, token refresh, post creation
├── main.py                    # CLI entry point (click commands)
├── config.example.yaml        # Configuration template
├── content-topics.example.yaml # Content calendar template
├── .env.example               # Environment variables template
├── scripts/
│   ├── init.py                # Workspace initializer (copies example configs)
│   ├── linkedin_setup.py      # Interactive OAuth setup (browser-based)
│   ├── linkedin_preflight.py  # Auth validation (credentials + token + API)
│   └── preview_drafts.py      # PR preview generator (markdown for PR body)
├── data/                      # State files (gitignored except structure)
│   ├── seen.json              # Processed article URLs and title hashes
│   ├── published.json         # Published draft metadata (LLM memory)
│   ├── features.json          # Feature lifecycle state
│   ├── known_repos.json       # Known GitHub repos (for new repo detection)
│   └── token_refreshed_at.txt # Last LinkedIn token use timestamp
├── drafts/                    # Generated draft markdown files
├── tests/                     # pytest test suite
└── .github/workflows/
    ├── tests.yml              # Runs pytest + ruff on push/PR
    ├── security.yml           # pip-audit dependency scanning
    ├── fetch-and-draft.yml    # Fetches news, generates drafts, creates PRs
    ├── publish-approved.yml   # Posts approved drafts to LinkedIn on PR merge
    ├── preflight.yml          # Manual LinkedIn auth health check
    ├── token-reminder.yml     # Bi-monthly token expiry alerts
    └── copilot-setup-steps.yml # Copilot coding agent environment setup
```

## GitHub Actions Workflows

| Workflow | Trigger | What it does | Active by default |
|---|---|---|---|
| `tests.yml` | push, PR | Runs pytest + ruff | Yes |
| `security.yml` | push, PR, weekly cron | pip-audit dependency scanning | Yes |
| `fetch-and-draft.yml` | manual / cron (commented) | Fetches news, generates drafts, creates PRs | Manual only |
| `publish-approved.yml` | PR merge with `approve-post` label | Posts approved drafts to LinkedIn | Requires secrets |
| `preflight.yml` | manual | Checks LinkedIn auth health | Requires secrets |
| `token-reminder.yml` | bi-monthly cron | Creates issue if LinkedIn token is expiring | Requires secrets |
| `copilot-setup-steps.yml` | push to workflow file | Sets up Copilot coding agent environment | Yes |

## Configuration Reference

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LINKEDIN_CLIENT_ID` | Yes | LinkedIn app client ID (from Auth tab) |
| `LINKEDIN_CLIENT_SECRET` | Yes | LinkedIn app client secret (from Auth tab) |
| `LINKEDIN_ACCESS_TOKEN` | Yes | OAuth access token (from `scripts/linkedin_setup.py`) |
| `LINKEDIN_REFRESH_TOKEN` | No | Refresh token (only for certain LinkedIn app tiers) |
| `GITHUB_TOKEN` | Yes | GitHub API access (releases, repo monitoring). Alias: `GH_TOKEN` |
| `COPILOT_GITHUB_TOKEN` | Yes (for Actions) | Fine-grained PAT with **Copilot Requests** account permission. Required for AI draft generation in GitHub Actions. Create at [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new). |
| `GITHUB_USER` | No | GitHub username for repo monitoring. Fallback: `GITHUB_ACTOR` |
| `AUTHOR_NAME` | No | Override author name (default: from `config.yaml`) |

### config.yaml Reference

```yaml
author_name: "Your Name"        # Used in AI prompts

feeds:                           # RSS/Atom feeds to monitor
  - name: "Feed Name"
    url: "https://..."

filter:
  include_keywords: [...]        # Must match at least one
  exclude_keywords: [...]        # Any match → item dropped
  min_significance_score: 3      # Minimum score to keep
  max_posts_per_run: 5           # Cap on drafts per run
  standalone_threshold: 12       # Score for standalone post (vs roundup)

llm:
  provider: "azure_openai"
  model: "gpt-4o"
  temperature: 0.7
  max_tokens: 500

linkedin:
  visibility: "PUBLIC"           # PUBLIC or CONNECTIONS
  max_post_length: 1500

publish:
  max_age_days: 7                # Skip stale drafts
  dry_run: false                 # Preview mode

github_releases:                 # Optional: monitor specific repos
  - repo: "owner/repo"
    name: "Display Name"
    min_release_type: "minor"
```

> **Note:** `author_name` and `github_releases` are read directly from YAML outside the validated schema. All other sections (`feeds`, `filter`, `llm`, `linkedin`, `publish`) are validated via Pydantic on load.

### CLI Commands

| Command | Description |
|---|---|
| `python main.py fetch` | Fetch and score news from configured feeds |
| `python main.py draft` | Generate AI drafts for top-scoring items |
| `python main.py draft-topic` | Generate scheduled topic/opinion posts |
| `python main.py draft-topic --topic "Free text"` | Generate from ad-hoc topic |
| `python main.py draft-repo` | Draft posts about new GitHub repos |
| `python main.py draft-repo --repo owner/name` | Draft about a specific repo |
| `python main.py publish` | Publish approved drafts to LinkedIn |
| `python main.py publish --dry-run` | Preview full post body without posting |
| `python main.py preflight` | Check LinkedIn auth status |

## Token Renewal

LinkedIn access tokens expire every ~60 days. Here's how to renew:

1. Make sure `.env` has your `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET`
2. Run the setup script:
   ```bash
   python scripts/linkedin_setup.py
   ```
3. Authorize in the browser when prompted
4. The script will verify the new token and update your `.env`

For GitHub Actions, also update the secret:
```bash
python scripts/linkedin_setup.py --set-secret
```

The `token-reminder.yml` workflow creates a GitHub issue when your token is within 14 days of expiring. It checks the timestamp in `data/token_refreshed_at.txt`.

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `preflight` fails | Missing or expired access token | Run `python scripts/linkedin_setup.py` |
| No drafts generated | No new items above threshold | Lower `standalone_threshold` in `config.yaml`, or check your `include_keywords` |
| Repo monitoring skipped | `GITHUB_USER` not set | Set `GITHUB_USER` in `.env` for local runs |
| Publish fails with 403 | Expired LinkedIn token or missing "Share on LinkedIn" product | Renew via `linkedin_setup.py`; check LinkedIn app Products tab |
| State files missing | First run | Run `python scripts/init.py` |
| "All models failed" error | Copilot SDK authentication issue | Create a PAT with `copilot` scope and add as `COPILOT_GITHUB_TOKEN` secret. The automatic Actions GITHUB_TOKEN does not support Copilot API. |
| Draft validation fails | Post too short, banned phrases, PII detected | Check the validation errors in the log output  - the validator lists specific issues |
| PR not triggering publish | Missing `approve-post` label | Add the label before merging  - the workflow checks for it |
| `config.yaml` not found | First run without init | Run `python scripts/init.py` to create from template |

## Security

- No secrets in code - everything via environment variables or GitHub Secrets
- Branch protection on `main` - no direct pushes, all changes via PR
- Content validation catches PII, customer names, monetary amounts, credentials
- SSRF protection on research tools (private IP blocking)
- SHA-pinned GitHub Actions where possible
- Prompt injection protection with XML-style data delimiters
- URL domain warnings for unapproved content sources
- File guard on publish: only `drafts/*.md` changes trigger posting

### Branch protection note

This repo has branch protection enabled on `main` (no force push, no deletion). All changes go through PRs.

If you fork this for personal use in a **private repo**, you may want to relax branch protection since the GitHub Actions bot needs to push state files (seen.json, published.json) to main. Options:
- Add `github-actions[bot]` as a bypass actor in your ruleset
- Use the `state` branch approach (this repo's workflow already does this)
- Disable branch protection entirely if you're the only contributor

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT  - see [LICENSE](LICENSE).
