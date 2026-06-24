---
name: authoring
description: "Author NEW skills & agents from session signal (Scribe office) — scan a recent transcript, extract reusable PROCEDUREs into skill drafts and recurring DELEGATION needs into agent drafts, and propose them to staged/ for you to adopt. Propose-only, never auto-writes a behaviour definition. Run when you want the agent to grow its own capabilities from what it has been doing repeatedly. Triggers on '/authoring', 'author a new skill', 'author an agent', '從 session 長出 skill', '把這套流程變成 skill', 'scribe authoring', 'grow a new worker', 'kilo 自己長 skill/agent'."
---

# Authoring — grow new skills & agents (Scribe office)

從 session signal 長出**新**手稿:反覆出現、長期需要的 procedure → skill draft;反覆被下放的工作 → agent draft。**propose-only** —— 候選丟 `staged/author.jsonl` 等你採納,**絕不自動寫進 `skills/` 或 `agents/`**(自動生成的行為定義必須你把關)。

> 這是 Scribe 職司的**創造**半邊,與 Corrector 的校訂半邊(`skill_review` / `agent_review` / `/dreaming`)對稱。它**只 create,不 consolidate / promote** —— 那是 Corrector。把兩者混在一起,正是 CHARTER 第一條邊界禁止的(舊 monolithic review job 的 #1 亂源)。

## 何時跑

- **不是每 session** —— authoring 要 batch 才看得出「反覆 / long-term」。攢一段時間或一批 session 再跑。
- 你察覺自己**重複手做某套流程**、或**重複手派某類工作**時。
- daemon 可排程(每天掃前一天 session,對稱舊 growth review 的 batch 節奏)。

## Workflow

### 1. 萃取(propose)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scribe/author.py" [--session <id>] [--dry]
```

- 不給 `--session` → 最新一個還沒 author 過的 session(state 記在 `$SCRIPTORIUM_HOME/state/authored-sessions.json`)。
- `--dry` → 只萃取印出,不寫 staged、不記 state(先驗品質,沿用舊 review 的 dry 習慣)。
- 候選落 `$SCRIPTORIUM_HOME/staged/author.jsonl`,每條:`kind`(skill|agent) · `slug` · `title` · `rationale`(為什麼 recurs / long-term)· `draft`(SKILL.md body 或 agent system prompt)· 來源 `session`。

### 2. 採納(你把關)

- 讀 `staged/author.jsonl`,逐條看 `rationale` —— 它憑什麼說這 recurs / 值得長期留。
- 值得的 → 把 `draft` 整理進 instance:
  - skill → `$SCRIPTORIUM_HOME/skills/<slug>/SKILL.md`
  - agent → `$SCRIPTORIUM_HOME/agents/<slug>.md`(對齊 `agents/README.md` 的回報 contract)
- 不值得的 → 刪掉那行。**採納是你的判斷,不是自動的** —— 呼應「如果會長期需要的話」。
- 採納後跑 `python3 "${CLAUDE_PLUGIN_ROOT}/armarium/bind.py"` 把新 skill/agent symlink 進 runtime。

## 邊界

- **propose-only**:`author.py` 永不寫 `skills/` `agents/` `CANON.md`。
- **secret scrub**:萃取前 transcript 已 scrub credential(從 raw 逐字稿萃取的防洩密,沿用舊 DESIGN 的 Info-Disclosure 對策);採納 draft 時仍自己掃一眼。
- **只 create**:去重 / 合併 / 晉升是 Corrector(`/dreaming`),不在這裡做。
