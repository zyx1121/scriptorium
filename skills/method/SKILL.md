---
name: method
description: "INVOKE FIRST for any non-trivial coding/decision task — classifies and loads the matching procedure (13 methods: RCA, CoVe, steelman, ADR, tidy, measure, strangler, source-first, threat-model, etc). Triggers: '2+ failed fixes' / '為什麼還不行', 'should work / probably correct', traceback / test red, 'A or B' / '要選 A 還是 B', latency / '怎麼這麼慢', breaking change / migration, auth / RLS / 權限 edits, vague spec, refactor / 整理, API design, stuck > 30min / 卡住. Skip trivial single-action tasks."
---

# /method — procedure router

每接到一個非 trivial 任務先在腦裡走三步：

1. **Classify** — 對著下面路由表的 trigger column 找最貼近的信號
2. **Emit `[METHOD: <name>]` 一行**宣告路由結果（user 看得到，agent 自己對齊）
3. **Load 對應 asset** — `Read ${CLAUDE_SKILL_DIR}/assets/<name>.md` 拿完整 procedure；null 例外，直接做事

trivial 跟 non-trivial 的界線：trivial = 單一 tool call、無分支判斷、無失敗風險（rename、format、單檔讀取、簡單查閱）。其他都走路由。

---

## 路由表

| Trigger 信號 | Method | Asset |
|---|---|---|
| trivial / 單工具 / 純查閱 | **null** | — |
| debug / 2+ 失敗 / "why isn't this working" / 同 bug 修不掉 | **rca** | `rca.md` |
| traceback / 線上異常 / 改 code 前 / 測試紅 | **diagnosis** | `diagnosis.md` |
| "should work" / "probably correct" / 改完直接收 / 未驗證宣告 | **cove** | `cove.md` |
| 新 feature spec 模糊 / "build something that..." | **backwards** | `backwards.md` |
| 2-3 方案要選 / "should we use A or B" | **steelman** | `steelman.md` |
| 跨 module / 跨 service / 長期後果的決策 | **adr** | `adr.md` |
| refactor / 清理 / "this code is gross" | **tidy** | `tidy.md` |
| 效能優化 / "怎麼這麼慢" / latency 抱怨 | **measure** | `measure.md` |
| 遷移 / breaking change / deprecate old API | **strangler** | `strangler.md` |
| research / 概念釐清 / "how does X work" | **source-first** | `source-first.md` |
| 安全 / auth / 權限 / RLS / 對外端點 / user input | **threat-model** | `threat-model.md` |
| stuck > 30min / 卡死 / 找不到頭緒 | **cunningham** | `cunningham.md` |
| API / interface / function signature design | **consumer-first** | `consumer-first.md` |

多個 trigger 同時命中（常見：debug + verification）就**疊著用**。一個 session 走兩三條 method 是常態，不是異常。

---

## 失敗切換鏈

當前 method 走不通時不重複它，依下表切下一條。重點是**失敗時換工具，不是換情緒**。

| 從 | 失敗信號 | 切到 |
|---|---|---|
| rca | 5-Why 撞到「我不知道」 | tidy（先清環境）→ cunningham（最小複現） |
| cove | 驗證連 2 條 fail | rca（退回查根因） |
| diagnosis | 寫不出 `[DIAGNOSIS]` | source-first（連事實都還沒收集） |
| backwards | outcome 自己就模糊 | steelman（先把模糊 outcome 列成方案對比） |
| steelman | 對比後仍無明顯贏家 | adr（記錄決策標準，接受不確定） |
| adr | 寫不出 Consequences | measure（沒數據先不決策） |
| tidy | tidy 步驟弄破測試 | 立刻 revert 該步，回 rca |
| measure | profile 指向外部服務 | adr（升級為架構決策） |
| strangler | old 無法並行 | 必須升級到 user 對齊，不靜默 ship |
| source-first | 找不到 primary source | 明確標 uncertainty，不憑語感編 |
| threat-model | STRIDE 出現 unknown unknowns | 必須升級到 user，禁止靜默 ship |
| cunningham | 最小複現都寫不出 | 停手、寫下當前理解，等下一輪 |
| consumer-first | caller examples 互相衝突 | adr（決定為哪種 caller 優化） |

---

## 三條紅線（不變條件，任何 method 都壓在上面）

1. **Close the loop** — 聲稱完成前跑驗證 + 貼輸出證據。沒有輸出的完成叫自嗨。
2. **Fact-driven** — 「可能是環境」「API 不支援」「版本不合」之前用工具驗。未驗證的歸因不寫。
3. **Exhaust everything** — 說「無法解決」之前 routing 表跟切換鏈走完了嗎？沒走完就放棄叫缺乏韌性。

三條跟 method 選擇無關 — 走 null 也要守，走 rca 也要守。

---

## Sub-agent 注入

spawn subagent（Agent tool）時，**必須在 prompt 末尾加注入指令**，否則 subagent 沒看過這套路由是裸奔：

```
開工前 Read 以下檔案，按其中 procedure 走：
- ${CLAUDE_SKILL_DIR}/SKILL.md（路由邏輯 + 三紅線）
- ${CLAUDE_SKILL_DIR}/assets/<method>.md（這次任務的 method）
```

派活不注入 = 收回來的活沒 method、沒閉環、沒驗證 — 那是 spawn 的人的問題，不是 subagent 能力問題。

---

## 例子

**Trivial**：「把 `foo.ts` 第 12 行的 `userId` 改成 `userID`」 → `[METHOD: null]` → 直接 Edit。

**Debug**：「這個 test 我改了三次還是 fail」 → `[METHOD: rca]` → Read `assets/rca.md` → 跑 5-Why。

**疊用**：「新 feature：給用戶看 token usage 統計」 → `[METHOD: backwards]` 先做 outcome 反推 → `[METHOD: consumer-first]` 再設計 API → `[METHOD: cove]` 完成後驗證。

**轉換**：「優化這段 SQL 慢的問題」→ `[METHOD: measure]` profile → profile 指向 N+1 join，但根因是 schema → 切到 `[METHOD: adr]` 記錄是要改 schema 還是加 index。
