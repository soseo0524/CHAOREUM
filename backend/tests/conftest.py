"""테스트는 항상 개발 모드(메모리 SQLite, 가짜 관제)로 돈다. backend/.env 의 운영 값(Supabase 등)이 섞이지 않게
config·database가 .env를 읽기 전에 환경변수를 고정한다(load_dotenv는 이미 있는 값을 덮어쓰지 않는다)."""
import os

for k, v in {"AUTH_MODE": "dev", "ROS_MODE": "mock", "PUSH_MODE": "mock", "DATABASE_URL": "", "SUPABASE_URL": "",
             "SUPABASE_SERVICE_ROLE_KEY": "", "SUPABASE_JWT_SECRET": "", "GATEWAY_TOKEN": ""}.items():
    os.environ[k] = v
