"""Instagram 로그인 기반 토큰이 유효하고 발행 가능한 계정인지 확인한다."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["IG_ACCESS_TOKEN"]
IG_USER_ID = os.environ["IG_BUSINESS_ACCOUNT_ID"]


def main():
    r = requests.get(f"https://graph.instagram.com/v21.0/{IG_USER_ID}", params={
        "fields": "id,username,account_type",
        "access_token": TOKEN,
    }).json()
    print(r)
    if r.get("account_type") == "BUSINESS":
        print("✅ 비즈니스 계정 확인, 발행 가능")


if __name__ == "__main__":
    main()
