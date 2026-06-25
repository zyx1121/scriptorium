#!/usr/bin/env bash
# Armarium — instance memory auto-sync (Stop hook).
# memory/ 一旦 dirty(新增 / 修改 / 移除)就 commit + 背景 pull --rebase + push。
#
# 「memory 變動必 git」不靠 agent 自覺 —— 在 git 層掃 dirty,涵蓋所有寫入來源
# (Write/Edit、dreaming、手編、instance-specific tools)。攔特定工具會漏;
# 掃 dirty 不會。全程容錯,任何步驟失敗都 exit 0,絕不卡 session。
#
# Operates on the INSTANCE repo (SCRIPTORIUM_HOME). If the instance isn't a git
# repo (e.g. a fresh `scriptorium init`), it no-ops cleanly. push 前先 pull
# --rebase,避免跨機 non-fast-forward 永久 diverge。

set -e

# Drain stdin so claude doesn't block on the pipe.
cat >/dev/null 2>&1 || true

# The corrector/scribe review jobs commit memory/ themselves; their spawned claude
# must not double-commit.
[ -n "$SCRIPTORIUM_REVIEW" ] && exit 0

HOME_DIR="${SCRIPTORIUM_HOME:-$HOME/.scriptorium}"
cd "$HOME_DIR" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# 背景 sync:pull --rebase + push,失敗寫麵包屑、成功清除。背景子行程的 fd 必須
# 全關 —— 留著 stdout/stderr pipe 的話 hook 會等 pipe EOF 卡住。--autostash 因
# working tree 可能有 memory/ 外的 dirty;rebase 失敗一定 abort。
sync_bg() {
  (
    if err=$(git pull --rebase --autostash -q origin main 2>&1); then
      if err=$(git push -q origin main 2>&1); then
        rm -f .sync-failed
        exit 0
      fi
      step=push
    else
      git rebase --abort >/dev/null 2>&1 || true
      step="pull --rebase"
    fi
    printf '%s %s failed: %s\n' "$(date -u +%FT%TZ)" "$step" \
      "$(printf '%s' "$err" | tail -c 200 | tr '\n' ' ')" > .sync-failed
  ) </dev/null >/dev/null 2>&1 & disown
}

# 上輪 sync 的失敗麵包屑 — hook 的 stderr 會 surface,divergence 不再隱形。
if [ -f .sync-failed ]; then
  echo "scriptorium memory-sync 上次失敗($(cat .sync-failed))— 背景重試中,持續失敗手動 git pull --rebase && git push" >&2
fi

# memory/ 無任何變動(working tree + index + untracked)就跳過 —— 多數 turn 走這條。
if git diff --quiet -- memory \
   && git diff --cached --quiet -- memory \
   && [ -z "$(git ls-files --others --exclude-standard -- memory)" ]; then
  if [ -f .sync-failed ]; then sync_bg; fi     # stranded commit 也要補推
  exit 0
fi

# 索引(MEMORY.md)是各檔 frontmatter 的衍生物 — commit 前重建,讓它永遠跟 frontmatter
# 一致。gen_memory_index.py 同在此目錄(armarium/),相對自身定位,不依賴 PLUGIN_ROOT。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gen_py="$(command -v python3 || command -v python || true)"
[ -n "$gen_py" ] && "$gen_py" "$SCRIPT_DIR/gen_memory_index.py" "$HOME_DIR/memory" >/dev/null 2>&1 || true

n=$(git status --porcelain -- memory | wc -l | tr -d ' ')
git add -A memory >/dev/null 2>&1 || exit 0
# 只提交 memory/ —— 不裹挾 working tree 裡其他 dirty。
git commit -q -m "chore(memory): auto-sync ${n} file(s) [hook]" -- memory >/dev/null 2>&1 || exit 0

sync_bg

exit 0
