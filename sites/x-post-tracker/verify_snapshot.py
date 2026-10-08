"""Verify snapshot completeness, provenance links, and safe packaging inputs."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import hashlib
import datetime as dt
import argparse

ROOT = Path(__file__).resolve().parent


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = []
        self.details = 0
        self.data = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        self.details += tag == "details"

    def handle_data(self, data):
        self.data.append(data)


def verify(source_path=None):
    dist = ROOT / "dist"
    assert {p.name for p in dist.iterdir()} == {"index.html", "health.json", "report.txt"}, "Unexpected exported assets"
    metadata = json.loads((dist / "health.json").read_text())
    page = (dist / "index.html").read_text()
    parsed = Document()
    parsed.feed(page)
    assert len(parsed.ids) == len(set(parsed.ids)), "Duplicate IDs"
    assert parsed.details > 0, "Missing retained histories"
    assert '<meta name="viewport"' in page and '@media(max-width:640px)' in page
    assert '<main id="content"' in page and 'lang="zh-Hant"' in page
    for link in parsed.links:
        if link.startswith("#"):
            assert link[1:] in parsed.ids, "Broken anchor: " + link
        elif not link.startswith("https://"):
            assert link in {"report.txt", "health.json"}, "Unexpected link: " + link
    embedded = re.search(r'<script type="application/json" id="snapshot-metadata">(.*?)</script>', page, re.S)
    assert embedded and json.loads(embedded.group(1)) == metadata, "Mismatched metadata"
    assert metadata["cloud_auto_sync_enabled"] is False
    assert metadata["historical_coverage_complete"] is False
    assert metadata["classifier_human_evaluation_complete"] is False
    assert metadata["collection_location"] == "Mac"
    assert metadata["active_accounts"] == len(metadata["accounts"])
    assert metadata["snapshot_fetched_posts"] == sum(a["tweets"] for a in metadata["accounts"])
    history = metadata["historical_new_unique_by_account"]
    assert len({a["handle"] for a in history}) == len(history), "Repeated account coverage"
    history_runs = [attempt["run_id"] for a in history for attempt in a["attempts"]]
    assert len(history_runs) == len(set(history_runs)), "Repeated history attempt"
    assert all(0 <= a["new_unique_in_scope"] <= a["new_unique_posts"] for a in history)
    assert sum(a["new_unique_posts"] for a in history) <= metadata["new_posts"]
    assert metadata["stance_classification"]["version"].startswith("codex-session/")
    assert metadata["disclosure_classification"]["version"] == "codex-session/disc-v2"
    assert metadata["pipeline_state"] != "ok" or metadata["pending_opinion_posts"] == 0
    assert all(0 < item['daily_bars'] < 2 for item in metadata['price_cache_fewer_than_two_bars'])
    assert f"{len(metadata['price_cache_fewer_than_two_bars'])} 個快取不足兩個交易日" in page
    assert f'{metadata["pending_opinion_posts"]} 篇窗口觀點尚未判讀' in page
    for key in ("site_snapshot_exported_at_utc", "dashboard_generated_at_utc", "last_fetch_completed_at_utc", "latest_post_at_utc"):
        dt.datetime.fromisoformat(metadata[key].replace("Z", "+00:00"))
    for path in dist.iterdir():
        content = path.read_text()
        for forbidden in ("/Users/", "file://", "localhost", "access_token", "refresh_token", "session_token", "siwc_bypass", "BEGIN PRIVATE KEY"):
            assert forbidden not in content, (path.name, forbidden)
        assert not re.search(r"(?:sk-[A-Za-z0-9]{24,}|gh[pousr]_[A-Za-z0-9]{24,})", content), "Credential-like value"
    # If the source dashboard is unchanged since export, all original X post
    # links and every history disclosure must still be present, in order.
    source = source_path or Path.home() / "Library/Application Support/xconsensus/out/dashboard.html"
    if source_path is not None:
        assert source.exists(), "Missing frozen source dashboard"
        assert hashlib.sha256(source.read_bytes()).hexdigest() == metadata["source_dashboard_sha256"], "Frozen source provenance differs"
    if source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() == metadata["source_dashboard_sha256"]:
        original = Document()
        original.feed(source.read_text())
        assert original.details == parsed.details, "Lost history groups"
        assert [url for url in original.links if url.startswith("https://x.com/")] == [url for url in parsed.links if url.startswith("https://x.com/")], "Changed original source links"
    print(json.dumps({"verified": True, "history_groups": parsed.details, "original_x_links": sum(url.startswith("https://x.com/") for url in parsed.links), "assets": sorted(p.name for p in dist.iterdir()), "new_posts": metadata["new_posts"], "pending_opinions": metadata["pending_opinion_posts"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Require full provenance/link comparison against this frozen dashboard')
    verify(parser.parse_args().source)
