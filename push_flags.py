"""발행 기록을 저장소에 밀어넣는다 — 다른 워크플로와 겹쳐도 유실되지 않게.

왜 필요한가 (2026-11-03 사고): ig_daily 와 tiktok_daily 가 같은 초에 끝나
둘 다 `pending_posts.json` 을 커밋했다. 뒤에 push 한 틱톡 쪽이 거부되고
`git pull --rebase` 가 같은 파일에서 충돌 → 리베이스가 멈춘 채 단계가 실패했다.
**틱톡은 실제로 올라갔는데 `tiktok_posted` 가 저장소에 남지 않았다.** 그러면
22:30 감시 워크플로가 같은 영상을 또 올린다(중복 발행).

기존 재시도 루프(`git pull --rebase --autostash`)로는 못 막는다. 두 워크플로는
같은 파일의 **다른 키**를 건드리는데, 리베이스는 파일 단위로만 볼 수 있어서다.

그래서 여기서는 충돌하면 원격을 기준으로 되돌린 뒤 **내가 바꾼 키만 다시 얹는다.**
- JSON: 시작점(HEAD) 대비 내가 바꾼 잎(leaf)만 기억해서 원격 최신본에 재적용
- 로그: 내가 덧붙인 줄 중 원격에 없는 것만 다시 덧붙인다

사용: python3 push_flags.py --message "✅ ... 발행" pending_posts.json tiktok_publish.log
"""
import argparse
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
TRIES = 5


def git(cmd, check=False):
    p = subprocess.run("git " + cmd, cwd=BASE, shell=True,
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {cmd} 실패: {(p.stdout + p.stderr).strip()[-300:]}")
    return p.returncode, (p.stdout + p.stderr).strip()


def head_blob(path):
    """커밋 전 시작점의 파일 내용. 새 파일이면 None."""
    p = subprocess.run(f"git show HEAD:{path}", cwd=BASE, shell=True,
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def leaf_diff(old, new, trail=()):
    """new 에서 바뀌거나 새로 생긴 잎들을 (경로, 값) 목록으로 돌려준다."""
    if isinstance(old, dict) and isinstance(new, dict):
        out = []
        for k, v in new.items():
            out += leaf_diff(old.get(k), v, trail + (k,))
        return out
    return [] if old == new else [(trail, new)]


def leaf_apply(doc, trail, value):
    """leaf_diff 로 뽑은 잎 하나를 doc 에 얹는다. 중간 경로가 없으면 만든다."""
    cur = doc
    for k in trail[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
    cur[trail[-1]] = value


def json_delta(base_text, mine_text):
    """내가 JSON 파일에 가한 변경을 '다시 얹을 수 있는' 형태로 뽑는다.

    - dict  : 바뀐 잎 목록 — 남이 건드린 다른 키를 지우지 않는다(발행 플래그가 이 경우)
    - list  : 뒤에 덧붙인 항목들 — edit_history.json 처럼 쌓이기만 하는 파일
    - 그 외 : 통째로 덮기

    edit_history.json 은 최상위가 배열이라 잎 방식으로는 다룰 수 없다. 경로가 빈
    잎을 그대로 얹으려 하면 IndexError 로 터지므로 여기서 갈라낸다.
    """
    try:
        mine = json.loads(mine_text)
    except json.JSONDecodeError:
        return ("raw", None)
    try:
        base = json.loads(base_text) if base_text else None
    except json.JSONDecodeError:
        base = None

    if isinstance(mine, dict):
        return ("leaves", leaf_diff(base if isinstance(base, dict) else {}, mine))
    if isinstance(mine, list):
        old = base if isinstance(base, list) else []
        if mine[:len(old)] == old:                 # 덧붙이기만 했다
            return ("append", mine[len(old):])
        return ("raw", None)                       # 중간이 바뀌었으면 통째로
    return ("raw", None)


def json_reapply(path, kind, payload, mine_text):
    """원격 최신본 위에 json_delta 로 뽑아둔 내 변경만 다시 얹는다."""
    if kind == "raw":
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(mine_text)
        return
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if kind == "leaves":
        for trail, val in payload:
            if trail:
                leaf_apply(doc, trail, val)
    else:                                          # append
        have = {json.dumps(x, sort_keys=True, ensure_ascii=False) for x in doc}
        for item in payload:
            if json.dumps(item, sort_keys=True, ensure_ascii=False) not in have:
                doc.append(item)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()

    files = [f for f in a.files if os.path.exists(os.path.join(BASE, f))]
    if not files:
        print("기록할 파일이 없다")
        return 0

    # 내가 무엇을 바꿨는지, 커밋하기 전에 먼저 붙잡아 둔다.
    mine, changes = {}, {}
    for f in files:
        with open(os.path.join(BASE, f), encoding="utf-8") as fh:
            mine[f] = fh.read()
        base = head_blob(f)
        if f.endswith(".json"):
            changes[f] = json_delta(base, mine[f])
        else:
            old = (base or "").splitlines()
            changes[f] = ("lines", [ln for ln in mine[f].splitlines() if ln not in old])

    git("config user.name github-actions[bot]")
    git("config user.email github-actions[bot]@users.noreply.github.com")
    git("add " + " ".join(files))
    if git("diff --staged --quiet")[0] == 0:
        print("변경 없음")
        return 0
    git(f'commit -m "{a.message}"', check=True)

    for attempt in range(1, TRIES + 1):
        if git("push")[0] == 0:
            print(f"push 성공 (시도 {attempt})")
            return 0
        if attempt == TRIES:
            break
        print(f"push 거부 (시도 {attempt}) — 원격 기준으로 내 변경만 다시 얹는다",
              file=sys.stderr)
        git("fetch -q origin main", check=True)
        git("reset -q --hard origin/main", check=True)

        for f in files:
            full = os.path.join(BASE, f)
            kind, payload = changes[f]
            if kind == "lines":
                have = []
                if os.path.exists(full):
                    with open(full, encoding="utf-8") as fh:
                        have = fh.read().splitlines()
                add = [ln for ln in payload if ln not in have]
                if add:
                    with open(full, "a", encoding="utf-8") as fh:
                        fh.write("\n".join(add) + "\n")
            elif os.path.exists(full):
                json_reapply(full, kind, payload, mine[f])
            else:                                   # 원격에 없던 새 파일
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(mine[f])

        git("add " + " ".join(files))
        if git("diff --staged --quiet")[0] == 0:
            print("원격에 이미 반영돼 있다 — 더 할 일 없음")
            return 0
        git(f'commit -m "{a.message}"', check=True)
        time.sleep(3)

    print("::error::발행 기록 push 최종 실패 — 플래그가 저장소에 없으면 중복 발행된다",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
