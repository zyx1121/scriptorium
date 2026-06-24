---
name: dreaming
description: "Memory consolidation — 整理整個 instance memory($SCRIPTORIUM_HOME/memory):清過時/雜訊、合併重疊、修正與 source-of-truth(CANON.md / 各 instance docs)矛盾的、把 reusable procedure 提升成 skill、同步 MEMORY.md index。像睡眠時大腦整理記憶,一次處理一批。Triggers on '/dreaming', '整理 memory', '記憶太亂', 'memory 去重', 'memory consolidation', '清記憶', '整理一下記憶'."
---

# Dreaming — Memory Consolidation (Corrector office)

整理 instance 的 `$SCRIPTORIUM_HOME/memory`(全 runtime 共享的 durable memory):清、整理、去重、提升成 skill。像睡眠時大腦整理記憶 —— 不是每次 session 跑,是**定期一次處理一批**。

> 這是 Corrector 職司的 consolidation 半邊(校訂既有手稿);calibration 半邊由背景的 `corrector/skill_review.py` 自動跑。

## Workflow

### 1. 盤點
- 讀 `$SCRIPTORIUM_HOME/memory/MEMORY.md`(index)+ `ls $SCRIPTORIUM_HOME/memory/*.md`。
- 比對 index 行數 vs 實際檔數(漂移?孤兒?)。
- 跑 `python3 "${CLAUDE_PLUGIN_ROOT}/armarium/gen_memory_index.py" "$SCRIPTORIUM_HOME/memory"` —— 看輸出的 `LINT` 區塊,它列出 missing-title / bad-type / orphan-link 三類規範問題,即「規範對齊」step 的待修清單。

### 2. 偵測(逐篇 + 跨篇)
- **過時**:跟 source-of-truth 矛盾 —— `CANON.md`(人格/慣例/guardrails)、instance 的設備/環境 docs、各 project repo。例:memory 寫某 port 但 canon/docs 是另一個。
- **重抄 source-of-truth**:memory 抄了 CANON.md 的工作原則、設備清單 —— 違反「索引不抄 source of truth」,刪 memory、指向正本。
- **重疊**:同主題多篇 → 合併成一篇,保留各自獨特點。
- **雜訊**:一次性、太 project-specific 的操作細節、abstract 到下次 match 不到的(description 無法 match 等於沒存)。
- **該升 skill**:描述「怎麼做某事」的 reusable procedure 重複出現 → 提升成 `$SCRIPTORIUM_HOME/skills/<name>/SKILL.md`(或併入現有 skill),memory 只留指標。
- **規範對齊**:frontmatter / 結構漂移 —— 缺 `title`、`type` 缺漏或對不上檔名前綴、wiki-link `[[x]]` 命名漂移(`-` vs `_`、解不到實檔)、description 抽象到 match 不到。前三類 gen linter 已自動列在 `LINT` 區塊。**修正(補 `title` / 改 `type` / 統一 link 命名)是非破壞性 frontmatter 編輯,直接改、不必先問** —— 只有刪 / 合併 memory 才需確認。

### 3. 處理(逐項)
- **刪 / 合併 / 修正前,先列清單給使用者確認** —— 刪 memory 是 destructive。寧可先標 `deprecated: true` + 一行警告 + 指向正本,也不擅自刪。
- **合併**:`Write` 一篇涵蓋重疊核心的新檔 → `git rm` 舊檔。
- **提升成 skill**:把 procedure 抽成 `SKILL.md`(放 instance `skills/`),memory 端刪掉或留一行指標。

### 4. 重建索引 + commit
- `MEMORY.md` 是衍生物:**只編各檔 frontmatter 的 `title`/`description`(單一源),絕不手編 `MEMORY.md`**。跑 `python3 "${CLAUDE_PLUGIN_ROOT}/armarium/gen_memory_index.py" "$SCRIPTORIUM_HOME/memory"` 重建(memory-sync.sh 每次 commit 前也會自動跑)。
- `git -C "$SCRIPTORIUM_HOME" add -A && commit && push`(若 instance 是 git repo)。
- 改完可 `claude -p` 開新 session 驗證 recall / skill 載入。

## Canonical frontmatter(規範對齊基準)
每篇 memory:`name`(= 檔名去 `.md`)、`title`(一行短標籤)、`description`(**用雙引號包** —— 裸值會被 Claude Code 的 memory normalizer 截斷;具體到下次任務 match 得到)、`type`(`feedback` / `project` / `reference` / `user`,對齊檔名前綴)。wiki-link 一律用實檔名(底線),`[[name]]` 要解得到。

## 判準(別違反)
- **一檔一事**、frontmatter 齊(`title` + `type` + 具體 `description`)。
- **索引不抄 source of truth** —— 重複 CANON.md / instance docs 的刪掉、指向正本。
- **「事實」留 memory,「怎麼做」升 skill**。
- 刪 = destructive,**先問**(對齊 CANON 的 destructive guardrail)。
