# cove — Chain-of-Verification

每個 claim 配一個 verification step。改完不直接收工，把所有「應該可以」變成「跑過確認」。

## Trigger 信號

- "should work" / "probably correct" / "looks good"
- "I think this is right"
- 改完直接說「完成了」沒貼輸出
- 多個 claim 串著（A 對 → B 對 → C 對 → 完成）— 任一條沒驗整串都不可信
- 「應該不會破壞別處」這種輻射宣告

## Procedure

### Step 1 — 列出所有 claim

把你的輸出 / 修改 / 結論拆成獨立 claim。一條 claim 一行。例如：

```
Claim 1: middleware 現在會檢查 null session
Claim 2: 修改後既有 test 全綠
Claim 3: 沒有破壞 /login 路徑
Claim 4: schema migration 是 backward-compatible
```

### Step 2 — 每條 claim 寫一個 verification step

verification 必須是**可執行 / 可觀察的動作**：

- 跑指令並貼輸出
- 讀檔案某行確認
- 跑特定 test
- curl 端點看 response
- query DB 看資料
- grep codebase 看引用

格式：

```
[COVE-1/N] Claim: <claim> | Verify: <可執行動作> | Result: <實際結果>
```

Result 必須是動作的真實 output，不是「應該會 ...」。

### Step 3 — 全部跑完才能宣告完成

任一 verification fail → 整體完成度回到「未完成」，回 rca 查為什麼。

不能 verify 的 claim（例如「未來不會 ...」「在某些情境下 ...」）— **明確標 unverified**，user 看得到不確定性，不藏起來。

## Anti-pattern

- Verification 寫「我有檢查」— 那不是 verification，是聲明
- Result 寫「應該 OK」— 沒跑過
- 只驗自己改的部分，沒驗連帶影響 — 違反 close loop
- claim 列得太粗（"應該都沒問題"）— 拆細，「都沒問題」拆不開不能驗

## Marker

`[COVE-N/M] Claim: ___ | Verify: ___ | Result: ___`

最後 emit `[COVE-summary: M/M passed]` 或標出哪幾條 fail / unverified。

## 失敗時切換

- 連續 2 條 verification fail → 切 **rca**，當前修改的根因判斷是錯的
- Verify 寫不出「可執行動作」 → 切 **diagnosis**，退回一步明確 diagnose
- 全部 verification 都依賴外部服務且服務掛掉 → 標 unverified、明確告知 user，不靜默 ship
