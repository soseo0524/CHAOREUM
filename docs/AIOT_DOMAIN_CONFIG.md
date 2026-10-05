# AIOT ROS 도메인 구성 (초안 — 확정 전)

기능 명세 5.4의 열린 질문을 풀기 위한 문서. 아래 표는 검토 의견의 예시이며 실제 배치 확정 시 고친다.

## 1. 도메인 배치 (안)

| 구성 | ROS_DOMAIN_ID |
| --- | ---: |
| Central Controller | 0 |
| FastAPI ROS Node | 0 |
| Charger Simulator | 0 |
| CAR_01 | 11 |
| CAR_02 | 12 |
| CAR_03 | 13 |
| CAR_04 | 14 |

## 2. Domain Bridge 계약 (안)

| Topic | From | To |
| --- | --- | --- |
| `/vehicle_task` | 0 | 11~14 |
| `/vehicle_task_status` | 11~14 | 0 |
| `/emergency_stop` | 0 | 11~14 |
| 차량 pose/state 관련 토픽 | 11~14 | 0 |

- FastAPI와 중앙관제가 같은 도메인(0)이면 `/charging/request`, `/central_status`는 Bridge를 통과하지 않는다.
- 토픽만 브리지한다(Action·Service 미사용). 메시지는 `vehicle_id`로 차량을 구분한다.

## 3. 확정할 것

- [ ] 도메인 개수와 노드·차량별 ROS_DOMAIN_ID
- [ ] Bridge로 넘길 토픽 최종 목록과 방향
- [ ] 차량별 토픽에 vehicle_id 필드를 넣을지, 토픽 이름에 넣을지
- [ ] `domain_bridge` 설정 파일 위치
