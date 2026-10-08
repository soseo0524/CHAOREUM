"""개발·테스트용 시드. 운영은 fleet_locations.yaml과 같은 값을 DB에 직접 넣어야 한다(좌표는 임시값)."""
from sqlalchemy import func, select

import models as m
from schemas.common import ParkingZoneKind
from schemas.parking_map import ALL_SEAT_NUMBERS, seat_zone_id


def sync_parking_zones(db) -> None:
    """주차 자리 57칸(PARKING_00~65, 12·14·27·30·31·34·35·39·44번 제외)을 DB와 맞춘다. 반복 실행해도 안전하다.
    없는 자리는 만들고, 지도에 없는 옛 자리(예: 21칸 시절의 PARKING_14)는 요청·차량 위치가 가리키지 않을 때만 지운다."""
    want = {seat_zone_id(n): f"{n}번 자리" for n in ALL_SEAT_NUMBERS}  # 자리 하나에 차 한 대(capacity=1)
    have = {z.id: z for z in db.scalars(select(m.ParkingZone).where(m.ParkingZone.kind == ParkingZoneKind.PARKING))}
    for zid, name in want.items():
        if zid not in have:
            db.add(m.ParkingZone(id=zid, name=name, kind=ParkingZoneKind.PARKING, capacity=1, pose_x=0.0, pose_y=0.0, pose_yaw=0.0))
    for zid, z in have.items():
        if zid in want:
            continue
        used = db.scalar(select(func.count()).select_from(m.ChargeRequest).where(m.ChargeRequest.parking_zone_id == zid)) \
            or db.scalar(select(func.count()).select_from(m.VehicleStateRow).where(m.VehicleStateRow.zone_id == zid))
        if not used:
            db.delete(z)


def seed_dev(db):
    if not db.get(m.Charger, "CHARGER_01"):
        for i in (1, 2):
            db.add(m.Charger(id=f"CHARGER_0{i}", name=f"충전기 {i}", max_power_kw=11))
        for zid, name, kind in [("WAIT_01", "대기 구역", ParkingZoneKind.WAITING), ("CHARGE_01", "충전 구역", ParkingZoneKind.CHARGING)]:
            db.add(m.ParkingZone(id=zid, name=name, kind=kind, capacity=2, pose_x=0.0, pose_y=0.0, pose_yaw=0.0))
    sync_parking_zones(db)
    db.commit()


if __name__ == "__main__":  # 운영 DB(Postgres)에 충전기·주차 구역 기본 데이터를 넣는다: cd backend && python seed.py
    from database import SessionLocal

    with SessionLocal() as _db:
        seed_dev(_db)
        _db.commit()
    print("seed 완료(없는 자리만 추가하고, 지도에 없는 옛 자리는 안 쓰는 것만 지움)")
