# cunningham — minimal reproducer / wrong version for critique

卡死 > 30 分鐘的時候，停止當前路線。兩條解法：把問題縮到最小（minimal repro），或寫一個故意錯的版本求批評（Cunningham's Law）。

Cunningham's Law：「The best way to get the right answer on the internet is not to ask a question; it's to post the wrong answer.」人糾正錯誤答案比回答問題快得多。

## Trigger 信號

- 同一問題卡 30 分鐘以上沒進展
- rca 5-Why 走到「我不知道」
- diagnosis 寫不出證據
- 試了 3 種以上方法都不行
- 開始有「我不知道我不知道什麼」的感覺
- 想 google 但不知道該 google 什麼關鍵字

## Procedure A — Minimal Reproducer

### Step 1 — 開新檔案 / 新 repo

不要在原 codebase 改 — 整個環境太多干擾。開：

- 新 `.py` / `.ts` / `.go` 檔
- 新 sandbox（[vercel:vercel-sandbox] 或 docker container）
- 新 git branch / 新 worktree
- 新 minimal project（`npm init` / `cargo new`）

### Step 2 — 從現象往內 strip

把問題從原 codebase 抽出來，剝到最小能復現：

1. 抽出失敗的核心邏輯（10-30 行）
2. mock 掉所有不相關依賴
3. 跑跑看 — 還會壞嗎？
4. 還壞 → 繼續 strip；不壞 → 上一步 strip 掉的就是 confounding factor

### Step 3a — 還壞到底

如果 strip 到 < 30 行還壞 — **這就是你問題的本質**。這時候：

- 容易 google：「python asyncio CancelledError in this context」短 code 比長 stack trace 好搜
- 容易發 issue 給 lib maintainer
- 容易理解（10-30 行你的腦袋能裝完）

### Step 3b — strip 後不壞

那原 codebase 裡有 confounding factor。**把上一個移除的步驟加回來** — 那個就是真兇。回 rca 查那個 factor 為什麼會搞壞。

## Procedure B — Cunningham's Law

當 minimal repro 也卡，或問題在概念層不在 code 層：

### Step 1 — 寫一個故意錯的版本

寫一段 code / 一個架構 / 一個 explanation，**故意錯一個地方**（但不要錯太離譜，要看起來像認真的）。

例如：
- 不知道某個 API 該怎麼用 → 寫一段「應該這樣用吧」的 code，加 comment "I think this is right"
- 不知道某個概念 → 寫一段「我的理解是 ...」的描述

### Step 2 — 貼到適當地方求批評

- GitHub issue / discussion
- Stack Overflow（記得包 minimal repro）
- 同事 / mentor / 技術群
- Reddit / Discord 相關 channel
- 自己問 Claude/GPT 但**特別指示「請批評這段，找出錯誤」**

### Step 3 — 收割糾正

人很愛糾正錯誤。會出現比你直接問還多的細節。

收到糾正後**驗證**（回 source-first），不要盲信。

## 規則

- 卡 < 30 分鐘不要跑 cunningham，繼續硬幹；卡 > 30 分鐘還沒進展才用
- minimal repro 是工程動作，wrong version 是社交工程動作 — 各自場合
- 開新 sandbox 比在原 codebase 改安全，原 codebase 留著 git stash 等等回來

## Anti-pattern

- 在原 codebase 直接砍東西當「minimal repro」 — 沒砍乾淨還是有干擾
- 寫了 wrong version 但寫得太離譜 — 沒人想糾正，被當 troll
- 寫了 wrong version 但藏起來 — 沒人看到等於沒寫
- minimal repro 跑得出來就放著不深究 — 這時候才是真正進到 rca 階段

## Marker

`[CUNNINGHAM: minimal-repro | wrong-version]`
`[CUNNINGHAM-strip: <step>]`（每砍一步寫一個）
`[CUNNINGHAM-found: <confounding factor>]`（找到的時候）

## 失敗時切換

- 連 minimal repro 都寫不出（問題定義都模糊） → 停手，把當前理解寫下來放著，下一輪頭腦清楚再回來
- wrong version 貼出去沒人回 → 太離譜或太冷門。重寫一個更接近真實的版本
- minimal repro 復現後查到根因 → 回 **rca** 補完 5-Why 並泛化同類
