讀取 PENDING_PATH，依照檔案開頭的說明抽取揭露事件。特別注意 trade_date：
每篇標題的時間是貼文日，不是交易日；只有原文明確寫出成交日期時才填，
沒寫就給 null，絕對不要拿貼文日充數，也不能晚於貼文日。

把答案寫成一個 JSON 檔到 ANSWERS_PATH（不是 PENDING_PATH 裡寫的 `events_*.json` 範例路徑，
就是這個 ANSWERS_PATH）。最外層是陣列，PENDING_PATH 裡的每一篇都要出現一次，
沒有交易事件就給空的 `events` 陣列。post_id 必須逐字照抄，不可自己造。

寫完檔案就結束，不要輸出摘要以外的東西。
