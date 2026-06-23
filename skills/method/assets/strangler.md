# strangler — Strangler Fig migration

要替換現有系統 / API / 模組時，不要 big-bang 切換。新舊並行 → 流量逐步切過去 → 舊的最後撤掉。每一步可 rollback。

Martin Fowler 的 Strangler Fig pattern：像榕樹纏絞老樹，新系統慢慢長出來把舊系統包起來，最後舊系統可以拔掉。

## Trigger 信號

- breaking change（API contract 改變 / 資料模型改）
- 要替換 library / framework / service
- deprecate 舊 endpoint
- migrate database schema
- 拆 monolith / 合 micro-services

差別於 tidy：tidy 是內部結構整理，外部行為不變；strangler 是**外部行為要變**，但提供平順過渡。

## Procedure（三階段）

### Phase 1 — 新舊並行

新版本上線，**舊版本繼續服務**。可以是：

- 新 endpoint `/v2/foo` + 舊 endpoint `/v1/foo` 同時開
- 新 column + 舊 column 同時寫
- 新 service + 舊 service 同時跑
- 雙寫雙讀

寫一個 **feature flag / 路由開關** 控制流量比例。預設 0% 走新版。

`[STRANGLER-phase: parallel | new=0% | old=100%]`

### Phase 2 — 流量切換

逐步把流量切到新版本。**不是 0%→100% 一次切**：

- 0% → 1%（內部 / canary）
- 1% → 10%（小規模 user）
- 10% → 50%
- 50% → 100%

每一步停留至少一個指標週期（24h / 一週看情況），看 error rate / latency / 業務指標有沒有 regression。

regression 出現 → **立刻 rollback 回前一個百分比**。不要硬撐。

`[STRANGLER-phase: shift | new=10% | old=90% | observe=48h]`

### Phase 3 — 舊版退役

新版 100% 跑穩定一段時間後（不是切完當天），才開始拆舊版：

1. 確認**所有 caller 都遷移**（grep / log analytics / monitoring）
2. 加 deprecation warning 在舊版（即使流量是 0%）
3. 一段 grace period 後（通常 1-2 release cycle）
4. 刪除舊版 code

`[STRANGLER-phase: retire | old=removed]`

## Rollback 要求

**每一階段都要可 rollback**：

- Phase 1 出問題 → 把流量留在 0% / 把新版下線
- Phase 2 出問題 → 把百分比調回前一個
- Phase 3 拆完後出問題 → 從 git 拉回來，幾乎沒人做這件事但要可能

寫一份 rollback playbook 在 PR description 或 ADR 裡。**不能 rollback 的 migration 不是 strangler，是賭博**。

## 雙寫雙讀的取捨

如果是 DB schema migration：

- **雙寫**（新舊欄位都寫）→ 安全但有資料一致性負擔
- **單寫雙讀**（只寫新欄位、舊欄位 fallback 讀新欄位）→ 寫端乾淨但讀端複雜
- **shadow**（生產跑舊，新版只 dry-run 對比）→ 安全但慢

選一種寫進 ADR，講清楚為什麼。

## Anti-pattern

- big-bang 切換（"週末把 v1 關掉直接上 v2"）— 出問題沒有 rollback
- 沒有 feature flag（"我 hot-swap 一下"）— 沒辦法逐步切
- Phase 3 拆太快（剛切完 100% 隔天就刪舊 code）— 第一週通常會有遺漏的 caller
- 「強制 user 一次升級」— 通常表示沒做 strangler，做了 wall of breaking change

## Marker

`[STRANGLER-phase: parallel | shift | retire]`
`[STRANGLER-traffic: new=X% | old=Y%]`
`[STRANGLER-rollback: <一句話 rollback plan>]`

## 失敗時切換

- 舊版本無法並行（架構就不允許雙寫 / 雙跑） → 必須 escalate 到 user 對齊，明確說「無法做平順 migration，要 downtime」，**不要靜默 ship breaking change**
- 流量切換途中出 regression 但 root cause 找不到 → 切 **rca** 查根因，rollback 到上一個百分比保護生產
- 看不出 caller 全部遷移完了（"應該都遷了吧"） → 切 **source-first**，grep / log analytics 確認，不靠語感
