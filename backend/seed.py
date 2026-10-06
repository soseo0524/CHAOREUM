"""개발·테스트용 시드. 운영은 fleet_locations.yaml과 같은 값을 DB에 직접 넣어야 한다(좌표는 임시값)."""
import models as m
from schemas.common import ParkingZoneKind


def seed_dev(db):
    if db.get(m.Charger, "CHARGER_01"):
        return
    for i in (1, 2):
        db.add(m.Charger(id=f"CHARGER_0{i}", name=f"충전기 {i}", max_power_kw=11))
    zones = [("WAIT_01", "대기 구역", ParkingZoneKind.WAITING), ("CHARGE_01", "충전 구역", ParkingZoneKind.CHARGING)]
    # 앱 지도의 자리 1~21번 = 주차 구역 PARKING_01~21. 자리 하나에 차 한 대(capacity=1).
    zones += [(f"PARKING_{n:02d}", f"{n}번 자리", ParkingZoneKind.PARKING) for n in range(1, 22)]
    for zid, name, kind in zones:
        db.add(m.ParkingZone(id=zid, name=name, kind=kind, capacity=1 if kind == ParkingZoneKind.PARKING else 2, pose_x=0.0, pose_y=0.0, pose_yaw=0.0))
    db.commit()


if __name__ == "__main__":  # 운영 DB(Postgres)에 충전기·주차 구역 기본 데이터를 넣는다: cd backend && python seed.py
    from database import SessionLocal

    with SessionLocal() as _db:
        seed_dev(_db)
        _db.commit()
    print("seed 완료(이미 있으면 건너뜀)")
