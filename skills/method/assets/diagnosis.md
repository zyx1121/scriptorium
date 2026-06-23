# diagnosis — pre-edit anchor

要改 code 前先把診斷外部承諾出來。防止「分析正確但不行動」、「動了但動錯地方」、「漂亮分析變零交付」三種失敗。

## Trigger 信號

- 有 traceback / error message
- test 紅了，要動 code 修
- 線上異常，要 hotfix
- "這 bug 應該是 X 造成的" — 動手前先寫
- rca 走完，根因找到了，要修 — 動手前先寫

差別於 rca：rca 是**找根因的過程**；diagnosis 是**找到根因準備動手前的承諾**。常常 rca → diagnosis → edit。

## Procedure

改任何 code / config 前輸出一行（**一行就夠，不要寫作文**）：

```
[DIAGNOSIS] 問題是 ___；證據是 ___；下一步動作是 ___。
```

三個位置都填，缺一不可：

- **問題是** — 一句話描述根因（不是症狀）
- **證據是** — 為什麼相信這個根因（file:line / error msg / 復現 / spec）
- **下一步動作是** — 具體要改什麼（哪個檔、哪個函式、哪個值）

## 規則

### 行動必須對齊證據指向

如果證據指向 `auth/middleware.ts:42`，下一步動作必須處理那個位置。**要動別處必須先寫為什麼**，例如「`middleware.ts:42` 是表象，根因在 `session-store.ts`，因為 ...」。

### 「修完後原來的測試會 fail」不是不行動理由

通常那個測試在 assert「舊 bug 存在」。修完它本來就該 fail。更新測試 / 跑真正的回歸，而不是因為怕弄破測試就不修。

### 證據要標來源類型

- 錯誤原文：`error: "TypeError: ..."`
- 源碼上下文：`src/foo.ts:42`
- 復現實驗：`執行 X 後得 Y`
- 官方文件：URL
- 歷史先例：`commit abc123 / issue #42`

## Anti-pattern

- 寫得像作文：「經過深入分析，我認為 ...」— 砍掉，三句話完事
- 證據是「我覺得」「應該是」— 那叫推測不叫證據
- 動作模糊：「修一下 auth」— 要說「在 `middleware.ts:42` 加 null check」
- 跳過 diagnosis 直接動手 — 之後發現方向錯，所有 edits 要 revert，浪費更多

## Marker

`[DIAGNOSIS] 問題是 ___；證據是 ___；下一步動作是 ___。`

可以在過程中多次出現 — 每次方向改了就重發一個，留 trace。

## 失敗時切換

- 寫不出來「證據是 ___」 → 切 **source-first**，連事實都還沒收集到，沒資格 diagnose
- 寫了 diagnosis 但動完沒解決 → 切 **rca** 退回查根因（這個 diagnosis 的根因判斷錯了）
- 寫不出來「下一步動作是 ___」 → 根因沒找到位置，回 rca
