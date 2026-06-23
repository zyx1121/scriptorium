# source-first — research grounded in real source

研究 / 回答 / 文件問題前先找一手來源。training data 不算來源、語感不算來源、印象不算來源。每條 claim 必須能指回實體出處。

## Trigger 信號

- "how does X work" / "X 是什麼" / 概念釐清
- 整理 stack / write-up / blog post / 簡報
- 跨 library / framework / spec 的整合問題
- 「應該是 ___ 吧」這種半確定的回答開頭
- agent 拿訓練資料當權威來源（已知會 stale）

## Procedure

### Step 1 — 找一手來源

依優先順序：

1. **codebase 本身**（grep / read 真實 code）
2. **官方文件**（官網 / docs.X.com / API reference）
3. **RFC / spec / paper**（協定 / 標準 / 學術出處）
4. **官方 blog / changelog / release note**
5. **maintainer 公開發言**（GitHub issue / PR comment / blog）

二手來源（StackOverflow / 部落格 / AI 生成內容）只當提示，引用前**必須交叉驗證到一手**。

### Step 2 — 每條 claim 標來源

寫出來的每一條判斷後面附 `[SOURCE: ...]`：

- code 來源：`[SOURCE: src/foo.ts:42]` 或 `[SOURCE: gh:org/repo:path/file.ts#L42]`
- docs：`[SOURCE: https://docs.example.com/api/v2/foo]`
- spec：`[SOURCE: RFC 7231 §6.5]`
- 自己跑的實驗：`[SOURCE: 跑了 X 命令，輸出 Y]`

claim 沒有來源 = **明確標 uncertainty**：`[UNVERIFIED: based on prior knowledge, not checked]`。藏起來不寫等於騙人。

### Step 3 — 跨來源交叉檢查

如果一手來源跟二手記憶不一致 → **以一手為準**，更新自己的理解。

如果兩個一手來源衝突（少見但會發生：spec 跟 implementation 不一致）→ 標出衝突，明確說明你選擇相信哪一個 + 為什麼。

### Step 4 — 寫下來時保留 source path

最終輸出（blog / 簡報 / PR description / memo）裡：

- 重要 claim 帶 inline link 或 footnote
- 不重要的細節不一定要 link，但你自己腦袋裡要知道來源
- 「我猜」「我覺得」明確標 — 不要用權威語氣藏不確定性

## Anti-pattern

- 「我記得 React 18 後 X 變 Y」— training data，未驗，可能錯。grep 或 fetch docs 確認再寫
- 引 StackOverflow 答案但沒看官方文件 — SO 答案常 outdated，先過官方
- 把 LLM 生的 sample code 當權威 — 沒跑過 / 沒讀過原始碼，不要直接搬
- 寫 blog 時混 fact + 個人意見不區分 — reader 看不出哪些是 verified

## Marker

`[SOURCE: <reference>]`（every verified claim）
`[UNVERIFIED: <one-line caveat>]`（when no source available）
`[SOURCE-conflict: A says X, B says Y, choosing X because ___]`

## 失敗時切換

- 找不到 primary source（feature 太新 / 太小眾 / proprietary） → 標 `[UNVERIFIED]` + 明確說「以目前可得資料」，不要硬推結論
- 一手來源讀完後仍有歧義 → 切 **cunningham**，寫最小複現自己跑跑看
- 一手來源跟自己印象差太多 → 把舊印象 unlearn，重寫 memory 對應條目
