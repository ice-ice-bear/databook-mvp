# Databook 로컬 MVP

가상 데이터 추출 → **MariaDB 적재 → SQL 가공·이력 누적 → 날짜별 신규 Excel 생성**을 한 명령으로 실행합니다. 기존 운영 DB를 교체하거나 변경하지 않습니다.

현재 구현은 가상 데이터를 사용하는 1차 자동화 검증 범위입니다. 실제 Adobe API, 기존 DB 스키마와 대시보드, LLM·Word·질문 UI는 아직 연결하지 않았습니다.

## 바로 실행

필수: Docker Desktop 실행, Docker Compose, `make`.

```sh
git clone https://github.com/ice-ice-bear/databook-mvp.git
cd databook-mvp
make demo
```

전용 MariaDB 컨테이너를 시작하고 테스트 테이블을 만든 후, 기존에 준비한 가상 CSV에서 2026-09-27과 전주 동일 요일을 조회해 다음 파일을 생성합니다.

```text
reports/daily_report_2026-09-27.xlsx
reports/daily_report_2026-09-27.json
logs/<실행ID>.json
```

Excel의 `일일 보고서`에는 KPI와 채널별 매출 비교, `조회 데이터`에는 실제 계산에 사용한 30행이 들어갑니다. 9월 27일 매출 22,273,572원, 비교일 24,079,860원이 검증 기준입니다. 이 값은 가상 수치입니다. `.json`에는 원본 해시·SQL 해시·실행 ID와 계산 결과가 기록됩니다.

Docker DB는 외부 포트를 공개하지 않으며 이 프로젝트 전용 볼륨을 사용합니다. 예제 DB 비밀번호는 로컬 데모 전용입니다. 실제 환경에 그대로 사용하지 마세요.

## 날짜 지정과 재생성

```sh
make report DATE=2026-09-26
make regenerate DATE=2026-09-27
```

- 동일 입력으로 다시 실행하면 기존 성공 보고서를 반환합니다.
- `regenerate`는 `_v2.xlsx`, `_v3.xlsx`처럼 새 파일을 만들고 이전 파일을 보존합니다.
- 입력 CSV·SQL·접속 DB가 변경됐는데 재생성 옵션이 없으면 명시적으로 실패합니다.
- `data/adobe_mock_daily.csv` 범위는 2026-06-30~2026-09-27입니다. 전주 동일 요일도 필요하므로 해당 CSV로 생성할 수 있는 보고일은 2026-07-07~2026-09-27입니다.
- CSV는 정확한 날짜 × 5채널 × 3디바이스 조합을 요구합니다. 누락 행을 0으로 채우지 않습니다. 실제 Adobe 연결 때는 실제 차원·누락 의미에 맞춰 이 계약을 수정해야 합니다.

매일 바뀌는 날짜로 로컬 테스트하려면 CSV 대신 결정적인 가상 데이터 생성기를 사용합니다. `--date` 생략 시 한국 시간 기준 어제이며 API 키는 필요 없습니다.

```sh
docker compose -f compose.yaml -f compose.demo.yaml run --rm worker run
```

같은 날짜에 CSV 보고서가 이미 있다면 데이터 모드 변경이므로 `--regenerate`가 필요합니다. 어느 입력을 썼는지는 Excel 상단과 실행 결과에 표시됩니다.

## 검증

```sh
make test
```

실제 데모 MariaDB를 사용해 적재·SQL 집계·Excel 수치, 입력 누락·중복·음수 거부, 0분모, 동일 요청 재사용, 새 버전 생성, 동시 실행 잠금, 파일 생성 실패 시 DB 롤백과 이전 파일 보존을 확인합니다. 테스트는 데모 DB의 2026-09-20·27일 데이터에만 쓰므로 운영 DB에서 실행하지 않습니다.

## 로컬 예약 실행

macOS에서는 Python 내부 스케줄러나 Airflow 대신 launchd로 동일 명령을 호출합니다.

```sh
make schedule
plutil -lint work/local.databook-mvp.daily.plist
```

이 명령은 설정 파일만 만듭니다. **기본 상태에서는 예약 실행을 등록하지 않습니다.** 활성화하려면 다음을 실행합니다.

```sh
launchctl bootstrap "gui/$(id -u)" "$PWD/work/local.databook-mvp.daily.plist"
```

매일 Mac의 시스템 시간대 기준 09:00에 어제(KST)의 **가상 데이터 보고서**를 생성합니다. 한국 시각 09:00을 원하면 Mac 시간대가 Asia/Seoul인지 확인하세요. Docker Desktop이 실행 중이고 `make demo`로 초기화가 끝나 있어야 합니다.

등록한 작업을 즉시 시험하거나 해제할 때:

```sh
launchctl kickstart "gui/$(id -u)/local.databook-mvp.daily"
launchctl bootout "gui/$(id -u)/local.databook-mvp.daily"
```

로그는 `logs/schedule.out.log`, `logs/schedule.err.log`에 남습니다. 꺼진 PC·종료된 Docker에서 실행을 보장하지 않습니다. 누락 날짜는 `--date`로 재실행합니다. 자동 과거 보충은 아직 없습니다. Linux·Windows에서는 같은 Compose 명령을 cron/systemd 또는 작업 스케줄러에 등록하면 됩니다.

## 기존 호스트 MariaDB로 전환

기본 `compose.yaml`은 `host.docker.internal`을 통해 호스트 DB에 연결합니다. `compose.demo.yaml`은 독립 로컬 검증을 위한 선택적 덮어쓰기 설정입니다. **실제 DB에 연결할 때도 demo overlay를 함께 쓰면 계속 데모 DB에 접속하므로 주의하세요.**

1. 기존 서버에서 사용해도 되는 테스트 DB와 계정을 지정합니다. 이 MVP는 실수 방지를 위해 `databook_mvp_*` 테스트 DB 이름만 허용합니다. 프로그램은 DB나 계정을 자동 생성하지 않습니다.
2. `.env.example`을 `.env`로 복사하고 테스트 접속값을 입력합니다. `.env`는 Git과 Docker 이미지에서 제외됩니다.
3. 운영 테이블에 연결하기 전 기존 스키마·SQL 매핑을 구현해야 합니다. 현재 `sql/schema.sql`은 테스트 테이블 2개뿐이며 원래 시스템의 축소·대체 스키마가 아닙니다.

```sh
cp .env.example .env
# .env에 지정된 테스트 DB 접속 정보를 입력한 후 실행
docker compose build worker
docker compose run --rm worker init-db
docker compose run --rm worker run --date 2026-09-27 --csv data/adobe_mock_daily.csv
```

`init-db`는 지정된 테스트 DB에 `mvp_raw_daily`, `mvp_history_daily`만 만듭니다. 일반 실행은 DDL을 실행하지 않습니다. 기존 DB의 테이블을 삭제·이름 변경하거나 새 DB 제품으로 옮기지 않습니다. Docker Desktop에서 호스트의 접근 허용 포트·DB 계정의 접속 허용 범위는 별도로 확인해야 합니다.

## 최소 운영 규칙

- MariaDB 이름 잠금으로 예약·수동 실행을 직렬화합니다. 잠금을 확보하지 못하면 실패 기록을 남기고 종료합니다.
- 대상 두 날짜의 원천 교체와 history 집계는 InnoDB 트랜잭션 하나로 처리합니다. Excel 임시 파일 생성까지 실패하면 롤백합니다.
- DB 커밋과 파일 공개를 하나의 원자적 트랜잭션으로 만들지는 않습니다. 커밋 후 파일 공개가 실패하면 해당 날짜를 재실행해 복구합니다. DB에는 중복 없이 다시 적재되며 기존 보고서는 보존됩니다.
- 완성된 임시 파일만 새 이름으로 공개합니다. 이미 존재하는 보고서는 덮어쓰지 않습니다. 비정상 종료로 임시 파일이 남으면 `.report-*`만 정리할 수 있습니다.
- JSON 로그에는 단계·상태·오류 종류를 기록합니다. 실행 중 프로세스가 강제 종료되면 `running` 기록이 남을 수 있으며 재실행할 수 있습니다. 자동 재시도·자동 상태 정리는 아직 없습니다.
- 수치 계산은 SQL·Python으로 처리합니다. 사람 기준 순방문자·전환율을 만들어내지 않으며 가상 방문의 합산 가정을 실제 AA 데이터에 적용하지 않습니다.

## 구조

```text
pipeline.py           추출·검증·잠금·트랜잭션·보고서·CLI
sql/schema.sql        데모 테이블 2개 (init-db 전용)
sql/transform.sql     원천을 채널별 history로 집계
data/                 기존 90일 가상 CSV
compose.yaml          호스트 MariaDB에 연결하는 worker
compose.demo.yaml     독립 MariaDB 테스트 환경
test_pipeline.py      실제 MariaDB를 사용하는 통합 확인
schedule.py           macOS 예약 실행 설정 생성
```

사용을 마치면 `make stop`으로 데모 DB만 중지합니다. 데이터 볼륨은 보존됩니다. 실제 Adobe API와 LLM을 쓰기 전까지 개인 API 키는 필요 없습니다.
