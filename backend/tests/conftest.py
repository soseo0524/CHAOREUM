"""테스트는 항상 개발 모드(SQLite, 가짜 관제)로 돈다. backend/.env 의 운영 값(Supabase 등)이 섞이지 않게
config·database가 .env를 읽기 전에 환경변수를 고정한다(load_dotenv는 이미 있는 값을 덮어쓰지 않는다).

DB는 메모리가 아니라 임시 파일 SQLite: 메모리 DB는 연결 하나를 모든 스레드가 같이 써서, 게이트웨이 반영(별도 스레드) 중에
화면 조회가 끝나며 롤백하면 반영 중인 내용까지 사라진다(테스트가 가끔 실패하던 원인). 파일 DB는 스레드마다 연결이 따로다."""
import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(prefix="aiot-test-"), "test.db")
for k, v in {"AUTH_MODE": "dev", "ROS_MODE": "mock", "PUSH_MODE": "mock", "DATABASE_URL": f"sqlite:///{_db}", "SUPABASE_URL": "",
             "SUPABASE_SERVICE_ROLE_KEY": "", "SUPABASE_JWT_SECRET": "", "GATEWAY_TOKEN": "", "AUTO_ASSIGN_ROS_IDS": ""}.items():
    os.environ[k] = v
