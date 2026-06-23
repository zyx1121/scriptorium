# threat-model — STRIDE security review

碰到任何安全邊界先列威脅，再列緩解。「之後再收」是禁區 — 今天 `using (true) -- For simplicity` 三個月後就是 PII 外洩 incident。

STRIDE 是 Microsoft 提出的六大威脅分類：Spoofing / Tampering / Repudiation / Information disclosure / Denial of service / Elevation of privilege。

## Trigger 信號

- auth / 認證 / 登入 / session 管理
- 權限 / authorization / RLS / RBAC
- user input / 表單 / API param / file upload
- 對外端點 / 公開 API / webhook
- 敏感資料：PII / token / secret / payment
- 第三方整合（SSO / OAuth / payment gateway）
- 「先這樣寫之後再收」這句話本身就是 trigger

## Procedure

### Step 1 — 定義 trust boundaries

畫出（或腦中列出）：

- 哪些是**信任的內部**（你的 server、你的 DB）
- 哪些是**不信任的外部**（user input、第三方 service、internet）
- 邊界**穿越點**在哪（API endpoint / form submit / file upload / webhook）

每條穿越邊界的線都是潛在威脅入口。

### Step 2 — STRIDE 六項輪一遍

對每個 trust boundary 跑 STRIDE：

#### S — Spoofing（身份偽造）
- 有人能不能假裝成別人？
- session token 可預測 / 可猜 / 可重放？
- API key 怎麼驗？
- 第三方 callback 簽章驗了沒？

#### T — Tampering（資料竄改）
- 傳輸途中有人改資料嗎？（HTTPS / signed payload）
- 儲存後有人改嗎？（DB write 權限 / file write）
- client-side 資料 server-side 信任嗎？（**不要**）

#### R — Repudiation（否認動作）
- 用戶能不能否認做過某動作？
- 重要操作有 audit log 嗎？
- log 完整性受保護嗎（append-only / signed）？

#### I — Information disclosure（資訊洩漏）
- 錯誤訊息洩漏內部細節嗎？（stack trace / SQL / file path）
- response body 多送了什麼？（password hash / internal IDs）
- log 寫了 PII 嗎？
- API 回應的不該回應的欄位？（過度 fetch）

#### D — Denial of service（阻斷服務）
- rate limit 有嗎？
- 大 payload / 多 request 會打掛 server 嗎？
- 昂貴的 query 有 timeout / pagination 嗎？

#### E — Elevation of privilege（權限提升）
- user 能不能取得管理員權限？
- horizontal escalation：A user 看得到 B user 資料嗎？
- vertical escalation：普通 user 變 admin 的路徑？
- RLS / policy 是否真的擋住，跑過測試了嗎？

### Step 3 — 每條威脅配緩解

```
[THREAT-S-1] Spoofing: session token 可預測
[MITIGATION] crypto-random 32-byte token, store hashed in DB
[VERIFIED] 跑了 token 隨機性測試 + 看 lib 文件確認 CSPRNG
```

如果某條威脅**無法緩解**（例如「DDoS 我們扛不住」）— 明確寫進去，標 `[ACCEPTED-RISK]`，並寫 monitoring 怎麼偵測。

### Step 4 — 過三紅線

- close loop：mitigation 跑過驗證了嗎？（自己 try 攻擊一次，不只是寫 mitigation code）
- fact-driven：「應該安全」「應該擋得住」— 沒驗證不算
- exhaust everything：STRIDE 六項都跑過了嗎？跳過任一項要寫理由

## 絕對禁區

連回 memory [[feedback_no_for_simplicity_in_security]]：

- ❌ 註解寫 "for simplicity" 在 RLS / auth / 權限附近 — 等於埋雷
- ❌ `using (true)` / `auth.role() = 'authenticated'` 當作 policy — 太鬆
- ❌ "TODO: 之後再收" 沒排定收斂時程 — 永遠收不掉
- ❌ 「先這樣寫，上 prod 前會收」— 等 prod 出事就來不及

要嘛一次寫對，要嘛明確 `TODO(security): ___` + 排定 deadline + 同步告知 user。

## Anti-pattern

- 只跑 STRIDE 自己想到的幾項 — 六項都要過
- mitigation 寫完沒驗 — 跑過攻擊測試（甚至最簡單的：嘗試用別人 ID 戳 API）
- 把「沒人會這樣攻擊」當成 mitigation — 攻擊者不照你的想像走

## Marker

`[THREAT-<letter>-N] <category>: <description>`
`[MITIGATION] <how>`
`[VERIFIED] <how confirmed>`
`[ACCEPTED-RISK] <why accepted, how monitored>`

## 失敗時切換

- STRIDE 跑出 unknown unknowns（「這條我不確定我們有沒有暴露」） → **必須 escalate 到 user**，禁止靜默 ship。安全 unknown 不靠運氣。
- mitigation 寫得出來但無法 verify（測試環境不允許 / 跨 service 無法獨立驗證） → 標 unverified + 加 monitoring + 告知 user
- 發現現有 code 已有違反 → 不是「等下次 refactor 再收」，是當下就升級為 incident 或排到本 PR 修
