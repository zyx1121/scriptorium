# null — pass-through, no method

Router classified the task as trivial. No methodology overhead, do the work.

## Trigger 信號

- 單一 tool call 解決（一次 Edit / 一次 Read / 一次 Bash）
- 無分支判斷、無失敗風險
- rename / format / 單檔讀取 / 簡單查閱 / 抓檔案內容
- 確切已知步驟、不需要驗證 root cause

## Procedure

1. Emit `[METHOD: null]`
2. 直接做

## 紅線仍然適用

null 不是「跳過品質要求」。三紅線（close loop / fact-driven / exhaust）對任何 method 都壓著：

- rename 後仍要 grep 確認沒有舊名字殘留 — 這是 close loop，不是 method
- 改 config 後仍要重啟 / reload 驗值有生效

如果動作做到一半發現有分支 / 失敗信號 / 連帶影響，**重新 classify**，可能要升級成 rca / diagnosis / 其他 method。

## 失敗切換

null 沒有「失敗」概念。如果出乎意料：

- 動作展開後發現是 debug → 重新路由到 rca
- 改完發現有連帶影響 → diagnosis 寫下來，重新評估範圍
- 「rename」其實牽涉跨檔重構 → 升級到 tidy
