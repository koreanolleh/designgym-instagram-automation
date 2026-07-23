"""Instagram Graph API로 이미지 1장을 게시한다 (컨테이너 생성 → 발행 2단계)."""
import os
import time
import requests

GRAPH_VERSION = "v21.0"
# Instagram 로그인 기반 토큰(IGAA...)은 graph.facebook.com이 아니라 graph.instagram.com을 사용한다.
GRAPH_HOST = "https://graph.instagram.com"


def post_image(image_url: str, caption: str) -> str:
    token = os.environ["IG_ACCESS_TOKEN"]
    ig_user_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    base = f"{GRAPH_HOST}/{GRAPH_VERSION}/{ig_user_id}"

    create_resp = requests.post(f"{base}/media", data={
        "image_url": image_url,
        "caption": caption,
        "access_token": token,
    })
    create_resp.raise_for_status()
    creation_id = create_resp.json()["id"]

    # 컨테이너가 IG 서버에서 이미지를 가져와 처리하는 데 시간이 걸릴 수 있음 (status_code 폴링)
    for _ in range(10):
        status = requests.get(f"{base[:base.rfind('/')]}/{creation_id}", params={
            "fields": "status_code",
            "access_token": token,
        }).json()
        if status.get("status_code") == "FINISHED":
            break
        time.sleep(3)

    publish_resp = requests.post(f"{base}/media_publish", data={
        "creation_id": creation_id,
        "access_token": token,
    })
    publish_resp.raise_for_status()
    return publish_resp.json()["id"]


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("사용법: python ig_post.py <image_url> <caption>")
        sys.exit(1)
    post_id = post_image(sys.argv[1], sys.argv[2])
    print(f"게시 완료: {post_id}")
