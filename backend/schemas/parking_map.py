"""주차 구역(A·B·C) 지도 — 전체 지도(02.02)와 구역 안 맵(02.03·02-A.02·02-A.03)용.

흐름: 전체 지도에서 구역(area)을 고른다 → 구역 안에서 자리를 고른다 → 고른 자리의 zone_id(PARKING_nn)를 충전 요청에 넣는다.
- 구역(area) A = 1~7번, B = 8~14번, C = 15~21번. 번호 n의 자리 = 주차 구역 PARKING_nn (capacity 1, 한 자리에 차 한 대).
- 구역 안 맵은 두 줄: 윗줄 4자리(col 0~3), 아랫줄 3자리(col 0~2)와 입구 칸(row 1, col 3).
"""
from __future__ import annotations

from pydantic import Field

from .common import ApiModel, StrEnum

# 구역 → (첫 번호, 끝 번호)
AREAS: dict[str, tuple[int, int]] = {"A": (1, 7), "B": (8, 14), "C": (15, 21)}
DETAIL_COLS = 4  # 구역 안 맵 한 줄에 놓는 자리 수


class SeatState(StrEnum):
    TAKEN = "TAKEN"  # 이미 차 있음/남이 선정(어두운 회색+차, 선택 불가. 02-A.02에서는 빨강)
    FREE = "FREE"  # 선택 가능(밝은 회색)
    MINE = "MINE"  # 내가 고른 자리 또는 내 차가 있는 자리(#68D2C3)


class AreaState(StrEnum):
    OPEN = "OPEN"  # 빈자리 있음
    FULL = "FULL"  # 가득 참(02-A.03). 들어가기 버튼을 막는다


class Seat(ApiModel):
    seat_no: int = Field(ge=1, description="지도에 표시되는 번호")
    zone_id: str = Field(description="PARKING_nn. 충전 요청의 parking_zone_id에 그대로 쓴다")
    state: SeatState


class AreaSummary(ApiModel):
    area_id: str = Field(description="A, B, C")
    name: str = Field(description="A구역")
    seat_total: int
    free_count: int = Field(ge=0, description="빈자리 수(화면의 '빈자리 4 / 7')")
    state: AreaState
    has_mine: bool = Field(description="내 자리(고른 자리·주차한 자리)가 이 구역에 있으면 true")
    seats: list[Seat] = Field(description="구역 카드의 미니 현황용. 번호 순서")


class AreasOut(ApiModel):
    """GET /parking-zones/areas — 전체 지도(02.02). 지도 확대·이동은 앱이 처리하고, 서버는 구역별 현황만 준다."""

    areas: list[AreaSummary]


class DetailSeat(Seat):
    row: int = Field(ge=0, description="0=윗줄, 1=아랫줄")
    col: int = Field(ge=0)


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
    rows: int = Field(description="줄 수(2)")
    cols: int = Field(description="한 줄 칸 수(4)")
    entrance: Cell = Field(description="입구 칸 위치")
    seats: list[DetailSeat]
    selected_zone_id: str | None = Field(None, description="요청에 담아 보낸 고른 자리")
    selected_ok: bool | None = Field(None, description="고를 수 있으면 true, 이미 선정됐으면 false(02-A.02). selected를 안 보내면 null")
