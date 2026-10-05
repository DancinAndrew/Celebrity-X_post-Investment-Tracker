"""把 fetch.sh 抓下來的原始 GraphQL 回應正規化成 raw_posts。

設計要點：
- 深度掃描整包 JSON 找 tweet 物件，而不是只看 `tweet-` 開頭的 entry。
  X 的自串樓會包成 `profile-conversation-*` entry，裡面才是 items[]；
  只看 `tweet-` 會把整串討論漏掉。
- 掃到的 tweet 包含「別人的」原文（被轉貼／被引用的那則），
  所以最後要用作者過濾，只留下我們正在抓的那個帳號發的。
- 長文（超過 280 字）的 legacy.full_text 會被截斷，完整內容在 note_tweet。
- 冪等：以 post_id 做 INSERT OR IGNORE，同一天重跑不會重複。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

TWEET_TYPES = {"Tweet", "TweetWithVisibilityResults"}


def _unwrap(node: dict[str, Any]) -> dict[str, Any]:
    if node.get("__typename") == "TweetWithVisibilityResults":
        return node.get("tweet") or {}
    return node


def _iter_tweets(node: Any, pinned_ids: set[str]) -> Iterator[tuple[dict[str, Any], bool]]:
    """深度走訪，吐出每個 tweet 物件與它是否為置頂。"""
    if isinstance(node, list):
        for item in node:
            yield from _iter_tweets(item, pinned_ids)
        return
    if not isinstance(node, dict):
        return
    if node.get("__typename") in TWEET_TYPES:
        tweet = _unwrap(node)
        legacy = tweet.get("legacy")
        if isinstance(legacy, dict) and legacy.get("id_str"):
            yield tweet, legacy["id_str"] in pinned_ids
    for value in node.values():
        yield from _iter_tweets(value, pinned_ids)


def _collect_pinned_ids(payload: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        instructions = node.get("instructions")
        if isinstance(instructions, list):
            for ins in instructions:
                if ins.get("type") != "TimelinePinEntry":
                    continue
                for tweet, _ in _iter_tweets(ins.get("entry"), set()):
                    found.add(tweet["legacy"]["id_str"])
        for value in node.values():
            walk(value)

    walk(payload)
    return found


def _screen_name(tweet: dict[str, Any]) -> str | None:
    core = (tweet.get("core") or {}).get("user_results", {}).get("result", {})
    name = (core.get("core") or {}).get("screen_name")
    return name or (core.get("legacy") or {}).get("screen_name")


def _full_text(tweet: dict[str, Any]) -> str:
    note = (
        (tweet.get("note_tweet") or {})
        .get("note_tweet_results", {})
        .get("result", {})
        .get("text")
    )
    if note:
        return note
    return (tweet.get("legacy") or {}).get("full_text", "")


def _symbols(tweet: dict[str, Any]) -> list[str]:
    entities = (tweet.get("legacy") or {}).get("entities") or {}
    out = [s.get("text") for s in (entities.get("symbols") or []) if s.get("text")]
    return sorted({s.upper() for s in out})


def _parse_created(value: str) -> str:
    return (
        datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
        .astimezone(timezone.utc)
        .isoformat()
    )


def parse_tweet(tweet: dict[str, Any], is_pinned: bool, fetched_at: str) -> dict[str, Any] | None:
    legacy = tweet.get("legacy") or {}
    author = _screen_name(tweet)
    if not legacy.get("id_str") or not legacy.get("created_at") or not author:
        return None

    retweet = legacy.get("retweeted_status_result", {}).get("result")
    quote = tweet.get("quoted_status_result", {}).get("result")
    retweet = _unwrap(retweet) if isinstance(retweet, dict) else None
    quote = _unwrap(quote) if isinstance(quote, dict) else None

    if retweet:
        kind = "retweet"
        original_id = (retweet.get("legacy") or {}).get("id_str")
        original_author = _screen_name(retweet)
        # 轉貼的 full_text 是 "RT @xxx: ..." 截斷版，要用原文全文才能分類
        text = _full_text(retweet)
    elif legacy.get("in_reply_to_status_id_str"):
        kind = "reply"
        original_id = legacy.get("in_reply_to_status_id_str")
        original_author = legacy.get("in_reply_to_screen_name")
        text = _full_text(tweet)
    elif quote:
        kind = "quote"
        original_id = (quote.get("legacy") or {}).get("id_str")
        original_author = _screen_name(quote)
        # 引用要把自己的評論與被引用的原文一起給分類器，否則看不懂在講什麼
        text = f"{_full_text(tweet)}\n\n[引用 @{original_author}]: {_full_text(quote)}"
    else:
        kind = "original"
        original_id = None
        original_author = None
        text = _full_text(tweet)

    return {
        "post_id": legacy["id_str"],
        "author_handle": author,
        "created_at_utc": _parse_created(legacy["created_at"]),
        "text": text,
        "lang": legacy.get("lang"),
        "kind": kind,
        "original_post_id": original_id,
        "original_author": original_author,
        "conversation_id": legacy.get("conversation_id_str"),
        "is_pinned": int(is_pinned),
        "symbols_json": json.dumps(_symbols(tweet), ensure_ascii=False),
        "url": f"https://x.com/{author}/status/{legacy['id_str']}",
        "source": "ego-browser/graphql",
        "fetched_at_utc": fetched_at,
    }


def parse_file(path: Path, expect_handle: str) -> list[dict[str, Any]]:
    """解析單一 payload 檔，只回傳 expect_handle 本人發的貼文。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    pinned = _collect_pinned_ids(payload)
    fetched_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()

    rows: dict[str, dict[str, Any]] = {}
    for tweet, is_pinned in _iter_tweets(payload, pinned):
        record = parse_tweet(tweet, is_pinned, fetched_at)
        if record is None:
            continue
        # 過濾掉被轉貼／被引用的「別人的原文」，那些不是這個帳號的觀點
        if record["author_handle"].lower() != expect_handle.lower():
            continue
        rows[record["post_id"]] = record
    return list(rows.values())
