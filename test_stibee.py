"""스티비 API 연결 테스트 및 발송"""
import sys
sys.path.insert(0, '.')

from stibee_integration import StibeeClient

# 1) 인증 테스트
client = StibeeClient()
print("=== AUTH CHECK ===")
client.check_auth()

# 2) 주소록 조회
print("\n=== LIST CHECK ===")
lists = client.get_lists()
if lists:
    for l in lists:
        lid = l.get("listId", l.get("id", "?"))
        name = l.get("name", "?")
        print(f"  ID: {lid}  Name: {name}")
else:
    print("  주소록 조회 불가 (스탠다드 요금제이거나 데이터 없음)")
    print("  스티비 웹에서 직접 주소록 ID 확인 필요")
