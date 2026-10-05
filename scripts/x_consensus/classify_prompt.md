你的任務只有一件：讀待分類檔，寫出答案檔。不要做其他事，不要修改任何其他檔案。

## 輸入

`PENDING_PATH` 這個檔案裡是待分類的 X 貼文，每篇以 `### <post_id> · <時間> · <型態>` 開頭。

## 輸出

把答案寫成一個 JSON 檔到 `ANSWERS_PATH`，最外層是陣列：

```json
[{"post_id":"2098016354250973657","is_list_or_market_wide":false,
  "signals":[{"symbol_as_written":"HOOD","company_name":"Robinhood","market_guess":"US",
              "stance":"bullish","tone":"positive","confidence":0.85,
              "reason_zh":"一句話說明為什麼判這個立場，要具體引到貼文內容",
              "evidence_quote":"從原文抄一小段，原文語言不要翻譯"}]}]
```

**待分類檔裡的每一篇都必須在答案裡出現一次**，即使它沒有任何個股訊號
（那就給空的 `signals` 陣列）。post_id 必須逐字照抄，不可自己造。

## 判準

每個訊號分開標兩件事：

- **stance**（`bullish` / `bearish` / `unclear`）——**唯一進共識計算的欄位，標準要嚴。**
- **tone**（`positive` / `negative` / `neutral`）——只顯示不投票，標準可以寬。

立場定義：

- `bullish`：作者認為這檔會漲、基本面轉好，或明確表達持有／買進傾向。
- `bearish`：作者認為這檔會跌、基本面轉壞，或明確表達賣出／看空傾向。
- `unclear`：有提到這檔，但看不出對股價的方向判斷。

必須遵守：

1. **只標具體個股。** 大盤、指數、ETF、總經、加密貨幣、商品都跳過。
2. **嘲諷產品不等於看空股票。** 「這支手機好醜」的 stance 是 `unclear`、tone 是 `negative`。
   把它算成看空會製造出不存在的共識，那是這個工具最致命的失效模式。
3. **反諷與雙重否定照語意判斷**，不要看字面。
   例：「not time to put down the semis」是看多。
4. **沒有 `$` 前綴的短字母串，只有你能指出公司名時才算個股。**
   PM、IT、ALL、NOW、BB、A、ON 這類極容易誤判；看不出是哪家公司就不要標。
5. **一篇貼文列出大量代碼**（例如「所有單字母代碼一覽」）屬於清單型內容，
   回空的 signals 並把 `is_list_or_market_wide` 設為 `true`。
   但如果作者明確表態（例如列出持股並說「我最看多」），那是觀點不是清單。
6. **帳號型別改變判讀寬嚴**（待分類檔的每個段落標題會註明）：
   - `opinion`：正常判立場。
   - `options_flow`：純數據播報給 `unclear`；作者有表達傾向才給方向。
   - `market_news`：轉述一律 `unclear`，除非作者加了自己的判斷。
   - `trade_disclosure`：一律 `unclear`。揭露別人的交易不是作者的觀點。
7. **引用型貼文的立場以引用者自己寫的那段為準**，被引用的原文只是脈絡。
   作者只轉貼沒加評論就給 `unclear`。
8. `symbol_as_written` 填**股票代碼**。原文只寫公司名沒寫 `$代碼` 時（例：「Samsung」），
   填你確定的上市代碼（`005930`）並把公司名寫進 `company_name`；不確定就不要標。
9. `confidence` 是你對這個判斷的把握（0 到 1）。語氣模糊、反諷、脈絡不足就壓低。
10. `reason_zh` 用繁體中文寫一句話，要具體引到貼文內容，不要寫「作者看多」這種空話。
11. `market_guess` 填該股主要掛牌市場：`US`、`KRX`、`KOSDAQ`、`SSE`、`SZSE`、
    `TWSE`、`TSE`、`HKEX` 其中之一。六碼數字特別容易搞混：005930 與 000660 是韓國（KRX），
    688xxx 與其他 6 開頭是上海（SSE），000001／002xxx／300xxx 是深圳（SZSE）。

寫完檔案就結束，不要輸出摘要以外的東西。
