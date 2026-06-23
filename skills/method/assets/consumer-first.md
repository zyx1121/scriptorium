# consumer-first — API design from caller

設計 API / function / interface 時，**先寫 3 個使用範例**，從 caller 角度看會怎麼用，再反推 signature。從實作端往外設計常常做出「對自己方便、對 caller 卡」的東西。

## Trigger 信號

- 新 API endpoint
- 新 function / class / module 公開接口
- library 的 public surface
- internal service 之間的 RPC contract
- CLI 命令的 flag 設計

## Procedure

### Step 1 — 想 3 個 caller 場景

**不是設計者想像中的場景，是 caller 真實會碰到的場景**。差別：

- 設計者想像：「user 會傳 ID 進來查 token usage」
- caller 真實：「我有 5 個 user ID，想一次拉，能不能 batch？」「我想拉某個時間範圍，怎麼指定？」「我想 stream 不是 paginate，可以嗎？」

如果想不出 3 個真實場景 → 表示需求不清，回 **backwards** 從 outcome 反推。

### Step 2 — 寫 3 個使用範例（**寫 caller code，不寫 implementation**）

```python
# Example 1: 單一 user 當下 usage
usage = await tokens.get(user_id="abc")
print(usage.total)

# Example 2: 多 user batch
usages = await tokens.get_many(user_ids=["abc", "def", "ghi"])
for u in usages:
    print(u.user_id, u.total)

# Example 3: 時間範圍
usages = await tokens.get(user_id="abc", since="2026-04-01", until="2026-05-01")
```

範例**要寫實**（用真實名字、真實場景），不要寫 `foo()`、`do_thing()`。

### Step 3 — 從 examples 反推 signature

看完 3 個 examples 你會發現：

- 參數該叫什麼名字（`user_id` vs `id` vs `uid`）— 哪個 caller 寫起來最自然？
- 該是 `get(id)` + `get_many(ids)` 還是 `get(id_or_ids)`？
- return value 該是什麼結構？（單一物件 / list / iterator / async generator）
- error handling 怎麼處理？（throw / return None / Result<T,E>）
- 必要 vs optional 參數的劃分？

**沒看過 examples 直接設計 signature**，最後常常被 caller 罵「為什麼不能直接 ___」。

### Step 4 — 反向驗證

寫好 signature 後**回頭看 3 個 examples 還順嗎**：

- Example 1 用起來像不像自然語言？
- Example 2 batch 寫起來會不會比 Example 1 醜很多？（差距太大 = API 不一致）
- Example 3 多參數時 keyword 還是 positional 比較順？

順不順 → 改 signature 直到順。

### Step 5 — 才開始實作

到這一步才寫 implementation。signature 已經被 examples 釘住，實作只是「怎麼讓它 work」。

## 進階：consumer 跨團隊 / 跨時間

如果 API 是給：

- **其他團隊用** → 把 examples 拿給對方看，問「這樣用得舒服嗎」，不要自己想
- **未來自己用**（library / 內部 framework） → examples 涵蓋多種未來可能場景，不只 happy path
- **公開 release** → 寫進 docs 當第一手 example，第一印象就是 API surface

## Anti-pattern

- 「先把 implementation 寫出來，signature 自然會出來」— 通常出來的 signature 反映 implementation 細節，不是 caller 需要
- examples 寫得太抽象（`foo(x, y)`） — 沒辦法驗證自然性
- 只寫 happy path examples — error / edge case 怎麼用？
- 不問 caller 就決定 — 「我覺得這樣比較對」，但 caller 不這樣寫
- 把 internal type 露出來當參數 — `get(opts: Options)` 反而比 `get(user_id, since, until)` 難用

## Marker

`[CONSUMER-example-N: <一句話場景描述>]`
`[CONSUMER-signature: <derived signature>]`
`[CONSUMER-verify: examples still natural]`

## 失敗時切換

- examples 互相衝突（Example 1 要簡單，Example 2 要彈性） → 切 **adr**，決定優化方向（簡單 API + 進階 API 兩條，或單一 API 偏向哪邊）
- 想不出 3 個真實 example → 切 **backwards**，回去從 outcome 反推
- caller 場景太多元無法統一 → 不要硬統一，分多個 API（`get` / `get_many` / `stream` 三個 endpoint 比一個 `query(opts)` 好）
