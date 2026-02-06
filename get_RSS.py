import argparse
import feedparser
import json
import re
import os
import datetime
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urlunsplit
from rfeed import Item, Feed, Guid

def _env_int(name, default):
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        print(f"Warning: invalid int in {name}={value!r}; using default {default}.")
        return default


def _env_float(name, default):
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        print(f"Warning: invalid float in {name}={value!r}; using default {default}.")
        return default


# --- Configuration (env -> CLI -> defaults) ---
DEFAULT_USER_AGENT = os.environ.get(
    "RSS_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36",
).strip()
DEFAULT_OUTPUT_FILE = os.environ.get("RSS_OUTPUT_FILE", "filtered_feed.xml").strip()
DEFAULT_MAX_ITEMS = _env_int("RSS_MAX_ITEMS", 1000)
DEFAULT_JOURNALS_FILE = os.environ.get("RSS_JOURNALS_FILE", "journals.dat").strip()
DEFAULT_KEYWORDS_FILE = os.environ.get("RSS_KEYWORDS_FILE", "keywords.dat").strip()
DEFAULT_DBLP_MAX_VOLUMES = _env_int("RSS_DBLP_MAX_VOLUMES", 1)
DEFAULT_REQUEST_SLEEP_SEC = _env_float("RSS_REQUEST_SLEEP_SEC", 0.5)
DEFAULT_FEISHU_WEBHOOK = os.environ.get("RSS_FEISHU_WEBHOOK", "").strip()
DEFAULT_NOTIFY_MAX_ITEMS = _env_int("RSS_NOTIFY_MAX_ITEMS", 20)

OUTPUT_FILE = DEFAULT_OUTPUT_FILE
MAX_ITEMS = DEFAULT_MAX_ITEMS
DBLP_MAX_VOLUMES = DEFAULT_DBLP_MAX_VOLUMES
REQUEST_SLEEP_SEC = DEFAULT_REQUEST_SLEEP_SEC
FEISHU_WEBHOOK = DEFAULT_FEISHU_WEBHOOK
NOTIFY_MAX_ITEMS = DEFAULT_NOTIFY_MAX_ITEMS
# --------------------------------------------

# --- Journal/source abbreviation mapping ---
JOURNAL_ABBR = {
    # ScienceDirect (Elsevier)
    "ScienceDirect Publication: Computers & Security": "C&S",
    "ScienceDirect Publication: Information and Software Technology": "IST",
    "ScienceDirect Publication: Journal of Systems and Software": "JSS",
    "ScienceDirect Publication: SoftwareX": "SoftwareX",
    "ScienceDirect Publication: Science of Computer Programming": "SCP",

    # ACM Digital Library
    "Association for Computing Machinery: ACM Transactions on Software Engineering and Methodology: Table of Contents": "TOSEM",
    "Association for Computing Machinery: ACM Transactions on Programming Languages and Systems: Table of Contents": "TOPLAS",
    "Association for Computing Machinery: ACM Transactions on Privacy and Security: Table of Contents": "TOPS",
    "Association for Computing Machinery: ACM Computing Surveys: Table of Contents": "CSUR",
    "Association for Computing Machinery: Proceedings of the ACM on Programming Languages: Table of Contents": "PACMPL",
    "Association for Computing Machinery: Proceedings of the ACM on Software Engineering: Table of Contents": "PACMSE",

    # arXiv
    "cs.CR updates on arXiv.org": "arXiv-CR",
    "cs.SE updates on arXiv.org": "arXiv-SE",
    "cs.PL updates on arXiv.org": "arXiv-PL",
    "cs.AI updates on arXiv.org": "arXiv-AI",
    "cs.LG updates on arXiv.org": "arXiv-LG",
    "cs.CL updates on arXiv.org": "arXiv-CL",
    "cs.IR updates on arXiv.org": "arXiv-IR",
    "stat.ML updates on arXiv.org": "arXiv-statML",
}


DBLP_STREAM_ABBR = {
    # CCF A (SE / PL / Systems)
    "pldi": "PLDI",
    "popl": "POPL",
    "fse": "FSE",
    "sosp": "SOSP",
    "oopsla": "OOPSLA",
    "kbse": "ASE",
    "icse": "ICSE",
    "issta": "ISSTA",
    "osdi": "OSDI",
    "fm": "FM",

    # AI (A-tier)
    "aaai": "AAAI",
    "neurips": "NeurIPS",
    "nips": "NeurIPS",
    "acl": "ACL",
    "icml": "ICML",
    "ijcai": "IJCAI",

    # Security (top/strong venues)
    "sp": "S&P",
    "ccs": "CCS",
    "uss": "USENIXSec",
    "ndss": "NDSS",
    "eurosp": "EuroS&P",
    "raid": "RAID",
    "acsac": "ACSAC",

    # Journals (SE / Security)
    "tse": "TSE",
    "tsc": "TSC",
    "ase": "ASE",
    "ese": "ESE",
    "tdsc": "TDSC",
    "tifs": "TIFS",
    "ieeesp": "IEEE S&P",
    "compsec": "C&S",
}


def get_journal_abbr(journal_name):
    journal_name = (journal_name or "").strip()
    if not journal_name:
        return "UNK"

    normalized = re.sub(r"\s+", " ", journal_name)
    normalized = normalized.replace(" - new TOC", "")

    if normalized in JOURNAL_ABBR:
        return JOURNAL_ABBR[normalized]

    m = re.match(
        r"^dblp:\s+new\s+(?:issues|volumes)\s+for\s+streams/(?P<kind>conf|journals)/(?P<stream>[A-Za-z0-9_-]+)$",
        normalized,
    )
    if m:
        stream = m.group("stream")
        return DBLP_STREAM_ABBR.get(stream, stream.upper())

    # Generic arXiv fallback: "<cat> updates on arXiv.org"
    m = re.match(r"^(?P<cat>[A-Za-z]+\.[A-Za-z0-9]+) updates on arXiv\.org$", normalized)
    if m:
        cat = m.group("cat")
        suffix = cat.split(".", 1)[1] if cat.startswith("cs.") else cat.replace(".", "")
        return f"arXiv-{suffix}"

    cleaned = normalized
    for prefix in (
        "ScienceDirect Publication: ",
        "Association for Computing Machinery: ",
        "Wiley: ",
        "IEEE Transactions on ",
        "IEEE Journal of ",
    ):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    cleaned = cleaned.replace(": Table of Contents", "").replace("Table of Contents", "").strip()
    if not cleaned:
        return "UNK"

    words = re.findall(r"[A-Za-z0-9]+", cleaned)
    stop = {"of", "and", "the", "on", "for", "in", "to", "a", "an"}
    acronym = "".join(word[0].upper() for word in words if word.lower() not in stop)
    if 2 <= len(acronym) <= 8:
        return acronym

    return cleaned[:15] if len(cleaned) > 15 else cleaned


def _sleep_between_requests():
    if REQUEST_SLEEP_SEC <= 0:
        return
    time.sleep(REQUEST_SLEEP_SEC)


def _http_get_bytes(url, timeout=30, retries=3):
    last_error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": feedparser.USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 and attempt + 1 < retries:
                retry_after = (e.headers.get("Retry-After") or "").strip()
                delay = int(retry_after) if retry_after.isdigit() else 5 * (attempt + 1)
                print(f"Rate limited while fetching {url}; sleeping {delay}s ...")
                time.sleep(delay)
                continue
        except Exception as e:
            last_error = e
        time.sleep(2)

    if last_error:
        raise last_error
    raise RuntimeError(f"Failed to fetch {url}")


def _http_post_json(url, payload, timeout=20, retries=2):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = None

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "User-Agent": feedparser.USER_AGENT,
                    "Content-Type": "application/json; charset=utf-8",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.getcode(), resp.read()
        except urllib.error.HTTPError as e:
            body = b""
            try:
                body = e.read()
            except Exception:
                body = b""

            if e.code == 429 and attempt + 1 < retries:
                retry_after = (e.headers.get("Retry-After") or "").strip()
                delay = int(retry_after) if retry_after.isdigit() else 2 * (attempt + 1)
                time.sleep(delay)
                continue

            return e.code, body
        except Exception as e:
            last_error = e
            time.sleep(2)

    if last_error:
        raise last_error
    raise RuntimeError("Failed to POST JSON.")


def send_feishu_text(webhook_url, text):
    if not webhook_url:
        return False

    trimmed = (text or "").strip()
    if not trimmed:
        return False

    payload = {"msg_type": "text", "content": {"text": trimmed}}
    try:
        status, body = _http_post_json(webhook_url, payload, timeout=20, retries=2)
    except Exception as e:
        print(f"Warning: Feishu notification failed: {e}")
        return False

    if not (200 <= int(status) < 300):
        print(f"Warning: Feishu notification failed (HTTP {status}).")
        return False

    if body:
        try:
            resp = json.loads(body.decode("utf-8", errors="replace"))
        except Exception:
            resp = {}
        code = resp.get("code", resp.get("StatusCode"))
        if code not in (None, 0, "0"):
            msg = resp.get("msg", resp.get("StatusMessage", ""))
            print(f"Warning: Feishu notification failed (code={code}, msg={msg!r}).")
            return False

    print("Feishu notification sent.")
    return True


def _strip_url_fragment(url):
    parts = urlsplit(url)
    base = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    return base, parts.fragment


def _dblp_page_to_xml_url(page_url):
    base, fragment = _strip_url_fragment(page_url)
    if base.endswith(".xml"):
        return base, fragment
    if base.endswith(".html"):
        return base[:-5] + ".xml", fragment
    if base.endswith(".htm"):
        return base[:-4] + ".xml", fragment
    return base.rstrip("/") + ".xml", fragment


def _parse_dblp_issue_from_fragment(fragment):
    m = re.match(r"^nr(?P<num>[0-9]+)$", fragment or "")
    if not m:
        return None
    return m.group("num")


def _parse_dblp_stream_url(rss_url):
    m = re.match(
        r"^https?://dblp\.org/feed/streams/(?P<kind>conf|journals)/(?P<stream>[A-Za-z0-9_-]+)\.rss$",
        (rss_url or "").strip(),
    )
    if not m:
        return None
    return m.group("kind"), m.group("stream")


def _expand_dblp_stream_entries(feed, rss_url, stream_title):
    stream_info = _parse_dblp_stream_url(rss_url)
    if not stream_info:
        return None

    stream_kind, stream_name = stream_info
    expanded_entries = []

    for i, entry in enumerate(feed.entries[: max(DBLP_MAX_VOLUMES, 0)]):
        page_url = entry.get("link", "")
        if not page_url:
            continue

        pub_struct = entry.get("published_parsed", entry.get("updated_parsed"))
        pub_date = convert_struct_time_to_datetime(pub_struct)

        xml_url, fragment = _dblp_page_to_xml_url(page_url)
        issue_number = _parse_dblp_issue_from_fragment(fragment) if stream_kind == "journals" else None

        try:
            xml_bytes = _http_get_bytes(xml_url, timeout=30, retries=3)
        except Exception as e:
            print(f"Error fetching DBLP XML {xml_url}: {e}")
            continue
        finally:
            _sleep_between_requests()

        try:
            root = ET.fromstring(xml_bytes)
        except Exception as e:
            print(f"Error parsing DBLP XML {xml_url}: {e}")
            continue

        if stream_kind == "conf":
            pubs = root.findall(".//inproceedings") + root.findall(".//incollection")
        else:
            pubs = root.findall(".//article")

        for pub in pubs:
            if issue_number is not None:
                number = (pub.findtext("number") or "").strip()
                if number != issue_number:
                    continue

            title = (pub.findtext("title") or "").strip()
            if not title:
                continue

            ee = (pub.findtext("ee") or "").strip()
            url = (pub.findtext("url") or "").strip()
            link = ee or (f"https://dblp.org/{url}" if url else page_url)

            key = (pub.attrib.get("key") or "").strip()
            item_id = f"dblp:{key}" if key else link

            expanded_entries.append(
                {
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "summary": "",
                    "journal": stream_title,
                    "id": item_id,
                }
            )

    return expanded_entries

def load_config(filename, env_var_name=None):
    """Load newline/semicolon-separated config from env var (preferred) or file."""
    if env_var_name and os.environ.get(env_var_name):
        print(f"Loading config from environment variable: {env_var_name}")
        content = os.environ[env_var_name]
        if '\n' in content:
            return [line.strip() for line in content.split('\n') if line.strip()]
        else:
            return [line.strip() for line in content.split(';') if line.strip()]
            
    if os.path.exists(filename):
        print(f"Loading config from local file: {filename}")
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
    return []

# --- 新增：XML 非法字符清洗函数 ---
def remove_illegal_xml_chars(text):
    """
    移除 XML 1.0 不支持的 ASCII 控制字符 (Char value 0-8, 11-12, 14-31)
    """
    if not text:
        return ""
    # 正则表达式：匹配 ASCII 0-8, 11, 12, 14-31 这些控制字符
    # \x09是tab, \x0a是换行, \x0d是回车，这些是合法的，所以不删
    illegal_chars = r'[\x00-\x08\x0b\x0c\x0e-\x1f]'
    return re.sub(illegal_chars, '', text)

def convert_struct_time_to_datetime(struct_time):
    if not struct_time:
        return datetime.datetime.now()
    return datetime.datetime.fromtimestamp(time.mktime(struct_time))

def parse_rss(rss_url, retries=3):
    print(f"Fetching: {rss_url}...")
    try:
        rss_bytes = _http_get_bytes(rss_url, timeout=30, retries=retries)
        _sleep_between_requests()
    except Exception as e:
        print(f"Error fetching {rss_url}: {e}")
        return []

    try:
        feed = feedparser.parse(rss_bytes)
    except Exception as e:
        print(f"Error parsing {rss_url}: {e}")
        return []

    entries = []
    journal_title = feed.feed.get('title', 'Unknown Journal')

    dblp_entries = _expand_dblp_stream_entries(feed, rss_url, journal_title)
    if dblp_entries is not None:
        if dblp_entries:
            return dblp_entries
        print("Warning: DBLP stream expansion returned 0 items; falling back to raw RSS entries.")
    
    for entry in feed.entries:
        pub_struct = entry.get('published_parsed', entry.get('updated_parsed'))
        pub_date = convert_struct_time_to_datetime(pub_struct)
        
        entries.append({
            'title': entry.get('title', ''),
            'link': entry.get('link', ''),
            'pub_date': pub_date,
            'summary': entry.get('summary', entry.get('description', '')),
            'journal': journal_title,
            'id': entry.get('id', entry.get('link', ''))
        })
    return entries

def get_existing_items():
    # (保持不变，但增加容错：如果 XML 坏了，就返回空列表重新抓)
    if not os.path.exists(OUTPUT_FILE):
        return []
    
    print(f"Loading existing items from {OUTPUT_FILE}...")
    try:
        feed = feedparser.parse(OUTPUT_FILE)
        # 如果解析出错（比如现在的 invalid char），feedparser 可能会拿到空或者 bozo 标志
        if hasattr(feed, 'bozo') and feed.bozo == 1:
             print("Warning: Existing XML file might be corrupted. Ignoring old items.")
             # 这里可以选择 return [] 直接丢弃坏掉的旧数据，重新开始
             # return [] 
             # 或者尝试读取能读的部分（取决于损坏位置）
        
        entries = []
        for entry in feed.entries:
            pub_struct = entry.get('published_parsed')
            pub_date = convert_struct_time_to_datetime(pub_struct)
            
            entries.append({
                'title': entry.get('title', ''),
                'link': entry.get('link', ''),
                'pub_date': pub_date,
                'summary': entry.get('summary', ''),
                'journal': entry.get('author', ''),
                'id': entry.get('id', entry.get('link', '')),
                'is_old': True
            })
        return entries
    except Exception as e:
        print(f"Error reading existing file: {e}")
        return [] # 如果旧文件读不了，就当做第一次运行

def match_entry(entry, queries):
    # (保持不变)
    text_to_search = (entry['title'] + " " + entry['summary']).lower()
    for query in queries:
        keywords = [k.strip().lower() for k in query.split('AND')]
        match = True
        for keyword in keywords:
            if keyword not in text_to_search:
                match = False
                break
        if match:
            return True
    return False

def generate_rss_xml(items):
    """生成 RSS 2.0 XML 文件 (已加入非法字符清洗)"""
    rss_items = []
    
    items.sort(key=lambda x: x['pub_date'], reverse=True)
    items = items[:MAX_ITEMS]
    last_build_date = items[0]["pub_date"] if items else datetime.datetime.now()
    
    for item in items:
        title = item['title']
        abbr = get_journal_abbr(item['journal'])
        year = item['pub_date'].year
        title = f"[{abbr} {year}] {item['title']}"
            
        # --- 关键修改：清洗数据 ---
        clean_title = remove_illegal_xml_chars(title)
        clean_summary = remove_illegal_xml_chars(item['summary'])
        clean_journal = remove_illegal_xml_chars(item['journal'])
        # -----------------------

        rss_item = Item(
            title = clean_title,
            link = item['link'],
            description = clean_summary,
            author = clean_journal,
            guid = Guid(item['id']),
            pubDate = item['pub_date']
        )
        rss_items.append(rss_item)

    feed = Feed(
        title = "My Customized Papers",
        link = "https://github.com/your_username/your_repo",
        description = "Aggregated research papers",
        language = "en-US",
        lastBuildDate = last_build_date,
        items = rss_items
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(feed.rss())
    print(f"Successfully generated {OUTPUT_FILE} with {len(rss_items)} items.")

def parse_args():
    parser = argparse.ArgumentParser(description="Fetch RSS feeds, filter by keywords, and output an RSS feed.")
    parser.add_argument("--journals-file", default=DEFAULT_JOURNALS_FILE, help="Path to journals/source RSS list file.")
    parser.add_argument("--keywords-file", default=DEFAULT_KEYWORDS_FILE, help="Path to keywords query list file.")
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE, help="Output RSS filename.")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS, help="Max number of items in output RSS.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="HTTP User-Agent for fetching RSS feeds.")
    parser.add_argument(
        "--feishu-webhook",
        default=DEFAULT_FEISHU_WEBHOOK,
        help="Feishu/Lark bot webhook URL; if set, notify when new items are added.",
    )
    parser.add_argument(
        "--notify-max-items",
        type=int,
        default=DEFAULT_NOTIFY_MAX_ITEMS,
        help="Max items to include in notifications.",
    )
    parser.add_argument(
        "--dblp-max-volumes",
        type=int,
        default=DEFAULT_DBLP_MAX_VOLUMES,
        help="For DBLP stream RSS, expand up to this many volume/event pages per run.",
    )
    parser.add_argument(
        "--request-sleep-sec",
        type=float,
        default=DEFAULT_REQUEST_SLEEP_SEC,
        help="Sleep seconds between extra HTTP requests (e.g., DBLP XML expansion).",
    )
    return parser.parse_args()

def main():
    args = parse_args()
    global OUTPUT_FILE, MAX_ITEMS, DBLP_MAX_VOLUMES, REQUEST_SLEEP_SEC, FEISHU_WEBHOOK, NOTIFY_MAX_ITEMS
    OUTPUT_FILE = args.output_file
    MAX_ITEMS = args.max_items
    DBLP_MAX_VOLUMES = args.dblp_max_volumes
    REQUEST_SLEEP_SEC = args.request_sleep_sec
    FEISHU_WEBHOOK = args.feishu_webhook
    NOTIFY_MAX_ITEMS = args.notify_max_items
    feedparser.USER_AGENT = args.user_agent

    rss_urls = load_config(args.journals_file, 'RSS_JOURNALS')
    queries = load_config(args.keywords_file, 'RSS_KEYWORDS')
    
    if not rss_urls or not queries:
        print("Error: Configuration files are empty or missing.")
        return

    existing_entries = get_existing_items()
    seen_ids = set(entry['id'] for entry in existing_entries)
    
    all_entries = existing_entries.copy()
    new_entries = []
    new_count = 0

    print("Starting RSS fetch from remote...")
    for url in rss_urls:
        fetched_entries = parse_rss(url)
        for entry in fetched_entries:
            if entry['id'] in seen_ids:
                continue
            
            if match_entry(entry, queries) and entry['pub_date'].year >= 2022:
                all_entries.append(entry)
                seen_ids.add(entry['id'])
                new_entries.append(entry)
                new_count += 1
                print(f"Match found: {entry['title'][:50]}...")

    print(f"Added {new_count} new entries.")
    generate_rss_xml(all_entries)

    if new_count > 0 and FEISHU_WEBHOOK:
        limit = max(int(NOTIFY_MAX_ITEMS), 0)
        shown = new_entries[:limit] if limit else []

        lines = [f"Paper-Feed updated: +{new_count} new items"]
        for entry in shown:
            abbr = get_journal_abbr(entry.get("journal", ""))
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()

            if title and abbr:
                lines.append(f"- [{abbr}] {title}")
            elif title:
                lines.append(f"- {title}")

            if link:
                lines.append(f"  {link}")

        if len(new_entries) > len(shown):
            lines.append(f"... and {len(new_entries) - len(shown)} more")

        msg = "\n".join(lines)
        msg = msg[:3500]  # keep within typical webhook text limits
        send_feishu_text(FEISHU_WEBHOOK, msg)

if __name__ == '__main__':
    main()
