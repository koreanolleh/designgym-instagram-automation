"""메타 토큰이 인스타 발행에 필요한 권한/자산을 갖췄는지 확인한다."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["IG_ACCESS_TOKEN"]
PAGE_ID = os.environ.get("FB_PAGE_ID", "1172548162600731")  # 디자인짐 FB 페이지


def main():
    print("--- 토큰 권한(scopes) ---")
    r = requests.get("https://graph.facebook.com/v19.0/debug_token", params={
        "input_token": TOKEN, "access_token": TOKEN,
    }).json()
    scopes = r.get("data", {}).get("scopes", [])
    print(scopes)
    for needed in ["instagram_basic", "instagram_content_publish"]:
        print(f"  {'✅' if needed in scopes else '❌'} {needed}")

    print("\n--- 페이지에 연결된 인스타 비즈니스 계정 ---")
    r = requests.get(f"https://graph.facebook.com/v19.0/{PAGE_ID}", params={
        "fields": "instagram_business_account,name", "access_token": TOKEN,
    }).json()
    print(r)


if __name__ == "__main__":
    main()
