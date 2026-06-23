# measure — profile before optimize

優化前先量。沒數據先不動。「我覺得這裡慢」的優化九成是優化錯地方。

## Trigger 信號

- "怎麼這麼慢" / "latency 太高" / "卡卡的"
- 某個 endpoint / query / page load 變慢
- bundle size 抱怨
- memory / CPU 使用率高
- 「我們應該優化 X」的建議

## Procedure

### Step 1 — 建立 baseline

優化前先 **量現在的數字**。沒 baseline 等於沒辦法宣稱「優化了」。

- 端到端 latency（p50 / p95 / p99，不只 average）
- throughput（req/s）
- 資源（memory peak / CPU %）
- bundle size / network bytes
- 視 case 而定

寫下來 `[MEASURE-baseline: p95 = 850ms]`。

### Step 2 — Profile 找熱點

跑 profiler / tracer / explain analyze / chrome devtools / py-spy / pprof / 視語言環境。

**目標是找出實際耗時在哪**，不是想像中應該在哪。

常見驚奇：

- 以為慢在 SQL，其實慢在 ORM serialize
- 以為慢在網路，其實慢在 JSON parse
- 以為 CPU bound，其實 IO bound
- 以為 N+1，其實是 N+1+M+1

寫下來 `[MEASURE-hotspot: <實際慢在哪> @ <某段 code / 某 query>]`。

### Step 3 — Only fix verified hotspot

只改 profiler 指出的位置。不順手「優化看起來慢的別處」— 那是猜。

如果 hotspot 是外部服務 / 不可改的依賴 → 升 ADR（要不要換、加 cache、改架構）。

### Step 4 — Re-measure

優化後**再量一次同樣的指標**。

- 改善多少？（p95 從 850ms → 300ms）
- 有沒有 regression？（throughput 是否下降）
- 在預期負載下表現如何？

寫下 `[MEASURE-after: p95 = 300ms (-65%)]`。

如果改善不夠或有 regression → 回 step 2，profile 還沒找對熱點。

## No-data rule

任何「我覺得 X 慢」「應該優化 Y」的判斷 — **先 measure 才有資格動手**。

例外：明顯算法錯誤（O(n²) 對 100k 資料）— 但也建議先量驗證 hotspot，因為大 codebase 常常 hotspot 在你想不到的地方。

## Anti-pattern

- 沒 baseline 就動手，最後說「感覺快了」— 沒辦法 reviewer 評估
- 一次改很多地方，分不清是哪一條改善 — 拆成多個 commit / PR
- 把 micro-benchmark 結果直接套用到 production 規模 — 量級不對結論常常反過來
- 過早優化還沒成 hotspot 的東西 — Knuth：premature optimization is the root of all evil

## Marker

`[MEASURE-baseline: <metric = value>]`
`[MEASURE-hotspot: <where> @ <evidence>]`
`[MEASURE-after: <metric = value (delta)>]`

## 失敗時切換

- profiler 指向外部服務 / 不能改的依賴 → 切 **adr**，這變架構決策（要不要 cache / 換 vendor / 改架構）
- 找不到 hotspot（時間平均分散沒有熱點） → 算法 / 資料模型問題，回 **backwards** 從預期 outcome 反推合理性能 budget
- 改了一輪沒有 measurable 進步 → 回 **rca**，可能根因 ≠ profiler 指的點
