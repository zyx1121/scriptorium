# backwards — Working Backwards from outcome

從「做完之後 user 看到什麼」反推要做哪些事。防止從技術棧往上堆，做完一堆東西但解錯問題。

借自 Amazon Working Backwards：先寫 press release / FAQ / mock UI，再反推實作。

## Trigger 信號

- 新 feature 但 spec 模糊
- "build something that helps users do X"
- "我們應該加個 ___ 功能"
- 拿到的需求是「目標」不是「規格」
- 多種實作路徑都可能滿足需求

## Procedure

### Step 1 — 寫「完成後 user 看到什麼」

選一種 outcome 格式，**先寫完成後**才能反推前面要做什麼：

- **假 PR description**：「This PR adds X. Users can now ___. Before this PR they had to ___.」
- **假 release note**：「v1.5.0 — the one where ___」
- **假 user flow**：「User opens 頁面 → 看到 X → 點 Y → 結果 Z」
- **假截圖描述**：「右上角會有 X 按鈕，點開彈出 Y panel，顯示 Z 資料」

寫的時候**從 user perspective**，不寫技術細節（不寫 endpoint、不寫 schema、不寫 lib 名）。

### Step 2 — 把 outcome 拆成「user 看到的元素」

例如假 release note 提到「token usage panel」，就拆：

- panel 在哪（哪個頁面、哪個位置）
- panel 顯示什麼（資料欄位）
- panel 怎麼更新（即時 / 重新整理 / WebSocket）
- 資料從哪來（哪個 API endpoint）
- 資料怎麼算（aggregation 邏輯）

### Step 3 — 反向排序成 work plan

從最後要做的元素開始往前：UI 顯示 ← API 回應 ← aggregation 邏輯 ← 資料儲存。

實作順序通常是反過來：**先做最底層的，最後做 UI**。但思考順序要從最頂層的 outcome 開始。

### Step 4 — 每個 work item 連結回 outcome

每個工作必須答得出「為什麼要做這個 — 因為 outcome 的哪一塊」。答不出來表示這個工作可能不需要。

## Anti-pattern

- 從技術棧開始：「先建 schema → 再做 API → 再做 UI」— 沒有 outcome 對齊，做完發現 schema 設計用不上
- outcome 寫得太抽象：「user 可以了解使用情況」— 不夠具體，反推不出元素
- 跳過 outcome 直接做 — 「邊做邊想 outcome」最終 scope creep

## Marker

`[BACKWARDS-outcome: <一句話 outcome>]`
`[BACKWARDS-element: <user 看到的元素>]`
`[BACKWARDS-step: <反推第 N 件事>]`

## 失敗時切換

- outcome 自己就模糊（寫不出假 PR description） → 切 **steelman**，把模糊 outcome 列成 2-3 個方案對比
- outcome 寫好了但元素互相衝突（例如「即時 + 不要太吵」） → 切 **adr** 記錄取捨
- 反推過程發現要動到大量現有 code → 加掛 **tidy**（refactor 部分）+ **strangler**（migration 部分）
