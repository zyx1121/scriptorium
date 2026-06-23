# adr — Architecture Decision Record

跨 module / 跨 service / 長期後果的決策寫 ADR — 不是為了形式，是為了未來自己看得懂當初為什麼這樣選。

## Trigger 信號

- 跨 module / 跨 service / 跨 repo 的決策
- 影響資料模型 / API contract / 部署架構的選擇
- 「現在這樣做之後一定後悔嗎」的判斷
- steelman 後沒明顯贏家，要正式記錄為什麼選 X
- 變更會卡住 future flexibility（例如選了某 vendor / 某 protocol）

不是所有決策都要 ADR。一個 function 內部選 map 還是 Set 不用 ADR — ADR 是給「半年後翻 git log 找不到答案」那種決策用的。

## Procedure

寫一份 ADR，至少 5 段：

### 1. Context

問題是什麼、當前限制、為什麼現在要決定（不能再拖的原因）。不寫解法。

### 2. Options Considered

至少 2-3 個。每個一段：

- 怎麼做（精簡描述）
- 強項
- 弱項
- 已知未知（如果有）

如果你有 steelman 過，把每個 option 的 favorable case 直接帶過來。

### 3. Decision

選 X。一句話。

### 4. Consequences

最重要的一段。三類都要：

- **好的**：選了 X 之後預期的好處（具體）
- **壞的**：選了 X 之後承擔的代價（具體）
- **風險 / unknown**：哪些情況下這個決策會變壞？怎麼偵測？

寫不出 Consequences = 你還沒準備好決策。回 measure 或 source-first 補資料。

### 5. Revisit signal

什麼時候 / 在什麼信號出現時，要回來重新評估這個決策。例如：

- 「user 數超過 10k 時 revisit」
- 「vendor X 漲價 > 2x 時 revisit」
- 「跑半年內 revisit 一次」

不寫 revisit signal = 假設這個決策永遠不會變，多半不對。

## 存放位置

選一個，整個 codebase 一致：

- `docs/adr/NNNN-decision-name.md`（最常見，repo 內 versioned）
- PR description（決策 + 變更同個地方）
- Notion / Confluence（如果團隊在那邊）

NNNN 是流水號，從 `0001` 開始。檔名用 kebab-case。

## Anti-pattern

- Consequences 只寫好的，不寫壞的 — 半年後出問題會被罵當初沒講
- Options 只寫了「選的那個」，沒列其他 — 別人看不到對比
- 過度 ADR：一個 function 寫法也來 ADR — overhead 大於 value
- 寫完就丟 — Revisit signal 沒人追蹤等於沒寫

## Marker

`[ADR-NNNN: <title>]`（行內引用）

ADR 檔內部用標準小節：Context / Options / Decision / Consequences / Revisit。

## 失敗時切換

- 寫不出 Consequences（壞的那欄） → 切 **measure**，沒數據先不決策
- Options 都列了但 trade-off 無法決定 → 回 **steelman** 把對比 matrix 寫清楚
- 決策依賴未知的外部行為（vendor / spec / 同事決定） → 標 unknown，等資訊回來再 close，不要硬選
