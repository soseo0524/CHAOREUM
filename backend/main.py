from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from errors import ApiError, api_error_handler
from routers import admin, charge_requests, me, parking_zones, vehicles
import asyncio

from config import settings

import models  # noqa: F401  (테이블 등록)
import repo
import ws as ws_router
from database import SessionLocal, engine, init_dev_db, migrate_db
from seed import seed_dev
from services import apply_central_status, vehicle_status
from state import dispatch, hub, ros, runtime

app = FastAPI(title="AIOT API")
if settings.cors_origins:  # 관리자 웹(브라우저)에서 호출. 비어 있으면 CORS 미허용
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
app.add_exception_handler(ApiError, api_error_handler)


async def _validation_handler(_: Request, exc: RequestValidationError):
    errs = [{"loc": [str(x) for x in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": "입력값이 올바르지 않습니다.", "details": {"errors": errs}})


app.add_exception_handler(RequestValidationError, _validation_handler)
for r in (me.router, vehicles.router, charge_requests.router, parking_zones.router, admin.router, ws_router.router):
    app.include_router(r)
if settings.ros_mode == "mock":  # 실제 관제가 없을 때 앱 개발용
    from routers import dev

    app.include_router(dev.router)


if engine.dialect.name == "sqlite":  # 개발 모드: 테이블·시드를 자동 생성. 운영(Postgres)은 Alembic으로만 만든다
    init_dev_db()
    with SessionLocal() as _db:
        seed_dev(_db)
else:  # 운영: 켜질 때 마이그레이션(새 리비전이 있으면 적용, 최신이면 그대로)
    migrate_db()


def _on_central(msg):
    """ROS 스레드에서 호출된다. 자체 세션으로 반영 후 변경된 차량을 WS로 방송."""
    with SessionLocal() as db:
        outbox: list = []
        changed = apply_central_status(db, msg, runtime, outbox)
        db.commit()
        payloads = []
        dispatch(db, outbox)
        for vid in changed:
            v = repo.live_vehicle(db, vid)
            if v:
                payloads.append((v.owner_id, {"type": "vehicle_status", "data": vehicle_status(db, v).model_dump(mode="json")}))
    if hub.loop and not hub.loop.is_closed() and hub.clients:
        for owner, payload in payloads:
            asyncio.run_coroutine_threadsafe(hub.send_vehicle(owner, payload), hub.loop)


ros.on_central_status(_on_central)


@app.get("/health")
def health():
    return {"ok": True}
