"""Export only the existing rendered dashboard and a small health summary.

No database, cookies, login state, worker logs, or local path metadata is copied.
The Mac's collection/analysis scripts and launchd configuration are untouched.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent


def utc_mtime(path):
    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()


def taipei(value):
    moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime("%m/%d %H:%M:%S")


def number(pattern, value):
    found = re.search(pattern, value)
    if not found:
        raise ValueError("Required health evidence missing: " + pattern)
    return int(found.group(1))


def unique_history_by_account(progress, coverage=None):
    grouped = {}
    runs = set()
    for attempt in progress["accounts"]:
        assert attempt["run_id"] not in runs, "Duplicate history receipt"
        runs.add(attempt["run_id"])
        handle = attempt["handle"]
        row = grouped.setdefault(handle, {"handle": handle, "new_unique_posts": 0,
                                          "new_unique_in_scope": 0, "attempts": []})
        row["new_unique_posts"] += attempt["new_account_unique_non_retweets"]
        row["new_unique_in_scope"] += attempt["new_account_unique_in_scope"]
        fetch = attempt["fetch"]
        row.update(status=fetch["status"], stop_reason=fetch.get("stop_reason"),
                   oldest_returned_at_utc=fetch.get("oldest"))
        row["attempts"].append({"run_id": attempt["run_id"], "status": fetch["status"],
                                "stop_reason": fetch.get("stop_reason"),
                                "oldest_returned_at_utc": fetch.get("oldest")})
    for item in coverage or []:
        if item['handle'] in grouped:
            row = grouped[item['handle']]
            row['ingest_receipt_delta_posts'] = row['new_unique_posts']
            row['ingest_receipt_delta_in_scope'] = row['new_unique_in_scope']
            row['new_unique_posts'] = item['new_unique_nonretweet_posts']
            row['new_unique_in_scope'] = item['new_unique_in_scope']
    return list(grouped.values())


def export(runtime, metrics_path, progress_path, baseline_path):
    dashboard_path = runtime / "out/dashboard.html"
    dashboard = dashboard_path.read_text()
    metrics = json.loads(metrics_path.read_text())
    progress = json.loads(progress_path.read_text())
    baseline = json.loads(baseline_path.read_text())
    pending = number(r"(\d+) 篇尚未判讀立場", dashboard) if "篇尚未判讀立場" in dashboard else 0
    assert pending == metrics["pending_opinion_26h"], "Dashboard and coverage snapshot differ"
    total_posts = metrics["raw_posts"]
    new_posts = total_posts - baseline["raw_posts"]
    latest_post_match = re.search(r"最新入庫貼文（UTC）：([^。<]+)", dashboard)
    if latest_post_match is None:
        raise ValueError("Dashboard lacks latest post timestamp")
    generated_at = utc_mtime(dashboard_path)
    exported_at = dt.datetime.now(dt.timezone.utc).isoformat()
    accounts = []
    finished = []
    for item in metrics["latest_fetches"]:
        receipt = json.loads((runtime / "data/runs" / (item["run_id"] + ".json")).read_text())
        fetch = next(a for a in receipt["accounts"] if a["handle"] == item["handle"])
        accounts.append({key: fetch.get(key) for key in ("handle", "status", "tweets", "oldest", "newest", "stop_reason")})
        finished.append(receipt["finished_at_utc"])
    last_fetch = max(finished, key=lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00")))
    if dt.datetime.fromisoformat(generated_at) < dt.datetime.fromisoformat(last_fetch.replace("Z", "+00:00")):
        raise ValueError("A fetch newer than the frozen dashboard entered the snapshot")
    classified = metrics["last_codex_applied_at_utc"]
    # Retained results include native CLI batches and reviewed session answers.
    # Do not assign one CLI model to every result in this mixed snapshot.
    stance = {"state": "partial" if metrics["pending_stance_history"] else "applied", "version": "codex-session/v1", "model": None, "posts": metrics["codex_stance_posts"], "finished_at_utc": metrics["last_codex_stance_at_utc"]}
    disclosure = {"state": "partial" if metrics["pending_disclosure_history"] else "applied", "version": "codex-session/disc-v2", "model": None, "posts": metrics["codex_disclosure_posts"], "finished_at_utc": metrics["last_codex_disclosure_at_utc"]}
    price_status = json.loads((runtime / "data/prices/last_status.json").read_text())
    price_completed = price_status["finished_at_utc"]
    summary = {
        "schema_version": 2,
        "data_as_of_utc": metrics["checked_at_utc"],
        "site_snapshot_exported_at_utc": exported_at,
        "dashboard_generated_at_utc": generated_at,
        "last_fetch_completed_at_utc": last_fetch,
        "latest_post_at_utc": latest_post_match.group(1).strip(),
        "fetch_run_ids": sorted({f["run_id"] for f in metrics["latest_fetches"]}),
        "fetch_scope": "latest completed receipt per enabled account; overlapping snapshots are not unique posts",
        "report_window_hours": 26,
        "source_dashboard_sha256": hashlib.sha256(dashboard.encode()).hexdigest(),
        "new_posts": new_posts,
        "total_posts": total_posts,
        "snapshot_fetched_posts": sum(a["tweets"] or 0 for a in accounts),
        "active_accounts": len(accounts),
        "accounts": accounts,
        "pending_opinion_posts": pending,
        "stance_classification": {key: stance.get(key) for key in ("state", "version", "model", "posts", "finished_at_utc")},
        "disclosure_classification": {key: disclosure.get(key) for key in ("state", "version", "model", "posts", "finished_at_utc")},
        "price_download_failures": len(metrics["price_no_cache"]),
        "price_keys_without_cache": metrics["price_no_cache"],
        "price_cached_symbols": metrics["price_symbols"],
        "price_required_symbols": metrics["price_required_symbols"],
        "price_rows": metrics["prices"],
        "price_last_refresh_completed_at_utc": price_completed,
        "price_last_refresh_state": price_status["state"],
        "price_last_refresh_missing_keys": price_status["missing"],
        "analysis_methods": ["Codex CLI", "Codex session full-text review"],
        "price_cache_fewer_than_two_bars": metrics.get("price_cache_fewer_than_two_bars", []),
        "price_calendar_age_over_5_days": metrics["price_stale_cache"],
        "price_calendar_age_note": "Calendar age does not prove missed sessions. SSE is closed 2026-10-01 through 2026-10-07; September 30 is its latest completed session.",
        "historical_cutoff_utc": metrics["cutoff_utc"],
        "pending_stance_history": metrics["pending_stance_history"],
        "pending_disclosure_history": metrics["pending_disclosure_history"],
        "historical_coverage": metrics["coverage"],
        "historical_new_unique_by_account": unique_history_by_account(progress, metrics['coverage']),
        "historical_delta_basis": "post_id difference against the initial database backup; includes supported archived sources ingested by the existing daily run before the history wrapper",
        "cloud_auto_sync_enabled": False,
        "collection_location": "Mac",
        "schedule_timezone": "Asia/Taipei",
        "schedule_hours": [2, 8, 14, 20],
        "stale_after_hours": 7,
        "historical_coverage_complete": False,
        "classifier_human_evaluation_complete": False,
    }
    snapshot_state = "partial" if pending or summary["price_download_failures"] or summary["price_cache_fewer_than_two_bars"] or any(a["status"] != "ok" for a in accounts) or any(s.get("state") not in ("applied", "no_pending") for s in (stance, disclosure)) else "ok"
    summary["pipeline_state"] = snapshot_state

    # Preserve the existing dashboard's source links, model explanations and
    # history. Adapt its obsolete Claude instruction only in the hosted copy.
    styles = re.search(r"<style>(.*?)</style>", dashboard, re.S).group(1)
    content = dashboard[dashboard.index('<div class="wrap">'):]
    content = re.sub(r"</body>\s*</html>\s*$", "", content)
    content = content.replace('<div class="wrap">', '<main id="content" class="wrap">', 1)
    content = re.sub(r"</div>\s*$", "</main>", content)
    content = content.replace("在 Claude Code 說「分類 x_consensus 的待辦貼文」即可補上。", "Codex 仍需補判讀；本網站顯示目前已完成的資料快照。")
    content = content.replace("<h1>X 觀點共識儀表板</h1>", "")
    anchors = {"明確共同看多": "consensus", "個股總覽": "stocks", "交易風向：交易者權重": "traders", "揭露事件（依交易日，新到舊）": "disclosures", "抓取健康度": "fetch-health"}
    for title, anchor in anchors.items():
        content = content.replace(f"<h2>{title}</h2>", f'<h2 id="{anchor}">{title}</h2>')
    content = content.replace("失敗的帳號代表資料缺失，不代表該帳號今天沒發文。", "下表貼文時間為 UTC。失敗的帳號代表資料缺失，不代表該帳號今天沒發文。ok 只代表本輪抓取條件完成，不代表全部歷史完整。")
    content = re.sub(r"<footer>.*?</footer>", '<footer>由既有 X_post Investment Tracker 產生。網站資料採手動發佈快照；最新 Mac 資料未必已同步。<a href="report.txt">本輪原始報告</a> · <a href="health.json">資料與判讀版本</a></footer>', content, flags=re.S)
    status_text = "部分正常" if snapshot_state == "partial" else "本輪完成"
    header = f'''<a class="skip-link" href="#content">跳至資料</a>
<header class="site-header wrap"><div class="eyebrow">X POST / INVESTMENT TRACKER <span class="private-label">公開網站</span></div>
<div class="title-row"><div><h1>X 觀點投資追蹤</h1><p class="lede">把意見、語氣與公開交易揭露放回各自的位置。</p></div><label class="theme-label">外觀 <select id="theme"><option value="auto">跟隨系統</option><option value="light">淺色</option><option value="dark">深色</option></select></label></div>
<section class="health-panel" aria-labelledby="health-title"><div class="health-top"><h2 id="health-title">執行狀態 <span class="health-badge {snapshot_state}" id="pipeline-state">{status_text}</span></h2><span id="snapshot-age" role="status">資料快照時間如下</span></div>
<div class="health-metrics"><div><span>接手後累計新增</span><strong>{new_posts}</strong><small>以接手時備份為起點 · 共 {total_posts:,} 篇</small></div><div><span>最近抓取成功</span><strong>{sum(a['status'] == 'ok' for a in accounts)} <em>/ {len(accounts)}</em></strong><small>各帳號最近一次 · 部分抓取保留缺口</small></div><div><span>窗口待判讀觀點</span><strong>{pending}</strong><small>26 小時窗口 · 缺口仍保留</small></div><div><span>Codex 判讀完成</span><strong>{stance['posts']} <em>+ {disclosure['posts']}</em></strong><small>資料庫累計 · 立場 / 揭露</small></div></div>
<dl class="time-grid"><div><dt>最後收集嘗試</dt><dd><time datetime="{last_fetch}">{taipei(last_fetch)}</time></dd></div><div><dt>最後 Codex 判讀</dt><dd><time datetime="{classified}">{taipei(classified)}</time></dd></div><div><dt>本機儀表板產出</dt><dd><time datetime="{generated_at}">{taipei(generated_at)}</time></dd></div><div><dt>網站資料匯出</dt><dd><time datetime="{exported_at}">{taipei(exported_at)}</time></dd></div><div><dt>最後行情更新（{'部分完成' if price_status['state'] != 'applied' else '本輪完成'}）</dt><dd><time datetime="{price_completed}">{taipei(price_completed)}</time></dd></div></dl><p class="time-note">以上均為台北時間（UTC+8）。最新貼文：{taipei(summary['latest_post_at_utc'])}。</p>
<p class="known-gap"><b>待處理：</b>{pending} 篇窗口觀點尚未判讀；歷史立場尚待 {metrics['pending_stance_history']:,} 篇、揭露尚待 {metrics['pending_disclosure_history']} 篇；{summary['price_download_failures']} 個標的尚無價格快取，{len(summary['price_cache_fewer_than_two_bars'])} 個快取不足兩個交易日。有快取不代表行情歷史完整。陸股 10/1–10/7 休市，9/30 收盤不代表漏抓。價格不足時不計算報酬。</p>
<p class="sync-note"><b>網站可隨時開啟；抓文與分析仍在 Mac。</b>本頁是明確標時的快照，目前沒有自動同步。Mac 排程為台北 02、08、14、20 點，需使用者登入、網路及有效 X／ChatGPT 登入；睡眠期間延至喚醒合併補跑，長時間離線可能留下缺口。瀏覽器重新整理不會觸發抓文。</p>
</section><nav class="section-nav" aria-label="資料區段"><a href="#consensus">本輪共識</a><a href="#stocks">個股歷史</a><a href="#traders">交易者</a><a href="#disclosures">揭露事件</a><a href="#fetch-health">抓取紀錄</a></nav>
<div class="method-note"><b>閱讀原則</b>　只有意見帳號的明確股票方向進共識；情緒語氣與買賣揭露不算意見票，沉默與待判讀不算中立。歷史總覽保留原判讀與來源連結。交易者權重含先驗和價格代理，尚未驗證實際績效。<br>判讀來源：Codex；既有分類與本次全文判讀沿用相同判準。立場版本 {stance['version']}，揭露版本 {disclosure['version']}。</div>
<section class="search-tools" aria-label="搜尋歷史資料"><label for="history-search">搜尋個股或交易者</label><div class="search-row"><input id="history-search" type="search" placeholder="例如 US:MU、NVDA 或 Nancy Pelosi" autocomplete="off"><button id="clear-search" type="button">清除</button></div><p id="search-count" role="status" class="sub">輸入名稱可篩選下方歷史區塊，點開可看原文與判讀理由。</p></section></header>'''
    script = (ROOT / "site.js").read_text()
    document = '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="X 觀點與公開交易揭露追蹤，保留判讀來源、涵蓋缺口及更新時間。"><title>X 觀點投資追蹤</title><style>' + styles + '\n' + (ROOT / "site.css").read_text() + '</style></head><body>' + header + content + '<script type="application/json" id="snapshot-metadata">' + json.dumps(summary, ensure_ascii=False).replace('<', '\\u003c') + '</script><script>' + script + '</script></body></html>'
    # Stop an export containing credentials, local runtime paths, active resource
    # loads, or an unexpected instruction left in the hosted product.
    for forbidden in ("/Users/", "file://", "localhost", "access_token", "refresh_token", "session_token", "siwc_bypass", "BEGIN PRIVATE KEY", "在 Claude Code"):
        if forbidden in document:
            raise ValueError("Unsafe/unadapted output: " + forbidden)
    if re.search(r'<(?:iframe|script|img)[^>]+src=', document, re.I):
        raise ValueError("Unexpected external active resource")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text(document)
    (dist / "health.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    title_date = re.search(r"X 觀點共識 (\d{4}-\d{2}-\d{2})", dashboard).group(1)
    report = runtime / "out/reports" / (title_date + ".md")
    (dist / "report.txt").write_text(report.read_text())
    print(json.dumps({"new_posts": new_posts, "pending_opinion_posts": pending, "output_bytes": (dist / "index.html").stat().st_size, "exported_at_utc": exported_at}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path.home() / "Library/Application Support/xconsensus")
    parser.add_argument('--metrics', type=Path, required=True)
    parser.add_argument('--history-progress', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    export(args.runtime, args.metrics, args.history_progress, args.baseline)
