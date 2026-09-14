# 分類裁決 · 版本 `claude-code-session/v1`

A 區 45 列（意見帳號訊號，影響共識結論者排前面）、B 區 15 列（抽查漏標）。

> [!important] 只有**立場**進共識計算，語氣只顯示不投票。
> 所以裁決時問的是「這個立場對不對」，不是「這個語氣對不對」。

判準的完整說明與理由在 [[判準]]。**先看那份文件的第 1 條**——立場與語氣為什麼分開兩欄、嘲諷產品為什麼不算看空。
如果你不同意那條判準本身，就不必逐列改：直接說，我改判準再全部重跑。

**怎麼填**：
- A 區：空白＝同意。不同意就寫 `bullish` / `bearish` / `unclear`，或寫 `none` 表示這裡根本不該有訊號。
- B 區：空白＝同意（確實沒有個股訊號）。有漏標就寫 `US:AMD=bullish`，多筆用逗號分隔。
- 填完執行 `python3 -m x_consensus.evalset score`。

---

> [!tip] 時間不夠就只做這幾列
> 我信心低於 0.5 的判斷：A1、A2、A3、A4、A5、A17、A18、A19、A20、A21、A22、A23、A24、A25。這些是最可能標錯、也最值得你花時間的。

## A 區：我標了訊號，請裁決

### A1 · US:AAPL · @jukan05 ⭐ 影響共識結論
- 我判：立場 **unclear** ／ 語氣 **negative**（信心 0.40）
- 依據：批評摺疊機外觀難看，屬產品評價而非對股票的判斷
- 引文：`First impressions of the iPhone Duo: Why is it so ugly?`
- 原文：First impressions of the iPhone Duo: Why is it so ugly? https://t.co/3VpCUciiOZ
- 連結：https://x.com/jukan05/status/2097822355141857590
- **裁決**: 

### A2 · US:AAPL · @octopusycc ⭐ 影響共識結論
- 我判：立場 **unclear** ／ 語氣 **negative**（信心 0.40）
- 依據：直播開場時提到蘋果股價跳水，屬盤中現象描述而非判斷
- 引文：`来看苹果跳水了`
- 原文：https://t.co/CarCi3HyIo ⏎ 来看苹果跳水了 ⏎  ⏎ [引用 @octopusycc]: 今天再播两场 ⏎ 晚点见  ⏎  ⏎ @heyibinance @yingbinance @binancezh https://t.co/OEUBd2HKLH
- 連結：https://x.com/octopusycc/status/2097738108708257810
- **裁決**: 

### A3 · US:AAPL · @ren_stocks ⭐ 影響共識結論
- 我判：立場 **unclear** ／ 語氣 **negative**（信心 0.40）
- 依據：用微軟 Surface Duo 反諷新摺疊機不新鮮，是產品揶揄不是股票判斷
- 引文：`The new IPhone Duo looks so awesome… Oh wait…`
- 原文：The new IPhone Duo looks so awesome… ⏎  ⏎ Oh wait… ⏎  ⏎ [引用 @surface]: The new Surface Duo. There’s a new way to get things done. Available today: https://t.co/c12L9wq24W #DoOneBetter https://t.co/byQCp7XAjm
- 連結：https://x.com/ren_stocks/status/2098022993859326374
- **裁決**: 

### A4 · US:META · @zephyr_z9 ⭐ 影響共識結論
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.40）
- 依據：只以驚訝回應該公司人才流失到 Anthropic 的消息，未表達方向
- 引文：`HUH`
- 原文：HUH ⏎  ⏎ [引用 @ArfurGrok]: ✅ Andrew Tulloch (@ajtulloch) has left Meta and joined Anthropic.
- 連結：https://x.com/zephyr_z9/status/2097874207967424648
- **裁決**: 

### A5 · US:AAPL · @michaelsikand ⭐ 影響共識結論
- 我判：立場 **bearish** ／ 語氣 **negative**（信心 0.45）
- 依據：承認市場對摺疊機反應冷淡、自己看多判斷錯誤
- 引文：`Market just faded the new iPhone Duo. I was wrong.`
- 原文：Market just faded the new iPhone Duo. ⏎  ⏎ I was wrong. ⏎  ⏎ Personally would've loved to have seen it better positioned as a productivity max device with keyboard compatibility. ⏎  ⏎ How many times have you been stuck with work/AI tasks on mobile that are tedious as hell? Shame. https://t.co/GR80jS…
- 連結：https://x.com/michaelsikand/status/2097752218355311048
- **裁決**: 

### A6 · US:GOOGL · @aleabitoreddit ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.55）
- 依據：同上，並總結 AI 相關股權資產將取得絕大部分增量所得
- 引文：`essentially all of the incremental GDP accrues to capital`
- 原文：Anthropic's Economic Scenario publication was a pretty interesting read: ⏎  ⏎ 1. Anthropic's "extreme" scenario has GDP growth reaching 15.4% in 2030 ⏎  ⏎ So around 7.3x current rates (~2.1% Y/Y), which is consistent with what Elon Musk is saying about outgrowing the national debt with AI.   ⏎  ⏎ 2.…
- 連結：https://x.com/aleabitoreddit/status/2097815176838017066
- **裁決**: 

### A7 · US:META · @aleabitoreddit ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.55）
- 依據：同上，被列為資本支出換取 2028 年後獲利的代表
- 引文：`when you look at $AMZN / $META / $GOOGL capex`
- 原文：Anthropic's Economic Scenario publication was a pretty interesting read: ⏎  ⏎ 1. Anthropic's "extreme" scenario has GDP growth reaching 15.4% in 2030 ⏎  ⏎ So around 7.3x current rates (~2.1% Y/Y), which is consistent with what Elon Musk is saying about outgrowing the national debt with AI.   ⏎  ⏎ 2.…
- 連結：https://x.com/aleabitoreddit/status/2097815176838017066
- **裁決**: 

### A8 · US:AAPL · @michaelsikand ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.60）
- 依據：稱自己稍早的看多判斷最終是對的，並提到當沖獲利
- 引文：`Nevermind I was right 🤣 Fun little 0 day.`
- 原文：Nevermind I was right 🤣 ⏎  ⏎ Fun little 0 day. https://t.co/pndxqVhMrp ⏎  ⏎ [引用 @michaelsikand]: I think the market could like $AAPL's new foldable phone launch today. ⏎  ⏎ Just think about it. ⏎  ⏎ - New CEO is here ⏎ - Biggest form change to iPhone ever ⏎ - Apple buyers who want a foldable phone t…
- 連結：https://x.com/michaelsikand/status/2097762394139427027
- **裁決**: 

### A9 · KRX:005930 · @zephyr_z9 ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.70）
- 依據：認為其基底晶片較佳且高頻寬記憶體產能擴張速度明顯較快
- 引文：`Samsung has a better base die and is also expanding HBM capacity much more rapidly`
- 原文：Not too sure if Hynix will retain the number 1 position in HBM ⏎ Samsung has a better base die and is also expanding HBM capacity much more rapidly ⏎  ⏎ [引用 @intelfabs]: HBM: keep &gt;40% revenue share next year.  ⏎ FY27 blended ASP now +48% y/y (was +35%).  ⏎ 8Hi mix seen at 55–60% as key customers…
- 連結：https://x.com/zephyr_z9/status/2098018599466111294
- **裁決**: 

### A10 · US:META · @zephyr_z9 ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.70）
- 依據：認為其在個人代理領域可比 OpenAI 更積極推進，因為伺服器處理器與記憶體採購量最大
- 引文：`Meta can probably move much more aggressively in the personal agent space compared to OpenAI`
- 原文：Meta can probably move much more aggressively in the personal agent space compared to OpenAI because they have been the most aggressive buyer of server CPUs since Q3 2025, and also the most aggressive memory buyer since Q2 2026 ⏎  ⏎ I don't think OpenAI has enough CPUs/DRAM to support this kind of r…
- 連結：https://x.com/zephyr_z9/status/2097881141114290467
- **裁決**: 

### A11 · US:SKHY · @zephyr_z9 ⭐ 影響共識結論
- 我判：立場 **bearish** ／ 語氣 **neutral**（信心 0.70）
- 依據：質疑其高頻寬記憶體龍頭地位能否保住，理由是三星基底晶片更好且擴產更快
- 引文：`Not too sure if Hynix will retain the number 1 position in HBM`
- 原文：Not too sure if Hynix will retain the number 1 position in HBM ⏎ Samsung has a better base die and is also expanding HBM capacity much more rapidly ⏎  ⏎ [引用 @intelfabs]: HBM: keep &gt;40% revenue share next year.  ⏎ FY27 blended ASP now +48% y/y (was +35%).  ⏎ 8Hi mix seen at 55–60% as key customers…
- 連結：https://x.com/zephyr_z9/status/2098018599466111294
- **裁決**: 

### A12 · US:AAPL · @michaelsikand ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.75）
- 依據：列出新執行長、史上最大機構變革與買家對價格不敏感等理由，預期市場會買單
- 引文：`I think the market could like $AAPL's new foldable phone launch today.`
- 原文：I think the market could like $AAPL's new foldable phone launch today. ⏎  ⏎ Just think about it. ⏎  ⏎ - New CEO is here ⏎ - Biggest form change to iPhone ever ⏎ - Apple buyers who want a foldable phone to do more serious work with AI etc. are price insensitive ⏎ - It sells like crazy https://t.co/hW…
- 連結：https://x.com/michaelsikand/status/2097736636704719296
- **裁決**: 

### A13 · KRX:005930 · @aleabitoreddit ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.80）
- 依據：同上，被列為受惠於記憶體漲價的廠商
- 引文：`So $SKHY, Samsung, $MU, should be happy to hear this`
- 原文：Wow, HBM reportedly drove up AI accelerator/card prices by 20-50% in China. ⏎  ⏎ So $SKHY, Samsung, $MU, should be happy to hear this: ⏎  ⏎ - Huawei has raised indicated pricing for the Ascend 950DT 20–50% above quotes from just 2 months ago ⏎  ⏎ - Cambricon's upcoming 690 is reportedly +20–30% ⏎  ⏎…
- 連結：https://x.com/aleabitoreddit/status/2097937708178186303
- **裁決**: 

### A14 · US:SKHY · @aleabitoreddit ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.80）
- 依據：高頻寬記憶體推升中國 AI 加速器售價 20 到 50%，作者明說記憶體廠應該樂見，且自陳做多記憶體
- 引文：`So $SKHY, Samsung, $MU, should be happy to hear this`
- 原文：Wow, HBM reportedly drove up AI accelerator/card prices by 20-50% in China. ⏎  ⏎ So $SKHY, Samsung, $MU, should be happy to hear this: ⏎  ⏎ - Huawei has raised indicated pricing for the Ascend 950DT 20–50% above quotes from just 2 months ago ⏎  ⏎ - Cambricon's upcoming 690 is reportedly +20–30% ⏎  ⏎…
- 連結：https://x.com/aleabitoreddit/status/2097937708178186303
- **裁決**: 

### A15 · US:META · @michaelsikand ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.85）
- 依據：自陳是旗艦基金最大持股、加碼後已漲逾 18%，並反問誰能看空
- 引文：`$META is the largest position in my Flagship Fund up over 18% since I added`
- 原文：$META is the largest position in my Flagship Fund up over 18% since I added after diversifying after it being all in memory. ⏎  ⏎ With this lawsuit done, Muse personal agents, and a boatload of compute to use or sell externally... ⏎  ⏎ Can you bet against Zuck? https://t.co/veZPiDifQN
- 連結：https://x.com/michaelsikand/status/2097756968962462036
- **裁決**: 

### A16 · US:GOOGL · @ren_stocks ⭐ 影響共識結論
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.90）
- 依據：明說是最喜愛的公司之一，若只能選一檔持有十年就選它
- 引文：`If I had to pick one stock to hold for the next ten years, for me it would be this one.`
- 原文：$GOOGL It's perhaps one of my favourite companies of all time. If I had to pick one stock to hold for the next ten years, for me it would be this one. ⏎  ⏎ But don't invest on TA alone. ⏎  ⏎ Understand why it's trading at the 200-day EMA. Understand the product roadmap. Understand the company.  ⏎  ⏎…
- 連結：https://x.com/ren_stocks/status/2097737010635235835
- **裁決**: 

### A17 · TSE:5332 · @aleabitoreddit
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.35）
- 依據：用免治馬桶換發現金的玩笑話，不是對該股的判斷
- 引文：`TOTO（5332.T）のトイレにアップグレードしたほうが、支持率はもっと上がるんじゃないか`
- 原文：共和党が議会で多数派を維持できたら、トランプが成人1人につき5,000ドルを配ると約束している理由が、正直よく分からない。（総額約1.35兆ドル） ⏎  ⏎ それより、アメリカ中のトイレを、日本にあるような便座が温かくなるTOTO（5332.T）のトイレにアップグレードしたほうが、支持率はもっと上がるんじゃないかと思う。 ⏎  ⏎ 計算してみた： ⏎  ⏎ 3億3,500万台のトイレをTOTO UltraMax II + S7Aに交換すると、約9,900億ドル。 ⏎ 設置費用まで含めると、総額は約1.3兆ドル。 ⏎  ⏎ 僕の案のほうがかなり安い。 ⏎  ⏎ [引用 @jijicom]: 【速…
- 連結：https://x.com/aleabitoreddit/status/2098031064002535908
- **裁決**: 

### A18 · US:MRVL · @zephyr_z9
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.35）
- 依據：補充載板供應商名單作為引用內容的延伸，未對該股表態
- 引文：`The list - Ibiden, Unimicron, Shinko, Toppan, Kyocera`
- 原文：The list - Ibiden, Unimicron, Shinko, Toppan, Kyocera,  SEMCO, Daeduck, Korea Circuit, LG Innotek, ZDT, Nan Ya PCB, Kinsus, Shennan, Fastprint ⏎  ⏎ [引用 @BenBajarin]: Also interesting from Matt Murphy $MRVL was the commentary on them ramping the supply chain to bet on their scale as well. And this po…
- 連結：https://x.com/zephyr_z9/status/2097841940318580977
- **裁決**: 

### A19 · US:NVDA · @zephyr_z9
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.35）
- 依據：認為對方是在對其潑冷水，作者未提出自己的方向判斷
- 引文：`To throw shade at Nvidia??`
- 原文：Lol ⏎ Why is Hock making stuff up?? ⏎ To throw shade at Nvidia?? ⏎ Open model developers have spent around $10B-$15B (optimistically) ⏎  ⏎ [引用 @techfund1]: Broadcom CEO Hock Tan breaks down AI economics: ⏎  ⏎ Open-weight models burn $100B compute to make $30B in revenue.  ⏎  ⏎ Frontier models spend …
- 連結：https://x.com/zephyr_z9/status/2097674402217271419
- **裁決**: 

### A20 · US:MU · @michaelsikand
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.40）
- 依據：引為他人 2024 年十倍報酬的舊案例，非當下對該股的判斷
- 引文：`if you missed his 10x $MU call in 2024`
- 原文：Always wondered why $U was one of @GavinSBaker's biggest positions.  ⏎  ⏎ Then after seeing GPT 6 Astra and how it integrates with $U to build virtual worlds, it all makes sense. ⏎  ⏎ AI + gaming feels like a name/theme that's still very early if you missed his 10x $MU call in 2024. https://t.co/hzv…
- 連結：https://x.com/michaelsikand/status/2097699543773319339
- **裁決**: 

### A21 · US:NVDA · @ren_stocks
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.40）
- 依據：只以大笑回應 Burry 出清部位的新聞，未表達自己的方向
- 引文：`HAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHA`
- 原文：HAHAHAHAHAHAHAHAHAHAHAHAHAHAHAHA ⏎  ⏎ [引用 @Kalshi]: JUST IN: Michael Burry "sells" entire Nvidia position
- 連結：https://x.com/ren_stocks/status/2097812079877017714
- **裁決**: 

### A22 · US:AVGO · @zephyr_z9
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.40）
- 依據：質疑其執行長對 AI 經濟數字的說法造假，但針對的是言論可信度而非股價
- 引文：`Why is Hock making stuff up??`
- 原文：Lol ⏎ Why is Hock making stuff up?? ⏎ To throw shade at Nvidia?? ⏎ Open model developers have spent around $10B-$15B (optimistically) ⏎  ⏎ [引用 @techfund1]: Broadcom CEO Hock Tan breaks down AI economics: ⏎  ⏎ Open-weight models burn $100B compute to make $30B in revenue.  ⏎  ⏎ Frontier models spend …
- 連結：https://x.com/zephyr_z9/status/2097674402217271419
- **裁決**: 

### A23 · US:NVDA · @jukan05
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.45）
- 依據：轉述其高價鎖定測試介面產能的供應鏈觀察，未對股價表態
- 引文：`NVIDIA has been paying hefty premiums to lock up probe card and test socket capacity`
- 原文：Taiwanese media reported that NVIDIA has been paying hefty premiums to lock up probe card and test socket capacity from test interface suppliers. ⏎  ⏎ https://t.co/GzgGhAnfVo
- 連結：https://x.com/jukan05/status/2097850670716223529
- **裁決**: 

### A24 · US:TSM · @jukan05
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.45）
- 依據：純數據播報月營收，作者未加上自己的判斷
- 引文：`TSMC August revenue: NT$514,806mn (+10.1% MoM, +53.3% YoY)`
- 原文：TSMC August revenue: NT$514,806mn ⏎ (+10.1% MoM, +53.3% YoY) ⏎  ⏎ $TSM https://t.co/UJtgcH2F2T
- 連結：https://x.com/jukan05/status/2097921040144093335
- **裁決**: 

### A25 · US:NVDA · @zephyr_z9
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.45）
- 依據：轉述機櫃功率藍圖延後、規格下修的產業訊息，未直接對股價表態
- 引文：`Khyber is delayed/canceled, so we won't see 600kW racks in 2027`
- 原文：Khyber is delayed/canceled, so we won't see 600kW racks in 2027 ⏎ It will hit 230-250kW https://t.co/8fD3POlnlg
- 連結：https://x.com/zephyr_z9/status/2097864880158326944
- **裁決**: 

### A26 · SSE:688256 · @aleabitoreddit
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.50）
- 依據：只被引用為漲價的例證，作者未對該股表態
- 引文：`Cambricon's upcoming 690 is reportedly +20–30%`
- 原文：Wow, HBM reportedly drove up AI accelerator/card prices by 20-50% in China. ⏎  ⏎ So $SKHY, Samsung, $MU, should be happy to hear this: ⏎  ⏎ - Huawei has raised indicated pricing for the Ascend 950DT 20–50% above quotes from just 2 months ago ⏎  ⏎ - Cambricon's upcoming 690 is reportedly +20–30% ⏎  ⏎…
- 連結：https://x.com/aleabitoreddit/status/2097937708178186303
- **裁決**: 

### A27 · SSE:688256 · @jukan05
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.50）
- 依據：轉述路透報導該公司次世代晶片漲價 20 到 30%，未對股價表態
- 引文：`Cambricon has also raised the price of its next-generation chip`
- 原文：CHINESE AI CHIPMAKERS ARE RAISING PRICES DUE TO HBM SHORTAGES — REUTERS ⏎  ⏎ Huawei has raised the price of its Ascend 950DT to 250,000 yuan, a 20%–50% increase from the quotes it gave customers two months ago. ⏎  ⏎ Cambricon has also raised the price of its next-generation chip, tentatively called …
- 連結：https://x.com/jukan05/status/2097917661804159158
- **裁決**: 

### A28 · US:RKLB · @michaelsikand
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.50）
- 依據：被舉為過去的代理標的案例，用來說明操作方法而非現在看多
- 引文：`It was trading the proxies like $RKLB that rallied in the weeks leading up to the big day`
- 原文：The biggest gains on the $SPCX IPO weren't on $SPCX. ⏎  ⏎ It was trading the proxies like $RKLB that rallied in the weeks leading up to the big day, and selling them into the hype. ⏎  ⏎ So me and the team @AsymmetricBets_ just came up with our best trade ideas around the Anthropic S-1. https://t.co/…
- 連結：https://x.com/michaelsikand/status/2097779182591995996
- **裁決**: 

### A29 · US:SPCX · @michaelsikand
- 我判：立場 **unclear** ／ 語氣 **neutral**（信心 0.50）
- 依據：回顧該檔上市時的交易經驗，未對現在的股價表態
- 引文：`The biggest gains on the $SPCX IPO weren't on $SPCX.`
- 原文：The biggest gains on the $SPCX IPO weren't on $SPCX. ⏎  ⏎ It was trading the proxies like $RKLB that rallied in the weeks leading up to the big day, and selling them into the hype. ⏎  ⏎ So me and the team @AsymmetricBets_ just came up with our best trade ideas around the Anthropic S-1. https://t.co/…
- 連結：https://x.com/michaelsikand/status/2097779182591995996
- **裁決**: 

### A30 · US:NVDA · @zephyr_z9
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.50）
- 依據：對其高價鎖定測試產能的做法表示佩服，語氣正面看待其供應鏈掌控力
- 引文：`LMAO Jensen is a demon`
- 原文：LMAO ⏎ Jensen is a demon ⏎  ⏎ [引用 @jukan05]: Taiwanese media reported that NVIDIA has been paying hefty premiums to lock up probe card and test socket capacity from test interface suppliers. ⏎  ⏎ https://t.co/GzgGhAnfVo
- 連結：https://x.com/zephyr_z9/status/2097850972446056584
- **裁決**: 

### A31 · US:AMZN · @aleabitoreddit
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.55）
- 依據：以 2028 年後獲利大幅成長解讀當前資本支出造成的自由現金流壓力，屬長線偏多
- 引文：`short term FCF headwinds (but massive projected profitability post 2028)`
- 原文：Anthropic's Economic Scenario publication was a pretty interesting read: ⏎  ⏎ 1. Anthropic's "extreme" scenario has GDP growth reaching 15.4% in 2030 ⏎  ⏎ So around 7.3x current rates (~2.1% Y/Y), which is consistent with what Elon Musk is saying about outgrowing the national debt with AI.   ⏎  ⏎ 2.…
- 連結：https://x.com/aleabitoreddit/status/2097815176838017066
- **裁決**: 

### A32 · KRX:009150 · @KawzInvests
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.60）
- 依據：同上，被列為正在調漲售價的主要供應商之一
- 引文：`Murata, Samsung Electro-Mechanics, and Taiyo Yuden all raising prices.`
- 原文：MLCC spot prices are up 3-5x on scarce AI-server specs since April. Some individual models up 8-10x. ⏎  ⏎ Murata, Samsung Electro-Mechanics, and Taiyo Yuden all raising prices. ⏎  ⏎ Nearly every major MLCC manufacturer trades in Japan, South Korea, Taiwan, or China. @roundhill  launched $CCML today …
- 連結：https://x.com/KawzInvests/status/2097692213014606169
- **裁決**: 

### A33 · TSE:6976 · @KawzInvests
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.60）
- 依據：同上，被列為正在調漲售價的主要供應商之一
- 引文：`Murata, Samsung Electro-Mechanics, and Taiyo Yuden all raising prices.`
- 原文：MLCC spot prices are up 3-5x on scarce AI-server specs since April. Some individual models up 8-10x. ⏎  ⏎ Murata, Samsung Electro-Mechanics, and Taiyo Yuden all raising prices. ⏎  ⏎ Nearly every major MLCC manufacturer trades in Japan, South Korea, Taiwan, or China. @roundhill  launched $CCML today …
- 連結：https://x.com/KawzInvests/status/2097692213014606169
- **裁決**: 

### A34 · TSE:6981 · @KawzInvests
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.60）
- 依據：點名積層陶瓷電容現貨價因 AI 伺服器規格短缺漲 3 到 5 倍，且該公司正在漲價
- 引文：`MLCC spot prices are up 3-5x on scarce AI-server specs since April`
- 原文：MLCC spot prices are up 3-5x on scarce AI-server specs since April. Some individual models up 8-10x. ⏎  ⏎ Murata, Samsung Electro-Mechanics, and Taiyo Yuden all raising prices. ⏎  ⏎ Nearly every major MLCC manufacturer trades in Japan, South Korea, Taiwan, or China. @roundhill  launched $CCML today …
- 連結：https://x.com/KawzInvests/status/2097692213014606169
- **裁決**: 

### A35 · US:TSM · @jukan05
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.60）
- 依據：對 1.4 奈米量產比原訂計畫提早一年表達驚訝與正面看待
- 引文：`Mass production of 1.4nm by the end of 2027??`
- 原文：Mass production of 1.4nm by the end of 2027?? ⏎  ⏎ [引用 @dnystedt]: TSMC may be in 1.4nm mass production by end-2027, a year earlier than planned, media report, adding the chip giant could begin commissioning equipment by April. Construction on its 1.4nm fab cluster near Taichung, central Taiwan, is …
- 連結：https://x.com/jukan05/status/2097855233921892542
- **裁決**: 

### A36 · US:NVDA · @zephyr_z9
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.60）
- 依據：認為 Rubin 平台每美元運算與記憶體頻寬效益遠勝華為，即使黑市價高四倍仍會主導訓練需求
- 引文：`It will dominate training even if the black market price is 4x higher`
- 原文：This price will ensure that black market/smuggling demand for Rubin is strong in China ⏎ Rubin offers 8x better FLOPS/$ and 2.2x better Mem BW/$ ⏎ It will dominate training even if the black market price is 4x higher ($320k vs $80k) ⏎  ⏎ [引用 @zephyr_z9]: "Huawei has raised the price of its Ascend 95…
- 連結：https://x.com/zephyr_z9/status/2097920303875911741
- **裁決**: 

### A37 · US:U · @michaelsikand
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.70）
- 依據：看到 GPT 6 Astra 與該公司整合建構虛擬世界後認同其邏輯，並稱 AI 加遊戲這個主題還很早期
- 引文：`AI + gaming feels like a name/theme that's still very early`
- 原文：Always wondered why $U was one of @GavinSBaker's biggest positions.  ⏎  ⏎ Then after seeing GPT 6 Astra and how it integrates with $U to build virtual worlds, it all makes sense. ⏎  ⏎ AI + gaming feels like a name/theme that's still very early if you missed his 10x $MU call in 2024. https://t.co/hzv…
- 連結：https://x.com/michaelsikand/status/2097699543773319339
- **裁決**: 

### A38 · US:MU · @aleabitoreddit
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.80）
- 依據：同上，作者明確表態自己是記憶體多方
- 引文：`As someone who is long memory, I'm happy about memory causing this much inflation.`
- 原文：Wow, HBM reportedly drove up AI accelerator/card prices by 20-50% in China. ⏎  ⏎ So $SKHY, Samsung, $MU, should be happy to hear this: ⏎  ⏎ - Huawei has raised indicated pricing for the Ascend 950DT 20–50% above quotes from just 2 months ago ⏎  ⏎ - Cambricon's upcoming 690 is reportedly +20–30% ⏎  ⏎…
- 連結：https://x.com/aleabitoreddit/status/2097937708178186303
- **裁決**: 

### A39 · US:AAOI · @ren_stocks
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.90）
- 依據：列在 Bullish for 清單，理由是可插拔光模組仍有成長空間
- 引文：`$AAOI - pluggable runway`
- 原文：Citi's TMT note has Lightmatter calling lasers and optical fiber "the next HBM." ⏎  ⏎ NPO 2027. CPO 2028-29. ⏎  ⏎ Pluggable, NPO, CPO all burn light, and all three need the same lasers and the same InP underneath. ⏎  ⏎ Bullish for: ⏎  ⏎ $AEHR - testing, the actual gate on CPO ⏎ $AXTI - InP substrate…
- 連結：https://x.com/ren_stocks/status/2097820413900276043
- **裁決**: 

### A40 · US:AEHR · @ren_stocks
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.90）
- 依據：直接列在 Bullish for 清單，理由是測試是共同封裝光學的實際瓶頸
- 引文：`$AEHR - testing, the actual gate on CPO`
- 原文：Citi's TMT note has Lightmatter calling lasers and optical fiber "the next HBM." ⏎  ⏎ NPO 2027. CPO 2028-29. ⏎  ⏎ Pluggable, NPO, CPO all burn light, and all three need the same lasers and the same InP underneath. ⏎  ⏎ Bullish for: ⏎  ⏎ $AEHR - testing, the actual gate on CPO ⏎ $AXTI - InP substrate…
- 連結：https://x.com/ren_stocks/status/2097820413900276043
- **裁決**: 

### A41 · US:AXTI · @ren_stocks
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.90）
- 依據：列在 Bullish for 清單，理由是磷化銦基板需求
- 引文：`$AXTI - InP substrate`
- 原文：Citi's TMT note has Lightmatter calling lasers and optical fiber "the next HBM." ⏎  ⏎ NPO 2027. CPO 2028-29. ⏎  ⏎ Pluggable, NPO, CPO all burn light, and all three need the same lasers and the same InP underneath. ⏎  ⏎ Bullish for: ⏎  ⏎ $AEHR - testing, the actual gate on CPO ⏎ $AXTI - InP substrate…
- 連結：https://x.com/ren_stocks/status/2097820413900276043
- **裁決**: 

### A42 · US:COHR · @ren_stocks
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.90）
- 依據：列在 Bullish for 清單，理由是雷射需求
- 引文：`$COHR - lasers`
- 原文：Citi's TMT note has Lightmatter calling lasers and optical fiber "the next HBM." ⏎  ⏎ NPO 2027. CPO 2028-29. ⏎  ⏎ Pluggable, NPO, CPO all burn light, and all three need the same lasers and the same InP underneath. ⏎  ⏎ Bullish for: ⏎  ⏎ $AEHR - testing, the actual gate on CPO ⏎ $AXTI - InP substrate…
- 連結：https://x.com/ren_stocks/status/2097820413900276043
- **裁決**: 

### A43 · US:FN · @ren_stocks
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.90）
- 依據：列在 Bullish for 清單，理由是光引擎組裝
- 引文：`$FN - engine assembly`
- 原文：Citi's TMT note has Lightmatter calling lasers and optical fiber "the next HBM." ⏎  ⏎ NPO 2027. CPO 2028-29. ⏎  ⏎ Pluggable, NPO, CPO all burn light, and all three need the same lasers and the same InP underneath. ⏎  ⏎ Bullish for: ⏎  ⏎ $AEHR - testing, the actual gate on CPO ⏎ $AXTI - InP substrate…
- 連結：https://x.com/ren_stocks/status/2097820413900276043
- **裁決**: 

### A44 · US:LITE · @ren_stocks
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.90）
- 依據：列在 Bullish for 清單，理由是雷射需求
- 引文：`$LITE - lasers`
- 原文：Citi's TMT note has Lightmatter calling lasers and optical fiber "the next HBM." ⏎  ⏎ NPO 2027. CPO 2028-29. ⏎  ⏎ Pluggable, NPO, CPO all burn light, and all three need the same lasers and the same InP underneath. ⏎  ⏎ Bullish for: ⏎  ⏎ $AEHR - testing, the actual gate on CPO ⏎ $AXTI - InP substrate…
- 連結：https://x.com/ren_stocks/status/2097820413900276043
- **裁決**: 

### A45 · US:MRVL · @ren_stocks
- 我判：立場 **bullish** ／ 語氣 **neutral**（信心 0.90）
- 依據：列在 Bullish for 清單，理由是訊號仍需傳輸
- 引文：`$MRVL - the signal still has to travel`
- 原文：Citi's TMT note has Lightmatter calling lasers and optical fiber "the next HBM." ⏎  ⏎ NPO 2027. CPO 2028-29. ⏎  ⏎ Pluggable, NPO, CPO all burn light, and all three need the same lasers and the same InP underneath. ⏎  ⏎ Bullish for: ⏎  ⏎ $AEHR - testing, the actual gate on CPO ⏎ $AXTI - InP substrate…
- 連結：https://x.com/ren_stocks/status/2097820413900276043
- **裁決**: 

---

## B 區：我判定這幾篇沒有個股訊號，請抽查

### B1 · @jukan05
- 原文：What does this mean for the mathematicians who devoted their entire lives to solving these problems? They won't be remembered. Only the AI will be. Or perhaps, from here on, the very notion of a "great unsolved problem" becomes meaningless. If something can be solved with a few million dollars' worth of tokens, can you still call it an unsolved problem? From that point on, it is no longer an achie…
- 連結：https://x.com/jukan05/status/2097978921090527601
- **裁決**: 

### B2 · @zephyr_z9
- 原文：DAYUM https://t.co/QJwXoaGwgT ⏎  ⏎ [引用 @zephyr_z9]: Fucking crazy dawg ⏎ Another 4x KV cache size per token reduction https://t.co/tkzZ9KfIkL
- 連結：https://x.com/zephyr_z9/status/2097928434928517532
- **裁決**: 

### B3 · @octopusycc
- 原文：今天再播两场 ⏎ 晚点见  ⏎  ⏎ @heyibinance @yingbinance @binancezh https://t.co/OEUBd2HKLH
- 連結：https://x.com/octopusycc/status/2097664555036119090
- **裁決**: 

### B4 · @zephyr_z9
- 原文：They threw in everything this time https://t.co/avEtHSEU1X
- 連結：https://x.com/zephyr_z9/status/2097932776721019014
- **裁決**: 

### B5 · @michaelsikand
- 原文：Follow along this portfolio trade by trade ⏎  ⏎ https://t.co/hISzOVfsHz
- 連結：https://x.com/michaelsikand/status/2097757379236630677
- **裁決**: 

### B6 · @zephyr_z9
- 原文：Interesting ⏎  ⏎ [引用 @tphuang]: ByteDance alone is building 5-6 GW AIDC in Ulanqab. This increases AIDC capacity there by 40 to 50% ⏎  ⏎ Cost 800-960B RMB, so 160B RMB per GW or $22B. ⏎ BD is battling Ali &amp; Tencent for consumer app &amp; work place app. Its oversea capex is fraction of what it invests in China. https://t.co/mT7ub6lmIT
- 連結：https://x.com/zephyr_z9/status/2097858736832520461
- **裁決**: 

### B7 · @zephyr_z9
- 原文：Deepseek has compressed KV cache size per token by 54x in the last 9 months https://t.co/TFoQschmle
- 連結：https://x.com/zephyr_z9/status/2097943984425545755
- **裁決**: 

### B8 · @zephyr_z9
- 原文：The whale strikes back!!! https://t.co/9ZVOA35EdH ⏎  ⏎ [引用 @deepseek_ai]: 🚀 Introducing DeepSeek-V4.1-Flash: smarter, faster, more efficient. ⏎  ⏎ 🔹 Introducing the smallest model in our new architecture family, with native visual understanding. ⏎ 🔹 Designed for greater capability, faster inference, higher throughput, and scaling to larger models. ⏎  ⏎ 1/6
- 連結：https://x.com/zephyr_z9/status/2097931320232235289
- **裁決**: 

### B9 · @jukan05
- 原文：WTF?? https://t.co/BP50PbVBC3 ⏎  ⏎ [引用 @sheriyuo]: https://t.co/8WhlMSIJUS ⏎  ⏎ DeepSeek V4.1 Flash 为 552B 参数的 MoE 模型，采用了全新的 Causal-Encoder-Decoder 结构，输入和输出不对称，输入激活只有 8B，输出激活 16B，成本显著低于已知的同尺寸模型。同时，V4.1 Flash 还采用了新的预训练方式、经过了更大规模的强化学习后训练，在基准测试中，成功超越了包括 DeepSeek V4 Pro 在内的一众旗舰模型的智能水平。
- 連結：https://x.com/jukan05/status/2097927926364967322
- **裁決**: 

### B10 · @zephyr_z9
- 原文：👀👀👀👀👀👀 https://t.co/pxS1FDnBM2 ⏎  ⏎ [引用 @nopainkiller]: compiled open source links from chenggang: ⏎ https://t.co/xXX2Te51kS ⏎ https://t.co/j5HLigHNbx ⏎ https://t.co/Js0tRBgC9M ⏎ https://t.co/CvHFwmwNLq ⏎ Big whale OSS day
- 連結：https://x.com/zephyr_z9/status/2097939622789783864
- **裁決**: 

### B11 · @jukan05
- 原文：https://t.co/9kPwBqNlkB
- 連結：https://x.com/jukan05/status/2097917663855182081
- **裁決**: 

### B12 · @aleabitoreddit
- 原文：If you hid the ticker, you would think this was an AI bottleneck name. https://t.co/6rR1BWYRb9
- 連結：https://x.com/aleabitoreddit/status/2097743984596861401
- **裁決**: 

### B13 · @zephyr_z9
- 原文：Did a crackdown happen in August 🤔🤔 https://t.co/23XDHgDuwf ⏎  ⏎ [引用 @jukan05]: CHINESE AI CHIPMAKERS ARE RAISING PRICES DUE TO HBM SHORTAGES — REUTERS ⏎  ⏎ Huawei has raised the price of its Ascend 950DT to 250,000 yuan, a 20%–50% increase from the quotes it gave customers two months ago. ⏎  ⏎ Cambricon has also raised the price of its next-generation chip, tentatively called the 690, by 20%–30% …
- 連結：https://x.com/zephyr_z9/status/2097923207831671240
- **裁決**: 

### B14 · @zephyr_z9
- 原文：Sol getting commoditized like this was not on my bingo card ⏎ v4.1 Pro is also coming, anon https://t.co/KiNbqgc1Ga ⏎  ⏎ [引用 @zephyr_z9]: HOLY FUCKING SHIT ⏎ New arch ⏎ LFG!!!! ⏎ @teortaxesTex
- 連結：https://x.com/zephyr_z9/status/2097929250217361760
- **裁決**: 

### B15 · @michaelsikand
- 原文：The Mag 7 are doing everything to make retail investors money ⏎ while short sighted institutions cry about no dividends.  ⏎  ⏎ They're going all in on asymmetric bets. This is the way.
- 連結：https://x.com/michaelsikand/status/2097819807949496561
- **裁決**: 
