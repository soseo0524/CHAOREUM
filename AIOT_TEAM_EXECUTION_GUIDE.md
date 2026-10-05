# AIoT EV 충전 중앙관제 팀 실행 가이드

> 팀원이 프로젝트를 내려받은 뒤 실행하고 정상 동작을 확인하기 위한 문서  
> 기준 환경: Ubuntu 22.04, ROS 2 Humble, Python 3.10  
> 기준 워크스페이스: `~/aiot_ws`  
> Qwen 실행 환경: `qwen-control`

## 1. 실행 구성

현재 시스템은 한 대의 PC에서 다음 네 프로세스를 실행한다.

| 터미널 | 실행 항목 | 역할 | 포트 |
| --- | --- | --- | --- |
| 1 | Qwen 서버 | 충전 우선 차량 결정 | `8000` |
| 2 | ROS 2 중앙관제 파이프라인 | 차량 상태 생성, 작업 배차, 이동·충전 모사 | ROS 2 DDS |
| 3 | rosbridge | ROS 2 데이터를 웹 대시보드에 전달 | `9090` |
| 4 | 대시보드 HTTP 서버 | 웹 화면 제공 | `8080` |

ROS launch에서 실행되는 노드는 다음과 같다.

| 노드 | 역할 |
| --- | --- |
| `vehicle_simulator_node` | EV01~EV03의 SOC와 차량 상태 생성 |
| `central_control_node` | 상태 관리, Qwen 호출, 작업 및 충전 명령 발행 |
| `vehicle_task_manager_ev01` | EV01의 이동을 5초 타이머로 모사 |
| `vehicle_task_manager_ev02` | EV02의 이동을 6초 타이머로 모사 |
| `vehicle_task_manager_ev03` | EV03의 이동을 7초 타이머로 모사 |
| `charging_simulator_node` | 충전 진행, SOC 증가 및 충전 완료 모사 |

> 현재 차량 이동은 실제 Nav2나 차량 플래너가 아니라 타이머로 모사한다.

## 2. 최초 1회 준비

이미 설치와 빌드가 끝난 PC라면 이 장을 건너뛰고 [3. 실행 절차](#3-실행-절차)부터 진행한다.

### 2.1 ROS 2 환경 확인

```bash
source /opt/ros/humble/setup.bash
ros2 --help
```

ROS 2 명령어 도움말이 출력되면 정상이다.

### 2.2 필요한 패키지 설치

```bash
sudo apt update
sudo apt install -y \
  ros-humble-rosbridge-server \
  python3-colcon-common-extensions \
  python3-requests
```

패키지 의존성 설치:

```bash
cd ~/aiot_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
```

### 2.3 주요 파일 확인

```bash
test -f ~/aiot_ws/qwen_server/qwen_server.py && echo "Qwen server OK"
test -f ~/aiot_ws/src/aiot_central_control/launch/central_control.launch.py && echo "Launch OK"
test -f ~/aiot_ws/src/aiot_central_control/config/fleet_locations.yaml && echo "Goal config OK"
test -f ~/aiot_ws/dashboard/index.html && echo "Dashboard OK"
```

네 항목 모두 `OK`가 출력되어야 한다.

### 2.4 Qwen 환경 확인

```bash
conda activate qwen-control
python -c "import torch, transformers, accelerate, bitsandbytes, fastapi, uvicorn; print('qwen-control OK')"
```

`qwen-control OK`가 출력되어야 한다. import 오류가 발생하면 누락된 패키지를 먼저 설치한다.

### 2.5 ROS 2 패키지 빌드

ROS 2 빌드는 Conda 환경을 비활성화한 상태에서 진행한다.

```bash
conda deactivate 2>/dev/null || true
cd ~/aiot_ws
source /opt/ros/humble/setup.bash

colcon build \
  --packages-select aiot_central_control \
  --symlink-install

source ~/aiot_ws/install/setup.bash
```

빌드 결과 확인:

```bash
ros2 pkg executables aiot_central_control
```

## 3. 실행 절차

총 4개의 터미널을 열고 아래 순서대로 실행한다. 각 프로세스가 정상적으로 시작된 것을 확인한 후 다음 터미널로 넘어간다.

### 3.1 터미널 1 — Qwen 서버

```bash
conda activate qwen-control
cd ~/aiot_ws/qwen_server
python -m uvicorn qwen_server:app --host 127.0.0.1 --port 8000
```

정상 로그 예시:

```text
Loading Qwen3.5-4B 4-bit...
Qwen loaded.
Uvicorn running on http://127.0.0.1:8000
```

별도 터미널에서 서버 상태를 확인한다.

```bash
curl -i http://127.0.0.1:8000/health
```

HTTP 상태 코드 `200 OK`가 나오면 다음 단계로 이동한다.

### 3.2 터미널 2 — ROS 2 중앙관제 파이프라인

```bash
conda deactivate 2>/dev/null || true
source /opt/ros/humble/setup.bash
source ~/aiot_ws/install/setup.bash

ros2 launch aiot_central_control central_control.launch.py
```

이 launch가 차량 시뮬레이터, 충전 시뮬레이터, EV01~EV03 Task Manager와 중앙관제 노드를 모두 실행한다.

> 차량별 Task Manager를 별도로 실행하지 않는다. 중복 실행하면 동일한 작업 상태가 두 번씩 발행된다.

### 3.3 터미널 3 — rosbridge

```bash
conda deactivate 2>/dev/null || true
source /opt/ros/humble/setup.bash
source ~/aiot_ws/install/setup.bash

ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

다음 로그가 나오면 정상이다.

```text
Rosbridge WebSocket server started on port 9090
```

### 3.4 터미널 4 — 대시보드 HTTP 서버

```bash
cd ~/aiot_ws/dashboard
python3 -m http.server 8080 --bind 127.0.0.1
```

Chrome에서 다음 주소를 연다.

```text
http://127.0.0.1:8080/
```

화면에 `ROS2 연결됨`이 표시되고 차량 SOC와 이벤트가 갱신되면 정상이다. `/favicon.ico`의 `404` 로그는 기능과 무관하다.

## 4. 정상 동작 확인

새 터미널에서 ROS 2 환경을 설정한다.

```bash
conda deactivate 2>/dev/null || true
source /opt/ros/humble/setup.bash
source ~/aiot_ws/install/setup.bash
```

### 4.1 노드 확인

```bash
ros2 node list | sort
```

최소한 다음 노드가 보여야 한다.

```text
/central_control_node
/charging_simulator_node
/vehicle_simulator_node
/vehicle_task_manager_ev01
/vehicle_task_manager_ev02
/vehicle_task_manager_ev03
```

### 4.2 중앙 상태 확인

```bash
ros2 topic echo /central_status --once --full-length
```

발행 주기 확인:

```bash
ros2 topic hz /central_status
```

약 `1 Hz`로 발행되면 정상이다.

### 4.3 작업 처리 흐름 확인

아래 토픽을 각각 별도 터미널에서 확인하면 전체 흐름을 볼 수 있다.

```bash
ros2 topic echo /vehicle_task --full-length
```

```bash
ros2 topic echo /vehicle_task_status --full-length
```

```bash
ros2 topic echo /vehicle_command --full-length
```

```bash
ros2 topic echo /charging_status --full-length
```

정상 처리 순서는 다음과 같다.

1. `/vehicle_task`에 충전기로 이동할 차량과 목표 좌표가 발행된다.
2. `/vehicle_task_status`에 `ACCEPTED`가 발행된다.
3. `MOVING_TO_CHARGER`와 이동 진행률이 발행된다.
4. 이동 모사 시간이 지나면 `ARRIVED_AT_CHARGER`가 발행된다.
5. `/vehicle_command`에 `START_CHARGING`이 발행된다.
6. `/charging_status`에서 SOC가 증가한다.
7. `CHARGE_COMPLETE` 후 충전기가 다시 `AVAILABLE` 상태가 된다.

## 5. 목표 좌표 변경

목표 좌표 설정 파일:

```text
~/aiot_ws/src/aiot_central_control/config/fleet_locations.yaml
```

좌표는 `[x, y, yaw]` 형식이며 `yaw`의 단위는 rad이다. 파일을 수정한 뒤 다시 빌드하고 launch를 재시작한다.

```bash
cd ~/aiot_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select aiot_central_control --symlink-install
source ~/aiot_ws/install/setup.bash
ros2 launch aiot_central_control central_control.launch.py
```

적용된 값 확인:

```bash
ros2 param get /central_control_node charger_01_pose
ros2 param get /central_control_node ev01_parking_pose
```

## 6. 종료 순서

각 실행 터미널에서 `Ctrl+C`를 눌러 다음 순서로 종료한다.

1. 대시보드 HTTP 서버
2. rosbridge
3. ROS 2 중앙관제 launch
4. Qwen 서버

## 7. 자주 발생하는 문제

### 7.1 Qwen 서버에서 `Attribute "app" not found`

`qwen_server.py`가 있는 디렉터리에서 uvicorn을 실행해야 한다.

```bash
cd ~/aiot_ws/qwen_server
python -c "import qwen_server; print(qwen_server.__file__); print(hasattr(qwen_server, 'app'))"
python -m uvicorn qwen_server:app --host 127.0.0.1 --port 8000
```

마지막 확인값이 `True`여야 한다.

### 7.2 중앙관제에서 Qwen `Connection refused`

```bash
ss -ltnp | grep ':8000'
curl -i http://127.0.0.1:8000/health
```

Qwen 서버가 중단되어도 중앙관제는 규칙 기반 `RULE_FALLBACK`으로 계속 동작한다.

### 7.3 `/central_status`가 발행되지 않음

```bash
ros2 topic list | grep central_status
ros2 topic info /central_status -v
ros2 node info /central_control_node
ros2 topic hz /central_status
```

코드를 수정했다면 다시 빌드하고 `install/setup.bash`를 source한 뒤 launch를 재시작한다.

### 7.4 Task 상태가 두 번씩 발행됨

```bash
ros2 node list | grep vehicle_task_manager
ps -ef | grep '[v]ehicle_task_manager_node'
```

launch와 별도로 실행한 Task Manager가 있다면 해당 터미널에서 `Ctrl+C`로 종료한다.

### 7.5 대시보드에 데이터가 표시되지 않음

```bash
ros2 topic echo /central_status --once --full-length
ss -ltnp | grep ':9090'
ss -ltnp | grep ':8080'
```

대시보드의 rosbridge 주소는 로컬 실행 기준 `ws://127.0.0.1:9090`이어야 한다.

## 8. 실행 전 최종 체크리스트

- [ ] `qwen-control` 환경에서 Qwen 패키지 import 성공
- [ ] ROS 2 패키지 빌드 완료
- [ ] Qwen `/health` 응답 `200 OK`
- [ ] 중앙관제 launch 실행 완료
- [ ] rosbridge의 `9090` 포트 실행 확인
- [ ] 대시보드의 `8080` 포트 실행 확인
- [ ] `/central_status` 약 1 Hz 발행 확인
- [ ] 대시보드에서 SOC와 이벤트 변화 확인

위 항목이 모두 확인되면 팀원이 전체 중앙관제·Qwen·충전 시뮬레이션 파이프라인을 정상적으로 실행한 상태다.
