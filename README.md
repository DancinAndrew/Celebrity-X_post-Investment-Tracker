# Celebrity X-post Investment Tracker

追蹤選定 X 帳號的個股觀點、公開交易揭露與選擇權資訊，產生本機報告及 HTML 儀表板。

GitHub 公開保存程式碼、報告及網站快照；目前快照資料截至 **2026-10-08 台北時間 10:41:36**。持續執行的程式、原始貼文、資料庫及最新輸出仍在使用者的 Mac，推送不會自動更新 Mac 的執行副本。

**公開 Sites 儀表板：** https://x-post-tracker.andrew921031.chatgpt.site ，任何人可開啟，無需登入。10/8 台北時間 12:06:00 已成功發布 v3。
網站保留既有歷史資料、原文連結與判讀理由，展示最後抓取／判讀／資料匯出時間與缺口；目前採手動發佈快照。
網站上線不會將 X 抓取、Codex 分析或 Mac 排程移到雲端，也沒有自動同步。

## 目前狀態

- 10/8 快照含24,211篇貼文、18,508條原始訊號、805筆揭露事件及319,684列行情；相較最初接手備份累計新增7,642篇，其中7,627篇在原固定歷史範圍內。詳見[增量更新](reports/2026-10-08_增量更新與站點狀態.md)。
- 26小時觀點待辦及原範圍揭露待辦皆0；歷史仍有5篇股別疑義保留，連續歷史抓取未證實完整。缺資料與未判讀不算中立。
- 933個價格快取鍵／936個需求鍵；NSCL、OURA、TMHC尚無可用快取。部分標的行情過舊或不足兩個交易日，網站保留缺口，不補猜價格或實際報酬。
- 網站與GitHub快照保留897組歷史及9,369個X來源連結。公開版本只更改受眾標示與存取設定，資料時間不因發布而前移；[公開發布紀錄](reports/2026-10-08_公開發布.md)保存來源與驗證。
- 自動分類與揭露抽取已改由 **Codex** 執行，使用現有 ChatGPT 登入；排程不呼叫 Claude CLI 或 Anthropic API。
- Mac 原有排程：Asia/Taipei 每日 **02:00、08:00、14:00、20:00**。08點使用26小時抓取窗口，其餘使用10小時窗口。
- 最近資料修復在專案與執行副本各通過52項測試。原文、訊號、分類、揭露、交易者與原價格鍵均保留，歷次價格修訂有舊值審計紀錄。已有CLI及session全文判讀並存，網站分開標示判讀方式。
- 人工60列評測尚未裁決；分類準確率及報酬預測能力未驗證。交易者權重含先驗與價格代理模型，不能解讀為交易者實際績效。

## 查看輸出

- [公開線上儀表板](https://x-post-tracker.andrew921031.chatgpt.site)
- [10/8公開發布紀錄](reports/2026-10-08_公開發布.md)
- [10/8增量更新與資料狀態](reports/2026-10-08_增量更新與站點狀態.md)
- [網站原始碼與匯出工具](sites/x-post-tracker)
- [目前GitHub網站快照](sites/x-post-tracker/dist/index.html)：下載整個dist資料夾後開啟index.html，保留健康摘要與文字報告連結。
- [10/7執行健康檢查](reports/2026-10-07_執行健康檢查.md)
- [10/7資料修復進度](reports/2026-10-07_資料修復進度.md)
- [10/7網站部署紀錄](reports/2026-10-07_網站部署.md)
- [10/5 GitHub 報告快照](reports/2026-10-05.md)
- [歷史樣本觀察與涵蓋限制](reports/2026-10-04_歷史樣本觀察.md)
- [接手紀錄](reports/2026-10-04_接手與涵蓋.md)
- [較早的GitHub儀表板快照](dashboard.html.local)：保留原有檔案，時間與目前公開網站不同。

各報告與網站保留自己的快照時間。Mac上的新一輪排程只更新本機輸出，不自動commit、push或同步網站。

## 程式與執行

程式位於 [scripts/x_consensus](scripts/x_consensus)，操作與版本保存規則見
[README_CONTINUATION.md](scripts/x_consensus/README_CONTINUATION.md)。

本機執行目錄是 `~/Library/Application Support/xconsensus/app`，資料在同層 `data`，輸出在 `out`。
在新的 checkout 中驗證可執行：

```sh
cd scripts/x_consensus
python3 -m unittest discover -s tests -v
bash -n run.sh
bash -n fetch.sh
bash -n classify_auto.sh
bash -n disclosure_auto.sh
bash -n backfill.sh
```

正式執行需 Python 3.12、uv、已登入X的ego-browser，以及已登入ChatGPT的Codex。
此Mac優先使用ChatGPT桌面程式內附的Codex CLI（驗證時0.159.2）；可用`XC_CODEX_BIN`指定執行檔。
模型預設`gpt-6.1-sol`、推理medium；使用既有訂閱額度，不需新增API金鑰。

```sh
export XC_DATA_DIR="$HOME/Library/Application Support/xconsensus/data"
export XC_OUT_ROOT="$HOME/Library/Application Support/xconsensus/out"
# 在正式執行副本的app目錄執行；保留既有資料。
bash run.sh
```

Mac必須有使用者登入與網路，且X和ChatGPT/Codex登入有效。
睡眠期間不執行；喚醒後錯過的時段合併補跑一次，不能保證完整補回所有缺失歷史。
[launchd範例](scripts/x_consensus/launchd/com.andrew.xconsensus.plist.example)需要先替換路徑佔位符；它不會在clone時自動安裝。

## 判讀原則與歷史文件

股票方向stance與情緒tone分開；只有明確方向進共識。交易揭露不算意見票，缺資料或沉默不算中立。
同一帳號在同一窗口同時看多／看空列為mixed。模型回覆須先驗證，再追加保存；先前Claude資料不被覆寫。
完整判準見 [判準.md](判準.md)。

[00_分析與規劃.md](00_分析與規劃.md)、[01_v2規劃.md](01_v2規劃.md)及9月報告保留當時紀錄；
它們的排程、資料量與實作狀態不能代替本頁的10/8資料與發布紀錄。

憑證、cookie、原始資料、SQLite資料庫、模型執行日誌、虛擬環境與本機備份不納入此repository。
