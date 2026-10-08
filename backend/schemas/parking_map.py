"""주차 구역(A·B·C) 지도 — 전체 지도(02.02)와 구역 안 맵(02.03·02-A.02·02-A.03)용.

흐름: 전체 지도에서 구역(area)을 고른다 → 구역 안에서 자리를 고른다 → 고른 자리의 zone_id(PARKING_nn)를 충전 요청에 넣는다.
- 자리 번호는 실제 주차장 슬롯 번호 0~65다. 12·14·27·30·31·34·35·39·44번은 없어서 모두 57칸이다.
  번호 n의 자리 = 주차 구역 PARKING_nn(두 자리, 0 채움. 예: 0번=PARKING_00, 65번=PARKING_65). capacity 1, 한 자리에 차 한 대.
  중앙관제의 슬롯 번호와 같은 번호이므로 PARKING_nn의 nn이 곧 관제 슬롯 번호다.
- 구역(area) A = 위쪽 한 줄 17칸, B = 가운데 두 줄(13칸+13칸), C = 아래쪽 한 줄 14칸.
- 구역 안 맵의 칸 위치(row, col)는 실제 배치대로 줄마다 왼쪽→오른쪽 순서다. 입구 칸은 없다.
"""
from __future__ import annotations

import re

from pydantic import Field

from .common import ApiModel, StrEnum

# 구역 → 줄별 자리 번호(실제 주차장 배치, 윗줄부터, 줄 안에서는 왼쪽→오른쪽)
AREA_ROWS: dict[str, list[list[int]]] = {
    "A": [[61, 45, 43, 42, 40, 41, 38, 37, 36, 58, 33, 32, 59, 29, 28, 62, 26]],
    "B": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 60], [25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 13, 63]],
    "C": [[57, 56, 46, 47, 48, 49, 50, 51, 52, 53, 54, 65, 55, 64]],
}
ALL_SEAT_NUMBERS: list[int] = sorted(n for rows in AREA_ROWS.values() for row in rows for n in row)  # 57칸


def seat_zone_id(n: int) -> str:
    """자리 번호 → 주차 구역 id. 0 → PARKING_00, 65 → PARKING_65"""
    return f"PARKING_{n:02d}"


def seat_no_of(zone_id: str | None) -> int | None:
    """주차 구역 id → 자리 번호. PARKING_00 → 0. PARKING이 아니면 None"""
    m = re.fullmatch(r"PARKING_(\d+)", zone_id or "")
    return int(m.group(1)) if m else None


def area_seat_numbers(area_id: str) -> list[int]:
    """구역의 자리 번호. 줄 순서(윗줄 → 아랫줄), 줄 안에서는 왼쪽→오른쪽"""
    return [n for row in AREA_ROWS[area_id] for n in row]


class SeatState(StrEnum):
    TAKEN = "TAKEN"  # 이미 차 있음/남이 선정(어두운 회색+차, 선택 불가. 02-A.02에서는 빨강)
    FREE = "FREE"  # 선택 가능(밝은 회색)
    MINE = "MINE"  # 내가 고른 자리 또는 내 차가 있는 자리(#68D2C3)


class AreaState(StrEnum):
    OPEN = "OPEN"  # 빈자리 있음
    FULL = "FULL"  # 가득 참(02-A.03). 들어가기 버튼을 막는다


class Seat(ApiModel):
    seat_no: int = Field(ge=0, description="지도에 표시되는 번호(0~65)")
    zone_id: str = Field(description="PARKING_nn. 충전 요청의 parking_zone_id에 그대로 쓴다")
    state: SeatState


class AreaSummary(ApiModel):
    area_id: str = Field(description="A, B, C")
    name: str = Field(description="A구역")
    seat_total: int
    free_count: int = Field(ge=0, description="빈자리 수(화면의 '빈자리 8 / 17')")
    state: AreaState
    has_mine: bool = Field(description="내 자리(고른 자리·주차한 자리)가 이 구역에 있으면 true")
    seats: list[Seat] = Field(description="구역 카드의 미니 현황용. 실제 배치 순서(윗줄 → 아랫줄, 왼쪽→오른쪽)")


class AreasOut(ApiModel):
    """GET /parking-zones/areas — 전체 지도(02.02). 지도 확대·이동은 앱이 처리하고, 서버는 구역별 현황만 준다."""

    areas: list[AreaSummary]


class DetailSeat(Seat):
    row: int = Field(ge=0, description="0=윗줄, 1=아랫줄(B구역만 두 줄)")
    col: int = Field(ge=0, description="줄 안에서 왼쪽부터 0")


class Cell(ApiModel):
    row: int
    col: int


class AreaDetailOut(ApiModel):
    """GET /parking-zones/areas/{area_id} — 구역 안 맵(02.03, 02-A.02)."""

    area_id: str
    name: str
    seat_total: int
    free_count: int = Field(ge=0)
    state: AreaState
    rows: int = Field(description="줄 수(A=1, B=2, C=1)")
    cols: int = Field(description="가장 긴 줄의 칸 수(A=17, B=13, C=14)")
    entrance: Cell | None = Field(None, description="쓰지 않는다(입구 칸 없음). 옛 앱과의 호환용으로 항상 null")
    seats: list[DetailSeat]
    selected_zone_id: str | None = Field(None, description="요청에 담아 보낸 고른 자리")
    selected_ok: bool | None = Field(None, description="고를 수 있으면 true, 이미 선정됐으면 false(02-A.02). selected를 안 보내면 null")
