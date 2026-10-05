"""GET /parking-zones/map — 1인칭(운전석 시점) 주차 지도 화면(4·4-1·4-2·5)용.

지도는 길 양옆에 주차 칸이 마주 보는 구조다. 한 '줄(row)'에 왼쪽·오른쪽 칸이 하나씩 있다.
왼쪽 칸 번호 = 10 - row, 오른쪽 칸 번호 = 11 + row (row 0이 입구 쪽 가장 가까운 줄).
번호 n의 칸 = 주차 구역 PARKING_nn (capacity 1, 칸 하나에 차 한 대). 21번은 맨 끝 줄의 오른쪽에만 있다.
앱은 사용자가 화면을 앞뒤로 끌 때마다 row를 바꿔 이 API를 다시 부르거나, depth를 크게 받아 한 번에 그린다.
"""
from __future__ import annotations

from pydantic import Field

from .common import ApiModel, StrEnum


class SeatState(StrEnum):
    TAKEN = "TAKEN"  # 이미 차 있음/남이 선정(어두운 회색, 선택 불가. 4-1에서는 빨강)
    FREE = "FREE"  # 선택 가능(밝은 회색)
    MINE = "MINE"  # 내가 고른 자리 또는 내 차가 있는 자리(#68D2C3)


class Seat(ApiModel):
    seat_no: int = Field(ge=1, description="지도에 표시되는 번호")
    zone_id: str = Field(description="PARKING_nn. 충전 요청의 parking_zone_id에 그대로 쓴다")
    state: SeatState


class MapRow(ApiModel):
    row: int = Field(ge=0)
    left: Seat | None = None
    right: Seat | None = None


class ParkingMapOut(ApiModel):
    row: int = Field(ge=0, description="내 위치(맨 앞 줄). 요청값을 범위 안으로 맞춘 값")
    depth: int = Field(ge=1, description="앞쪽으로 몇 줄을 돌려주는지")
    total_rows: int = Field(ge=1, description="전체 줄 수. 앱이 드래그 범위를 정할 때 사용")
    rows: list[MapRow]
    selected_zone_id: str | None = Field(None, description="요청에 담아 보낸 고른 자리. 이미 TAKEN이면 selected_ok=false")
    selected_ok: bool | None = Field(None, description="selected 자리를 고를 수 있으면 true, 이미 선정됐으면 false(4-1)")
