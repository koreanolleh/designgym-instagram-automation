"""Instagram Graph API로 이미지 1~10장을 게시한다 (1장=단일 게시물, 2장 이상=캐러셀)."""
import os
import time
import requests

GRAPH_VERSION = "v21.0"
# Instagram 로그인 기반 토큰(IGAA...)은 graph.facebook.com이 아니라 graph.instagram.com을 사용한다.
GRAPH_HOST = "https://graph.instagram.com"


def _wait_until_finished(base: str, container_id: str, token: str):
    for _ in range(20):
        status = requests.get(f"{base}/{container_id}", params={
            "fields": "status_code",
            "access_token": token,
        }).json()
        if status.get("status_code") == "FINISHED":
            return
        if status.get("status_code") == "ERROR":
            raise RuntimeError(f"컨테이너 처리 실패: {status}")
        time.sleep(3)


def post_images(image_urls: list, caption: str) -> str:
    token = os.environ["IG_ACCESS_TOKEN"]
    ig_user_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    account_base = f"{GRAPH_HOST}/{GRAPH_VERSION}/{ig_user_id}"
    node_base = f"{GRAPH_HOST}/{GRAPH_VERSION}"

    if len(image_urls) == 1:
        create_resp = requests.post(f"{account_base}/media", data={
            "image_url": image_urls[0],
            "caption": caption,
            "access_token": token,
        })
        create_resp.raise_for_status()
        creation_id = create_resp.json()["id"]
        _wait_until_finished(node_base, creation_id, token)
    else:
        # 캐러셀: 자식 컨테이너(is_carousel_item=true, 캡션 없음)를 먼저 만들고
        # 부모 컨테이너(media_type=CAROUSEL)에 children으로 묶는다.
        child_ids = []
        for url in image_urls:
            child_resp = requests.post(f"{account_base}/media", data={
                "image_url": url,
                "is_carousel_item": "true",
                "access_token": token,
            })
            child_resp.raise_for_status()
            child_id = child_resp.json()["id"]
            _wait_until_finished(node_base, child_id, token)
            child_ids.append(child_id)

        carousel_resp = requests.post(f"{account_base}/media", data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": token,
        })
        carousel_resp.raise_for_status()
        creation_id = carousel_resp.json()["id"]
        _wait_until_finished(node_base, creation_id, token)

    publish_resp = requests.post(f"{account_base}/media_publish", data={
        "creation_id": creation_id,
        "access_token": token,
    })
    publish_resp.raise_for_status()
    return publish_resp.json()["id"]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("사용법: python ig_post.py <caption> <image_url1> [image_url2 ...]")
        sys.exit(1)
    caption = sys.argv[1]
    urls = sys.argv[2:]
    post_id = post_images(urls, caption)
    print(f"게시 완료: {post_id}")
