# Celebrity X-post Investment Tracker

追蹤選定 X 帳號的個股觀點、公開交易揭露與選擇權資訊，產生本機報告及 HTML 儀表板。

截至 **2026-10-05**，GitHub 保存程式碼與報告快照；持續執行的程式、原始貼文、資料庫及最新輸出仍在使用者的 Mac。
這個 repository 沒有部署網站或雲端排程，推送不會自動更新 Mac 的執行副本。

## 目前狀態

- 自動分類與揭露抽取已改由 **Codex** 執行，使用現有 ChatGPT 登入；排程不呼叫 Claude CLI 或 Anthropic API。
- Mac 原有排程：Asia/Taipei 每日 **02:00、08:00、14:00、20:00**。08點使用26小時抓取窗口，其餘使用10小時窗口。
- 10/5已實際完成22篇 Codex 分類及9篇揭露抽取，新增19條股票訊號及1筆揭露事件；當時26小時分類／72小時揭露待辦均為0。
- 30項測試通過，shell語法與Python編譯檢查通過；既有原文、分類、揭露、交易者及價格資料列均完整保留。
- 原固定候選5,239篇觀點及636篇揭露已完成全文判讀；**歷史抓取仍不完整**，其他未命中候選預篩的歷史內容仍有待判讀。
- 人工60列評測尚未裁決；分類準確率及報酬預測能力未驗證。交易者權重含先驗與價格代理模型，不能解讀為交易者實際績效。

## 查看輸出

- [10/5最新報告快照](reports/2026-10-05.md)
- [歷史樣本觀察與涵蓋限制](reports/2026-10-04_歷史樣本觀察.md)
- [接手紀錄](reports/2026-10-04_接手與涵蓋.md)
- [儀表板快照](dashboard.html.local)：下載後用瀏覽器開啟；這不是已部署的網站。

上述檔案是本次提交時的快照。Mac上的新一輪排程只更新本機輸出，不自動commit或push。

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
它們的排程、資料量與實作狀態不能代替本頁的10/5查核結果。

憑證、cookie、原始資料、SQLite資料庫、模型執行日誌、虛擬環境與本機備份不納入此repository。
