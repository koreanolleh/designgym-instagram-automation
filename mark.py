"""클라우드 루틴의 상태 기록 스크립트 — 모든 기록은 즉시 커밋·push된다.

배경(2026-08-11 분석): 클라우드 세션은 발화 후 5~8분 안에 예고 없이 끝나는 일이 반복됐다.
죽는 시점이 매번 달라서 (a) 시작도 못 함, (b) 게시까지 하고 커밋 전에 죽음, (c) 전부 성공
세 경우를 밖에서 구분할 수 없었다. 그래서:
  - 루틴은 시작하자마자 heartbeat를 남긴다 (죽어도 "시작은 했다"가 남음)
  - 게시 성공 즉시 tiktok-done을 실행한다 (플래그·로그·커밋·push를 한 번에)
  - 감시 워크플로는 heartbeat 유무로 "미실행"과 "중단"을 구분한다

사용:
  python3 mark.py heartbeat daily                 # 시작 직후 1회
  python3 mark.py tiktok-done --publish-id ID --song-id SID --song-name "이름"
  python3 mark.py tiktok-fail --reason "한 줄 사유"
"""
import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
BASE = os.path.dirname(os.path.abspath(__file__))
PENDING = os.path.join(BASE, "pending_posts.json")
HEARTBEAT = os.path.join(BASE, "routine_heartbeat.log")
PUBLISH_LOG = os.path.join(BASE, "tiktok_publish.log")
MUSIC_LOG = os.path.join(BASE, "tiktok_music.log")


def now():
    return datetime.now(KST)


def run(cmd):
    p = subprocess.run(cmd, cwd=BASE, shell=True, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def commit_push(message):
    run("git config user.name claude-cloud")
    run("git config user.email cloud@example.com")
    run("git add -A")
    rc, _ = run("git diff --staged --quiet")
    if rc == 0:
        print("변경 없음")
        return True
    run(f'git commit -m "{message}"')
    for attempt in range(1, 4):
        rc, out = run("git push")
        if rc == 0:
            print(f"push 성공 (시도 {attempt})")
            return True
        print(f"push 실패 (시도 {attempt}): {out[-200:]}", file=sys.stderr)
        run("git pull --rebase --autostash")
        time.sleep(3)
    print("push 최종 실패", file=sys.stderr)
    return False


def append(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def today_entry():
    data = json.load(open(PENDING, encoding="utf-8"))
    today = now().strftime("%Y-%m-%d")
    for day, p in data.get("posts", {}).items():
        if p.get("date") == today:
            return data, day, p
    return data, None, None


def cmd_heartbeat(kind):
    append(HEARTBEAT, f"{now().strftime('%Y-%m-%d %H:%M:%S')} {kind} start")
    ok = commit_push(f"💓 {now().strftime('%Y-%m-%d')} {kind} 루틴 시작")
    sys.exit(0 if ok else 1)


def cmd_tiktok_done(args):
    data, day, entry = today_entry()
    if entry is None:
        print("오늘자 항목 없음", file=sys.stderr)
        sys.exit(1)
    entry["tiktok_posted"] = True
    entry["posted"] = True
    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    d = now().strftime("%Y-%m-%d")
    if args.song_id:
        append(MUSIC_LOG, f"{d} {args.song_id} {args.song_name or ''}".rstrip())
    append(PUBLISH_LOG, f"{d} 루틴 자동 게시 성공: {args.publish_id} ({day})")
    ok = commit_push(f"✅ {d} TT 발행 ({day})")
    sys.exit(0 if ok else 1)


def cmd_tiktok_fail(reason):
    d = now().strftime("%Y-%m-%d")
    append(PUBLISH_LOG, f"{d} 보류/실패: {reason}")
    ok = commit_push(f"⚠️ {d} TT 미발행 기록")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    hb = sub.add_parser("heartbeat"); hb.add_argument("kind", choices=["daily", "weekly"])
    td = sub.add_parser("tiktok-done")
    td.add_argument("--publish-id", required=True)
    td.add_argument("--song-id", default="")
    td.add_argument("--song-name", default="")
    tf = sub.add_parser("tiktok-fail"); tf.add_argument("--reason", required=True)
    args = ap.parse_args()

    if args.cmd == "heartbeat":
        cmd_heartbeat(args.kind)
    elif args.cmd == "tiktok-done":
        cmd_tiktok_done(args)
    elif args.cmd == "tiktok-fail":
        cmd_tiktok_fail(args.reason)


if __name__ == "__main__":
    main()
