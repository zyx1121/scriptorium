# steelman — option comparison

要選方案時，每個方案先用**最善意框架**講一次，再對比。避免「快速否決不喜歡的方案」這種偏誤。

「Steelman」與 strawman 相反：強化對立方論點到最有力的版本，再去評估。

## Trigger 信號

- "should we use A or B"
- 2-3 個候選實作 / library / 架構
- 卡在「我傾向 X 但 Y 也合理」
- code review 時對既有方案有意見，要不要重做
- 別人提了一個你覺得不好的方案 — 先 steelman 再否決

## Procedure

### Step 1 — 列出所有候選

至少 2 個，最多 3-4 個。包含「不做」當作 baseline 候選（status quo）。

### Step 2 — 每個方案寫 3 句強化版

對每個候選方案寫 3 句，每句都從**支持者最有力的角度**：

```
[STEELMAN: Option A]
1. 它的主要優勢是 ___（具體 + 數據如果有）
2. 它解決了 ___ 這個其他方案沒處理的痛點
3. 即使它有 X 缺點，那也可以靠 Y 緩解
```

**不能寫**「但它有 ___ 問題」— 這層在下一步才出現。先強化，後對比。

### Step 3 — 建對比 matrix

挑 4-6 個對你重要的 criteria，每個方案打分（不一定數字，可以是「強 / 中 / 弱」）：

| Criterion | A | B | C |
|---|---|---|---|
| 實作成本 | 強 | 中 | 弱 |
| 維護負擔 | 中 | 強 | 中 |
| 對既有 code 衝擊 | 弱 | 強 | 中 |
| ... | | | |

Criteria 的選擇本身要透明 — 如果某個 criterion 是「我比較會用」那就明白寫，不要藏起來變成隱性 bias。

### Step 4 — 做選擇 + 寫理由

選一個，並寫**因為 ___ criterion 比 ___ criterion 重要**。如果這個取捨難寫，可能要升 ADR 正式記錄。

## Anti-pattern

- 對 A 寫優點對 B 寫缺點 — 不公平比較，是 strawman 不是 steelman
- Criteria 是事後反向工程的（先選好 A 再列「正好 A 強的 criteria」） — 自欺
- 只寫 2 個候選，硬選一個 — 第三個「不做」或「混合版」常常是真正答案

## Marker

`[STEELMAN: Option-X favorable case]`（每個方案一段）
`[STEELMAN-compare: criteria × options matrix]`
`[STEELMAN-decision: 選 X 因為 ___]`

## 失敗時切換

- 對比後沒明顯贏家（兩三個方案各勝幾條 criteria） → 切 **adr** 正式記錄決策標準 + Consequences
- Criteria 自己就模糊（「比較好」「比較對」） → 回 **backwards** 從 outcome 推導真正重要的 criteria
- 方案之間其實可以混用（不是 either-or） → 用混合版當第 N+1 個候選重新 steelman
