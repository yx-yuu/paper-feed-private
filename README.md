# Automated Literature Precise Screening

This repo fetches RSS feeds (DBLP streams, arXiv RSS, ACM/Elsevier RSS), filters items by keyword rules, and writes a combined RSS XML feed (`filtered_feed.xml` by default).

## Quick start (local)

- Install: `pip install -r requirements.txt`
- Run (incremental): `python -B get_RSS.py --prune-existing`
- Run (rebuild from scratch): `python -B get_RSS.py --rebuild`

Config files:

- Sources: `journals.dat`
- Keywords: `keywords.dat` (high precision) or `keywords.broad.dat` (higher recall)

## Config via environment variables

- `RSS_JOURNALS`: newline- or `;`-separated RSS URLs (overrides `journals.dat`)
- `RSS_KEYWORDS`: newline- or `;`-separated keyword queries (overrides `keywords.dat`)
- `RSS_OUTPUT_FILE`: output file path (default: `filtered_feed.xml`)
- `RSS_MAX_ITEMS`: max items in output feed (default: `1000`)
- `RSS_USER_AGENT`: HTTP User-Agent string
- `RSS_FEISHU_WEBHOOK`: Feishu/Lark bot webhook URL (optional)

DBLP stream options:

- `RSS_DBLP_MAX_VOLUMES`: expand up to N volume/event pages per run (default: `1`)
- `RSS_DBLP_ENRICH_ARXIV`: set to `1` to fetch arXiv abstracts for DBLP entries whose `ee` link is arXiv
- `RSS_DBLP_ENRICH_MAX`: max number of arXiv enrichments per run (default: `30`)

## Rebuild via GitHub Actions

Trigger the `Auto RSS Fetch` workflow manually and set the `rebuild` input to `true`. Optionally enable `dblp_enrich_arxiv` to enrich DBLP entries with arXiv abstracts.

## Keyword query syntax

Each non-empty line is a query. A query can be a single term or `AND`-combined terms:

- `SAST`
- `LLM AND static analysis`
- `security specification AND vulnerability`

Prefix a term with `=` for case-sensitive exact matching (rarely needed).
