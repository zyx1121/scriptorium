# tidy — Tidy-First refactor

Kent Beck Tidy-First：refactor 的時候把「整理」跟「行為改變」分開做，整理的每一步都可逆、不改外部行為。

## Trigger 信號

- "this code is gross" / "我想整理一下"
- 要加新 feature 但現有 code 結構擋路（**先 tidy 再 change**）
- code review 看到亂的地方想動
- 重複 pattern 想抽 abstract
- rename / extract / inline / dead code remove

## Procedure

### Step 1 — 列出 tidy operations

每個 operation 是**單一可逆動作**：

- **rename** — 改變數 / 函式名
- **extract** — 抽出 function / variable / module
- **inline** — 把間接的東西攤平
- **reorder** — 函式 / 參數順序調整
- **dead code remove** — 確認沒人用後刪
- **simplify expression** — 邏輯等價簡化
- **move** — 搬檔案位置

每個 operation 一條 commit。不要混。

### Step 2 — 每步前後跑測試

- 動之前測試綠
- 動之後測試仍然綠
- **不綠就 revert 那一步**，不是 debug 那一步

如果測試在 tidy 過程中需要更新（例如改了引用名）— 把測試更新也視為 tidy 的一部分，但仍跑得綠。

### Step 3 — tidy 不混行為變更

- tidy commit message：`refactor: extract X from Y`、`refactor: rename foo to bar`
- behavior commit message：`feat: ...` 或 `fix: ...`

混到同一個 commit 是大忌，review 沒辦法分辨「這個 diff 改了什麼」。

### Step 4 — 先 tidy 後 change

如果是「為了加 feature 才整理」：

1. 先做完所有 tidy commits（行為不變）
2. 再 push behavior change commit
3. PR 順序：tidy PR → behavior PR；或同一 PR 但 commits 分開、reviewer 可以分段看

## Anti-pattern

- 一個大 commit 既 rename 又改邏輯 — review 看不懂
- tidy 過程中順手「修了個小 bug」— 那是 behavior 變更，獨立 commit
- 沒測試的 codebase 直接 tidy — 沒測試 = 不知道有沒有弄破，先補測試再 tidy
- 「我只是改 indent」這種 tidy 變動數百個檔案 — 工具自動化（formatter）跑一次當一個 commit，不要手動

## Marker

`[TIDY-step-N: rename / extract / inline / reorder / remove / move]`

每步一個 marker，方便 trace。

## 失敗時切換

- tidy 步驟弄破測試 → 立刻 revert 那步（不是修），回 rca 查為什麼這個「等價」的操作其實不等價
- tidy 過程發現結構問題大到不是 rename 能解 → 升級到 **adr**，這是架構決策
- 越 tidy 越亂（每步動到的東西越來越多） → 暫停，回 backwards 確認 outcome 是什麼，可能你在解錯問題
