# Databook 로컬 MVP

가상 데이터 추출 → **MariaDB 적재 → SQL 가공·이력 누적 → 날짜별 신규 Excel 생성**을 한 명령으로 실행합니다. 기존 운영 DB를 교체하거나 변경하지 않습니다.

현재 구현은 로컬 검증 범위입니다. 보고서·데이터 질문·관리자 화면, 테이블 ER 탐색, 실행 검증 후 SQL 등록·수정, KST 요일별 예약, OneDrive 폴더 설정을 지원합니다. 데이터 수집은 가상 쇼핑몰 HTTP API 또는 Adobe Analytics 2.0이며 LLM은 OpenAI/Gemini를 선택할 수 있습니다. Adobe 인증·메타데이터 확인·일별 수집 어댑터는 구현되어 있지만 실제 계정 연결은 아직 검증하지 않았습니다. 기존 DB 스키마 매핑, 외부 대시보드와 Word는 후속 연동 범위입니다.

## 빠른 시작

Docker를 실행하고 uv를 설치한 뒤 저장소 폴더에서 실행합니다. 아래 명령은 macOS·Windows·Linux에서 동일합니다. `.env`가 이미 있으면 그대로 유지합니다.

```sh
uv sync --locked
uv run --locked python -c "from pathlib import Path; import shutil; Path('.env').exists() or shutil.copyfile('.env.example', '.env')"
docker compose -f compose.yaml -f compose.demo.yaml build worker example-api
docker compose -f compose.yaml -f compose.demo.yaml up -d --wait db example-api
docker compose -f compose.yaml -f compose.demo.yaml run --rm worker init-db
uv run --locked web.py
```

1. [보고서](http://127.0.0.1:8765/)에서 날짜를 선택해 첫 보고서를 생성합니다. 새 버전은 기존 Excel을 보존합니다.
2. [설정](http://127.0.0.1:8765/admin)에서 테이블 탐색, 분석 SQL 등록·수정, 다섯 파이프라인 SQL 편집을 사용합니다. 파이프라인 검증에는 이미 적재된 날짜를 선택하세요.
3. 같은 설정 화면에서 OneDrive 폴더, 실행 쿼리, KST 요일·시각을 저장합니다.
4. [데이터 분석](http://127.0.0.1:8765/questions)에서 적재된 데이터에 질문합니다. AI 기능에는 아래 LLM 설정이 필요하며, SQL 실행·편집·Excel 생성은 LLM 키 없이 테스트할 수 있습니다.

재실행은 Docker 서비스를 실행한 상태에서 `uv run --locked web.py`만 사용하면 됩니다. 개인 키는 `.env`, 웹 설정은 `work/`, 생성 파일은 `reports/`와 `logs/`에 남으며 모두 Git에서 제외합니다.

## 패키지 관리 (uv)

설치·실행은 모든 OS에서 uv로 관리합니다. uv가 없다면 [공식 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)를 먼저 따르세요.

```sh
uv sync --locked
```

- `pyproject.toml`: 직접 의존성과 지원 Python 버전. 현재 PyMySQL·openpyxl 두 가지입니다.
- `uv.lock`: 간접 의존성까지 고정하며 Git에 포함합니다. 직접 편집하지 않습니다.
- `.python-version`: 기본 실행 Python 3.12. 가상환경 `.venv`는 Git·Docker에서 제외합니다.
- 의존성 추가·삭제: `uv add 패키지`, `uv remove 패키지`. 잠금 파일도 함께 갱신합니다.
- Docker도 고정 uv 이미지로 `uv sync --locked`를 사용합니다. 별도 requirements.txt는 관리하지 않습니다.
- 한국어 SQL·HTML·JSON·로그는 UTF-8을 명시하고, 예약 날짜는 KST 고정 오프셋을 사용합니다.

참고: [uv 프로젝트 관리](https://docs.astral.sh/uv/guides/projects/), [Docker 통합](https://docs.astral.sh/uv/guides/integration/docker/).

## 로컬 웹 화면

```sh
make web
```

[http://127.0.0.1:8765](http://127.0.0.1:8765)에 접속합니다.
일일 보고서(`/`)와 데이터 질문(`/questions`) 화면을 상단 메뉴로 전환합니다.
보고서 화면에서 날짜 선택 → 생성 → AI 해석·지표 확인 → Excel 다운로드 순서로 사용합니다.
질문 화면에서는 기준일을 선택하고 자연어로 기간·필터·집계 방식을 요청합니다. AI가 해석한 실제 조건과 수치·SQL을 답변 아래에서 확인하세요.
새 날짜는 보고서를 먼저 생성해야 질문할 데이터가 적재됩니다. 질문에 따라 최대 31일의 기간·채널·디바이스 조건을 선택합니다.
새 버전 옵션을 끄면 동일 입력의 기존 보고서를 재사용합니다. SQL·LLM 설정이 바뀌면 새 버전 생성이 필요합니다.
생성 후 호스트에서 OneDrive 폴더로 Excel을 복사하며, 실패해도 보고서는 로컬에 남습니다.
현재 화면의 AI 분석 상태와 OneDrive 복사 결과를 구분해서 확인하세요.

질문에 사용할 채널·디바이스별 합계와 증감률도 SQL·코드에서 계산해 LLM에 전달합니다.
답변 아래 조회 수치와 SQL을 펼쳐 원본을 확인할 수 있습니다. AI 해석의 정확성은 별도 검토가 필요합니다.

화면은 로컬 127.0.0.1에만 바인딩합니다. API 키를 브라우저에 전달하지 않습니다.
한 번에 한 요청을 처리하며, 질문과 생성 버튼을 잠급니다. 질문마다 새 답변을 생성하고 대화 이력은 저장하지 않습니다.
이 서버는 로컬 MVP 전용입니다. 외부 서버에 공개하려면 사용자 인증과 배포 구성을 별도로 추가해야 합니다.
종료는 실행 터미널에서 Ctrl+C입니다. 이미 이미지를 빌드했다면 `uv run --locked web.py`로 바로 시작할 수 있습니다.
웹 서버가 실행 중이어야 사용할 수 있습니다. 관리자(`/admin`)에서 예약을 켜고 KST 시각을 저장합니다. 웹 서버·Docker의 재부팅 후 자동 시작은 등록하지 않았습니다.

## 관리자 SQL 조회 · 저장 쿼리

설정 화면에서 연결된 MariaDB의 테이블·컬럼을 확인하고 SELECT를 실행할 수 있습니다.
현재 연결 대상은 데모 DB입니다. Adobe는 아래 사전 설정으로 읽기 확인부터 시작하며, 기존 MariaDB 연결은 별도 매핑 작업입니다.

1. **테이블 탐색**의 ER 카드에서 컬럼·타입·PK/FK를 확인합니다. 테이블 또는 컬럼 이름으로 검색할 수 있으며 뷰도 표시합니다.
2. 테이블 이름을 클릭하면 실제 DB의 예시 최대 20행을 조회합니다. **SQL로 조회**는 편집기에 SELECT를 넣고, **이 테이블로 질문**은 질문 화면에 해당 테이블을 선택합니다.
3. **분석 SQL → 기본 분석 SQL**에서 기존 집계 테이블의 채널별 성과나 원본 테이블의 디바이스별 성과 SQL도 직접 확인·실행할 수 있습니다. 기본값은 `sql/analysis_queries.json`에서 관리하며 웹에서 이름·SQL을 수정하면 같은 ID의 기본 항목에 반영합니다. 변경 내용은 `work/queries.json`에 보관하며 질문·예약도 수정한 SQL을 사용합니다.
4. 이름·SQL·조회 날짜를 입력하고 **검증 후 등록** 또는 **검증 후 수정**합니다. 서버가 입력한 SQL을 DB에서 한 번 실행하고 성공한 경우에만 저장하며 결과를 표시합니다. 사전에 실행 버튼을 누르지 않아도 됩니다. SQL 오류·시간 초과 시 기존 항목과 설정 파일을 유지합니다. 조회 결과가 0행인 유효 SELECT도 저장할 수 있습니다. 저장 쿼리는 `work/queries.json`에 보관하며 Git에서 제외합니다.
5. 예약의 **실행 쿼리**에서 기본 분석/저장 SQL을 선택하고 저장하면 해당 요일에 전일 데이터를 수집·적재한 뒤 SQL 보고서를 만듭니다.
6. 데이터 분석의 **조회 쿼리**에서 기본 분석 SQL, 저장 SQL 또는 연결된 테이블을 선택해 질문할 수 있습니다. 테이블 직접 조회는 `report_date`가 날짜 타입이면 질문의 기간을 적용합니다. 그 외 날짜·필터·집계는 SQL로 작성해 저장합니다. 분석 입력이 200행을 넘으면 일부 결과라는 안내가 표시됩니다.
7. **일일 파이프라인 SQL**에서 `load_daily.sql`, `aggregate_daily.sql`, `transform.sql`, `validate_daily.sql`, `report_daily.sql`을 모두 직접 편집할 수 있습니다. **검증 실행**은 저장 없이 시험하며, **검증 후 적용**은 서버가 파이프라인을 한 번 실행·검증한 다음 설정을 저장합니다. 둘 다 데이터 변경은 롤백하고 Excel·LLM·OneDrive 작업은 호출하지 않습니다.

파이프라인 검증은 선택한 보고일과 7일 전의 기존 DB 원본을 입력으로 사용합니다. 두 날짜가 이미 적재된 날짜를 선택하세요. 스키마·원본 적재·집계·이력·보고서 SELECT를 모두 실행하고 컬럼·행 수·원본 합계를 대조합니다. 실패 시 기존 SQL 설정을 유지합니다. 적재·삭제·이력 INSERT도 편집 가능하되 지정된 두 InnoDB MVP 테이블에 한정합니다. 대상 날짜 밖의 데이터를 바꾸는 SQL은 롤백하고 거부합니다. SELECT는 단일 조회로 감싸 실행 시간과 행 수를 제한하며 DDL·트랜잭션 제어·파일 접근은 지원하지 않습니다.

문장 순서와 매개변수 개수는 현재 Python·DB 계약에 맞춰 유지합니다. 화면의 **매개변수와 출력 기준**에 파일별 기준이 표시됩니다. 집계 출력은 `report_date, channel, visits, page_views, orders, revenue_krw` 6개 컬럼이며 두 날짜 × 5개 채널의 10행입니다. 보고서 SELECT 3개는 상세 30행, 채널 10행, 디바이스 6행을 반환합니다. 다른 지표·컬럼·기간의 자유 분석은 **분석 SQL**로 등록해 질문·보고서·예약에 사용하세요. 실제 공급자의 다른 스키마는 연동 단계에서 매핑합니다.

웹에서 적용한 SQL은 `work/pipeline_sql.json`, 집계 SELECT는 `work/aggregation.json`에 저장하고 수동·예약 수집에 공통 적용합니다. Docker는 `work/`를 읽기 전용으로 마운트하므로 SQL 편집에 재빌드는 필요 없습니다. **기본 SQL 불러오기**는 편집기 내용만 바꾸며 **검증 후 적용**해야 복원됩니다. 변경은 과거 보고서를 바꾸지 않으므로 같은 날짜를 생성하려면 **새 버전**을 선택하세요. 적용된 SQL 내용은 보고서 식별 해시에 포함합니다.

`report_daily.sql`의 상세·채널·디바이스 결과는 실제 기본 보고서의 **조회 데이터 / 일일 보고서 / 디바이스 집계** 시트에 사용합니다. 수집 시에도 편집된 SQL의 결과를 검증하며 실패 시 원본·이력 변경을 함께 롤백합니다.

ER 실선은 DB에 선언된 외래키이며 PK/FK는 메타데이터에서 읽습니다. 데모의 원본→집계 테이블은 실제 외래키가 없어 `aggregate_daily.sql` 기본값의 **논리적 집계 관계**를 점선으로 구분합니다. 사용자 SQL의 조인 관계는 자동 추정하지 않습니다. 같은 이름의 컬럼만으로 임의 관계를 추정하지 않습니다. 탐색·미리보기는 연결된 DB 내부의 테이블/뷰로 제한하며, 테이블 선택만으로 생성되는 SQL도 동일한 읽기 전용·실행 시간·행 수 제한을 적용합니다.

날짜 변수는 `%(report_date)s`, `%(comparison_date)s`(7일 전), `%(start_date)s`, `%(end_date)s`입니다.
직접 조회·예약은 start/end 모두 보고일이고, 데이터 질문은 해석한 기간을 전달합니다.
SQL에 변수를 사용하지 않으면 그 날짜 조건은 적용되지 않습니다. 채널·그 외 조건은 저장 SQL에 직접 작성합니다.
임의 스키마의 결과 컬럼을 지원하며 기존 고정 채널·디바이스 KPI 형식에 맞출 필요는 없습니다.

```sql
SELECT report_date, channel, SUM(revenue_krw) AS revenue_krw
FROM mvp_raw_daily
WHERE report_date BETWEEN %(start_date)s AND %(end_date)s
GROUP BY report_date, channel
```

- 단일 SELECT/WITH 조회만 허용합니다. 주석·다중 문장·파일 접근·잠금 함수는 지원하지 않습니다.
- 실제 실행은 읽기 전용 트랜잭션, 5초 서버 제한, 미리보기 200행 제한을 적용합니다. 보고서는 최대 5,000행이고 초과하면 실패합니다.
- 사용자 SQL 오류는 원문·접속 정보 대신 오류 종류만 기록합니다. 등록·수정 버튼에서 서버가 SQL을 실행해 검증하며, 실패하면 기존 항목을 유지합니다.
- SQL 보고서 Excel은 **조회 데이터 / AI 분석** 시트로 생성하고, 기존 파일을 보존합니다. 숫자 타입은 유지하며 문자열은 Excel 수식으로 해석하지 않습니다.
- SQL 보고서의 AI 입력은 최대 200행입니다. 더 큰 결과는 SQL에서 집계하고 AI의 표본 해석을 전체 결과로 간주하지 마세요.
- 저장 쿼리의 연결 계정은 실제 환경에서 승인된 테이블의 SELECT 권한만 가진 전용 계정을 사용해야 합니다. FILE·관리자·UDF 권한을 부여하지 않습니다.
- 기본 실행은 기존 예시 API 추출→적재→집계 흐름입니다. 저장 SQL 예약도 이 수집·적재 단계를 먼저 실행합니다. 화면의 수동 SQL 보고서와 질문은 이미 적재된 DB를 조회합니다.
- 수집이 커밋된 뒤 SQL 보고서를 생성하므로 분석·파일 생성 실패 시에도 수집 데이터는 DB에 남습니다. 결과가 0행이면 보고서를 생성하지 않습니다.

Adobe Analytics의 Report Suite·차원·지표는 API 메타데이터와 Reports API로 조회한 뒤 MariaDB 테이블로 정규화해 적재합니다.
이후 동일한 테이블 탐색·저장 SQL·예약·질문을 사용할 수 있습니다. Adobe Report API를 SQL 테이블 서버로 취급하지 않습니다.
공식 참고: [Report API](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/reports/),
[Report Suites API](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/report-suites).

## SQL 보관

일일 업무 SQL은 `sql/`에 모았습니다. Python은 순서·매개변수 바인딩·트랜잭션과 수치 대조를 담당합니다.

| 파일 | 처리 |
|---|---|
| schema.sql | 초기 테스트 테이블 생성 |
| load_daily.sql | 대상 날짜 원천 교체·적재 |
| aggregate_daily.sql | 일별·채널별 집계 SELECT 기본값 (웹에서 사용자 SQL 적용 가능) |
| transform.sql | 검증한 집계 결과의 이력 삭제·INSERT |
| validate_daily.sql | InnoDB 확인·집계 결과 조회 및 대조 |
| report_daily.sql | 실제 Excel의 상세·채널·디바이스 조회 SELECT |
| question.sql | 전체·채널·디바이스·일별 질문 집계 SELECT 4종 |
| question_coverage.sql | 질문 대상 날짜 적재 완전성 확인 |

DB 잠금 및 읽기 전용 트랜잭션 시작은 실행 제어용 SQL이므로 코드에 둡니다.
여러 문장이 있는 파일은 고정된 순서로 실행하며, 저장소 SQL의 문자열·주석 안에는 세미콜론을 쓰지 않습니다.
날짜는 `%s` 또는 `%(report_date)s` 등 매개변수로 바인딩합니다. 저장소 파일은 브라우저나 LLM이 수정하지 않으며, 웹에서 편집한 다섯 파이프라인 SQL은 별도 로컬 설정으로 보관합니다.
적용된 다섯 파이프라인 SQL 내용의 해시를 보고서 식별에 반영해 변경된 SQL의 기존 결과를 조용히 재사용하지 않습니다.

## 로컬 API + LLM 테스트

```sh
# 최초 한 번만. 기존 .env를 덮어쓰지 마세요.
test -f .env || cp .env.example .env
make api-demo DATE=2026-09-29
```

가상 쇼핑몰 HTTP API → 필드 정규화 → 기존 MariaDB → SQL → 새 Excel 흐름입니다.
실제 쇼핑몰이나 Adobe에 접속하지 않으며, API와 DB는 Docker 내부에서만 접근합니다.
`api-demo`는 이미지 빌드·서비스 시작·테이블 초기화까지 수행합니다.
이후 `make api-report DATE=2026-09-29`로 재생성합니다. 기존 파일은 보존됩니다.

`.env`에서 아래 중 하나를 선택하고 API 계정에서 사용 가능한 **정확한 모델 ID**를 입력하세요.
모델을 코드에 고정하지 않습니다. Compose가 `.env`를 읽으므로 키 변경 후 이미지 재빌드는 필요 없습니다.
Python을 직접 실행할 경우에는 환경변수를 직접 설정해야 합니다.

```dotenv
LLM_PROVIDER=gemini
LLM_MODEL=사용할-Gemini-모델-ID
GEMINI_API_KEY=본인의-API-키
```

또는:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=사용할-OpenAI-모델-ID
OPENAI_API_KEY=본인의-API-키
```

키는 대화창·소스코드 대신 로컬 `.env`에만 입력하세요. Git과 Docker 이미지에서 제외됩니다.
LLM을 끄려면 `LLM_PROVIDER=none`입니다. Excel 파일 생성 자체에는 API 키가 필요 없습니다.
LLM에는 조회 결과를 전달합니다. 기본 질문은 검증된 조건으로 고정 SELECT를 실행하며, 저장 쿼리를 선택한 질문은 날짜 변수를 바인딩해 해당 SELECT를 실행합니다. LLM은 조회 기간과 답변을 만들며 SQL 실행은 서버가 담당합니다.
선택한 서비스의 API 사용 요금이 발생할 수 있습니다.

- `AI 분석` 시트 및 JSON의 `analysis.status`: `disabled`, `not_configured`, `succeeded`, `failed`.
- 키·모델 누락, 인증 실패, 시간 초과 등에도 수치 Excel은 생성합니다. LLM 상태를 반드시 확인하세요.
- 실패 응답 본문이나 키는 로그에 기록하지 않습니다. `HTTP_401` 등 오류 분류만 남깁니다.
- 키 수정 후 `make api-report DATE=...`로 새 버전을 생성하세요. 성공·실패 결과 모두 명시적 재생성이 필요합니다.
- LLM 설정·프롬프트 변경은 보고서 식별에 반영합니다. 키 값은 식별자나 보고서에 저장하지 않습니다.
- 한 번 호출하며 자동 재시도는 없습니다. HTTP 읽기 제한 1MB, 소켓 타임아웃 45초입니다.

`DATA_PROVIDER=mock|example_api|adobe`와 `LLM_PROVIDER=none|openai|gemini`는 독립적입니다.
`--csv`는 DATA_PROVIDER보다 우선합니다. 다른 실제 데이터 공급자를 추가할 때는
`providers.py`의 변환 함수에서 공통 필드로 맞추고 `pipeline.extract`에 분기를 추가하면 됩니다.
공통 필드: `date, channel, device, visits, page_views, orders, revenue_krw`.
실제 AA 고유 방문자나 차원 합산은 별도 정의·검증이 필요합니다.

API 구현 기준: [OpenAI Responses](https://developers.openai.com/api/docs/guides/text),
[Gemini generateContent](https://ai.google.dev/gemini-api/docs/generate-content/text-generation).
모델 접근권한·실제 키의 성공 여부는 각 계정으로 호출해 확인해야 합니다.

## 개인 OneDrive로 Excel 동기화

Microsoft API 대신 **OneDrive 앱**의 동기화 폴더를 사용합니다. 현재 Mac 경로로 검증했으며 Windows에서는 실제 OneDrive 폴더 경로를 지정하세요. Linux에서 OneDrive 폴더가 없다면 로컬 Excel 저장만 사용할 수 있습니다.
Azure 가입, Client ID, Client Secret, Microsoft 비밀번호 설정은 필요 없습니다.

1. OneDrive 앱에 개인 Microsoft 계정으로 로그인합니다.
2. 파일 탐색기에서 해당 OneDrive 폴더를 열고 `Databook` 폴더를 만듭니다.
3. 웹 **설정 → OneDrive 저장**에서 **Databook 폴더의 실제 전체 경로**를 입력하고 **경로 저장**합니다. 서버에서 폴더 존재·절대 경로·쓰기 권한을 확인하며 실패 시 기존 경로를 유지합니다.

경로는 `work/onedrive.json`에 저장하며 재시작 후에도 유지됩니다. 웹 설정을 저장하기 전에는 기존 `.env`의 `ONEDRIVE_DIR`를 사용합니다. 저장 이후에는 웹 설정이 환경 변수보다 우선하며 **빈 경로를 저장하면 복사를 끕니다**. 수동 실행·예약·CLI 모두 같은 설정을 사용합니다. `work/`는 Git 및 Docker 빌드에서 제외하므로 개인 경로와 사용자 SQL은 공개 저장소에 포함되지 않습니다. API 키와 `.env`의 다른 값은 웹에 표시하지 않습니다.

웹 설정을 사용하지 않을 때만 아래 환경 변수로 설정할 수 있습니다.

```dotenv
# 예시입니다. 실제 Mac에 존재하는 경로로 바꾸세요.
ONEDRIVE_DIR=/Users/YOUR_USER/Library/CloudStorage/OneDrive-Personal/Databook
```

```sh
# 이미 생성된 해당 날짜의 최신 Excel만 복사 (DB·LLM 재실행 없음)
make sync DATE=2026-09-29

# 보고서 생성 후 자동 복사
make api-report DATE=2026-09-29
```

`make demo`, `report`, `regenerate`, `api-demo`, `api-report`는 생성 성공 후 복사합니다.
사용할 OneDrive 경로가 비어 있으면 복사를 건너뜁니다. 폴더는 미리 존재해야 하며 잘못된 경로를
자동 생성하지 않습니다. JSON·로그·.env는 복사하지 않고 완성된 Excel 하나만 복사합니다.
원본 체크섬을 검증하고, 같은 파일이면 건너뛰며, 같은 이름의 다른 내용은 덮어쓰지 않습니다.
복사가 실패해도 로컬 보고서는 보존됩니다. 설정을 고친 뒤 `make sync`로 복사만 재시도하세요.
복사 중 프로세스를 강제 종료해 불완전한 대상 파일이 남았다면 해당 파일을 확인·정리한 뒤 재시도하세요.

`copied_local`은 **로컬 OneDrive 폴더에 복사 완료**라는 의미입니다. 클라우드 업로드 완료는
OneDrive 앱의 동기화 상태나 OneDrive 웹에서 확인하세요. 앱 종료·오프라인·용량 부족 시 업로드가 지연됩니다.
원본은 프로젝트의 `reports/`에 유지합니다. Docker에 OneDrive를 직접 마운트하지 않습니다.
`docker compose ... worker run`을 직접 실행했다면 이후 `make sync`를 별도로 실행하세요.

예약 실행도 생성 후 복사합니다. 예약 설정은 관리자 화면에서 변경하며, OS 작업 등록이나 Microsoft 자격 증명은 필요 없습니다.

## DB 데이터에 질문하기

질문에는 이미 적재된 데이터만 사용합니다. 질문 자체는 추출·적재·DB 변경을 하지 않습니다.

```sh
docker compose -f compose.yaml -f compose.demo.yaml run --rm worker ask --date 2026-09-29 '최근 7일간 paid_search 채널의 모바일 매출 추세를 설명해줘'
```

- 기준일은 웹 날짜 선택 또는 `--date`이며 현재 시각이 아닙니다.
- AI가 `start,end,group,channel,device` 조건만 JSON으로 제안합니다. 서버는 날짜·31일 상한·허용 값과 키 목록을 검증합니다.
- 집계 방식: 전체, 채널별, 디바이스별, 일별. 필터: 현재 테스트의 5채널·3디바이스 중 하나 또는 전체.
- 하루는 전주 같은 요일, 여러 날은 직전 같은 길이 기간과 비교합니다. 임의 비교 기간은 아직 지원하지 않습니다.
- 두 기간 모든 날짜의 15개 원천 조합이 있어야 합니다. 부족하면 날짜를 안내하고 종료합니다. 누락 날짜 보고서를 먼저 생성하세요.
- SQL은 `question.sql`에서 선택하고 모든 조건을 `%s` 매개변수로 바인딩합니다. 읽기 전용 트랜잭션으로 실행합니다.
- 수치·증감률은 코드로 계산하고 AI에는 집계 결과만 전달합니다. 답변의 조건·조회 수치·SQL을 펼쳐 검증할 수 있습니다.
- 질문당 조건 해석과 답변 생성으로 보통 LLM을 두 번 호출합니다. 대화 이력, 임의 SQL, 새로운 차원·지표는 지원하지 않습니다.


## 바로 실행

필수: Docker 실행, Docker Compose, uv. `make`는 선택 사항이며 Make 없는 실행 명령도 아래에 있습니다.

```sh
git clone https://github.com/ice-ice-bear/databook-mvp.git
cd databook-mvp
uv sync --locked
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
- CSV는 정확한 날짜 × 5채널 × 3디바이스 조합을 요구합니다. 누락 행을 0으로 채우지 않습니다. Adobe 어댑터도 누락 조합을 임의로 채우지 않습니다. 다른 차원·누락 의미·소수 금액을 쓰려면 DB·SQL·출력 계약을 함께 변경해야 합니다.

매일 바뀌는 날짜로 로컬 테스트하려면 CSV 대신 결정적인 가상 데이터 생성기를 사용합니다. `--date` 생략 시 한국 시간 기준 어제이며 API 키는 필요 없습니다.

```sh
docker compose -f compose.yaml -f compose.demo.yaml run --rm worker run
```

같은 날짜에 CSV 보고서가 이미 있다면 데이터 모드 변경이므로 `--regenerate`가 필요합니다. 어느 입력을 썼는지는 Excel 상단과 실행 결과에 표시됩니다.

## 검증

```sh
make test
```

실제 데모 MariaDB를 사용해 적재·SQL 집계·Excel 수치, 입력 누락·중복·음수 거부, 0분모, 동일 요청 재사용, 새 버전 생성, 동시 실행 잠금, 파일 생성 실패 시 DB 롤백과 이전 파일 보존을 확인합니다.

Adobe는 가짜 HTTP 응답으로 인증·페이지·breakdown·토큰 갱신·오류 처리를 검증하고, 정규화한 가짜 Adobe 데이터를 실제 데모 MariaDB에 적재해 Excel까지 확인합니다. 실제 Adobe 계정/API는 테스트에서 사용하지 않습니다.

웹·예약·OneDrive 설정, 기본 분석 SQL의 직접 수정, 등록·수정 시 1회 실행 후 저장, 검증 실패 시 기존 파일 보존도 확인합니다. 다섯 파이프라인 파일을 각각 실행·롤백하고 대상 날짜 밖의 DELETE와 잘못된 보고서 결과를 거부하는지 검증합니다. ER의 실제 FK·뷰는 임시 테스트 객체로 확인 후 제거합니다. 테스트는 지정된 데모 DB와 가상 날짜 데이터에 쓰므로 운영 DB에서 실행하지 않습니다. LLM 호출과 OneDrive 복사는 테스트에서 실행하지 않습니다.

## KST 요일별 예약 실행 · 관리자

[관리자 화면](http://127.0.0.1:8765/admin)에서 **자동 실행 사용** 여부와 월~일 중 실행 요일, 실행 시각을 저장합니다. 매일·평일·주말 빠른 선택 버튼을 사용하거나 요일 토글로 직접 조합합니다. 주 1회는 원하는 요일 하나만 선택합니다. 변경한 요일은 예약 설정 저장 후 적용됩니다.
기본 시각은 **09:00 KST**입니다. OS 시간대와 관계없이 UTC+09:00을 사용합니다.
설정을 켜면 선택한 요일의 다음 도래하는 시각부터 실행합니다. 이미 지난 시각을 저장하면 다음 선택 요일의 해당 시각부터 시작합니다.
다음 실행 시각, 실행 중 여부, 마지막 실행 결과를 화면에서 확인합니다.

- 요일 선택은 **실행 날짜**의 KST 요일입니다. 선택 요일마다 어제의 일일 보고서를 생성하며, 주간 합산 보고서로 바뀌지는 않습니다.
- 설정: `work/schedule.json` (Git 제외). 종료·재시작 후에도 설정을 유지합니다.
- 웹 서버가 스케줄러를 함께 실행합니다. 화면을 열어둘 필요는 없지만 서버 프로세스와 Docker는 실행 중이어야 합니다.
- 웹을 사용하지 않을 때는 `uv run --locked schedule.py --serve` 또는 `make schedule`로 동일 스케줄러만 실행합니다.
- OS별 Python 명령 대신 `uv run --locked`로 동일 환경에서 실행합니다. 호스트 Python은 `.python-version`의 3.12를 사용합니다.
- 실행 시 db·example-api 서비스 상태를 확인하고 필요하면 시작합니다. 최초 이미지 빌드·DB 초기화는 먼저 완료해야 합니다.
- KST 기준 어제 보고서를 만들고 OneDrive로 복사합니다. 같은 KST 날짜에는 한 번만 시도하며 `work/schedule_날짜.claim`으로 중복 실행을 방지합니다.
- 실패한 작업은 자동 재시도하지 않습니다. 웹에서 해당 날짜의 보고서를 수동 생성하세요. 로그는 `logs/schedule.out.log`, `logs/schedule.err.log`입니다.
- 중지 상태로 지나간 과거 날짜는 자동 보충하지 않습니다. 예약 시각이 지난 같은 날에 서버를 다시 켜면 해당 예약을 실행할 수 있습니다.
- 컴퓨터 종료·절전·Docker 종료 상태에서 실행을 보장하지 않습니다. 재부팅 후 서비스 자동 시작은 향후 운영 단계에서 OS별로 추가합니다.

### Make 없이 시작하기

Make가 없는 환경은 위 [빠른 시작](#빠른-시작)의 uv·Docker Compose 명령을 사용합니다. OneDrive 경로만 해당 OS의 실제 폴더로 지정하세요.
호스트와 Docker 모두 `pyproject.toml`과 `uv.lock`의 동일한 의존성을 설치합니다. 웹·예약 코드는 표준 라이브러리를 사용합니다.


## 기존 호스트 MariaDB로 전환

기본 `compose.yaml`은 `host.docker.internal`을 통해 호스트 DB에 연결합니다. `compose.demo.yaml`은 독립 로컬 검증을 위한 선택적 덮어쓰기 설정입니다. **실제 DB에 연결할 때도 demo overlay를 함께 쓰면 계속 데모 DB에 접속하므로 주의하세요.**

1. 기존 서버에서 사용해도 되는 테스트 DB와 계정을 지정합니다. 이 MVP는 실수 방지를 위해 `databook_mvp_*` 테스트 DB 이름만 허용합니다. 프로그램은 DB나 계정을 자동 생성하지 않습니다.
2. `.env.example`을 `.env`로 복사하고 테스트 접속값을 입력합니다. `.env`는 Git과 Docker 이미지에서 제외됩니다.
3. 운영 테이블에 연결하기 전 기존 스키마·SQL 매핑을 구현해야 합니다. 현재 `sql/schema.sql`은 테스트 테이블 2개뿐이며 원래 시스템의 축소·대체 스키마가 아닙니다.

```sh
test -f .env || cp .env.example .env
# 기존 키는 유지하고 .env의 테스트 DB 접속 정보만 수정
docker compose build worker
docker compose run --rm worker init-db
docker compose run --rm worker run --date 2026-09-27 --csv data/adobe_mock_daily.csv
```

`init-db`는 지정된 테스트 DB에 `mvp_raw_daily`, `mvp_history_daily`만 만듭니다. 일반 실행은 DDL을 실행하지 않습니다. 기존 DB의 테이블을 삭제·이름 변경하거나 새 DB 제품으로 옮기지 않습니다. Docker Desktop에서 호스트의 접근 허용 포트·DB 계정의 접속 허용 범위는 별도로 확인해야 합니다.

### 기존 DB 연결 전 준비할 자료와 매핑

현재 웹·예약 명령은 `compose.demo.yaml`을 사용하는 데모 경로로 고정되어 있습니다.
`.env`의 DB 접속값만 바꿔도 웹·예약이 기존 DB로 전환되는 것은 아닙니다. 실제 연결은 아직 미구현입니다.

1. 기존 MariaDB의 호스트·포트·테스트 DB·계정, 테이블 DDL, 현재 추출/가공/export SQL을 준비합니다. 비밀번호와 덤프는 저장소에 넣지 않습니다.
2. 운영 DB와 동일한 스키마의 승인된 `databook_mvp_*` 테스트 DB에서 먼저 검증합니다. 현재 코드의 테스트 DB 이름 제한은 유지합니다.
3. 원래 다중 원천 테이블·기본 뷰·history 테이블과 이 MVP의 2개 테이블 사이의 매핑을 작성합니다. 기존 테이블을 삭제하거나 MVP 테이블로 교체하지 않습니다.
4. 추출 필드, SQL 입력·출력, 날짜별 갱신 키, 이력 누적 방식, Excel 출력 열을 원래 업무 기준으로 맞춥니다. `sql/` 파일과 파이프라인 검증도 함께 변경해야 합니다.
5. 읽기 조회부터 연결을 확인하고, 쓰기는 지정 테스트 테이블에만 허용합니다. 실제 작업에 필요한 권한만 부여하고 기존 데이터 백업·롤백 범위를 확인합니다.
6. 직접 Compose 실행 때는 `compose.yaml`만 사용합니다. 웹·예약용 Compose 명령도 demo overlay를 제거하는 변경이 필요합니다. 운영 원천에는 `init-db`와 통합 테스트를 실행하지 않습니다.
7. 동일 날짜의 수동 결과와 원천 건수·채널 집계·총계·이력·Excel을 대조한 후 전환합니다. 현재 질의의 5채널×3디바이스 완전성 검증도 실제 차원과 누락 의미에 맞춰 변경해야 합니다.

현재 사용자 설정이 필요한 DB 항목은 `DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD`이며
Docker Desktop의 호스트 DB 주소 예시는 `host.docker.internal`입니다. Linux 호스트에서도 Compose의
`extra_hosts` 설정을 사용합니다. 실제 계정의 허용 호스트·포트 접근은 서버 설정과 함께 확인하세요.

## Adobe Analytics 사전 설정과 실제 수집

`adobe.py`는 OAuth Server-to-Server 인증, Discovery/차원/지표 조회, 채널 → 디바이스 일별 breakdown, 페이지 처리, 401 토큰 갱신, 429·일시 오류의 제한된 재시도를 구현합니다. 토큰·비밀키·응답 오류 본문은 로그나 파일에 저장하지 않습니다. 실제 Adobe 계정으로는 아직 검증하지 않았습니다.

### 1. 개인 환경변수 입력

Adobe Admin Console에서 Analytics product profile과 대상 Report Suite 접근 권한을 부여하고, [Adobe Developer Console](https://developer.adobe.com/console/) 프로젝트에 Adobe Analytics API와 **OAuth Server-to-Server** 자격 증명을 추가합니다.

`.env.example`의 `ADOBE_*` 항목을 개인 `.env`에 입력하세요. 기존 파일은 덮어쓰지 않습니다.

| 항목 | 입력할 값 |
| --- | --- |
| `ADOBE_CLIENT_ID`, `ADOBE_CLIENT_SECRET`, `ADOBE_SCOPES` | Developer Console의 해당 OAuth 자격 증명 값. Scopes는 프로젝트 값을 그대로 사용 |
| `ADOBE_GLOBAL_COMPANY_ID` | 아래 `adobe-check`의 companies에 표시되는 Global Company ID |
| `ADOBE_REPORT_SUITE_ID` | 분석할 Report Suite ID (RSID) |
| `ADOBE_REPORT_SUITE_TIMEZONE` | `adobe-check`의 suite.timezoneZoneinfo와 동일한 값 |
| `ADOBE_CHANNEL_DIMENSION`, `ADOBE_DEVICE_DIMENSION` | 조회된 실제 차원 ID. 기본값은 marketingchannel/mobiledevicetype |
| `ADOBE_METRIC_VISITS`, `ADOBE_METRIC_PAGE_VIEWS`, `ADOBE_METRIC_ORDERS`, `ADOBE_METRIC_REVENUE_KRW` | 조회된 실제 지표 ID. 회사별 event/계산 지표라면 변경 |
| `ADOBE_SEGMENT_ID` | 선택 사항. Workspace와 동일한 세그먼트를 적용할 때 입력 |
| `ADOBE_CHANNEL_MAP`, `ADOBE_DEVICE_MAP` | 실제 Adobe 표시값을 MVP 값으로 변환하는 JSON. 예시의 키를 실제 값으로 교체 |
| `ADOBE_MAPPING_CONFIRMED` | 초기값 `false`. 미리보기·매핑·집계 대조 후에만 `true` |

`.env`의 기존 `DATA_PROVIDER`는 이 단계에서 유지합니다. 키·토큰·실제 응답은 Git에 넣지 않습니다. OneDrive/LLM 설정은 별개이며 변경할 필요가 없습니다.

### 2. DB 쓰기 없이 인증·메타데이터 확인

```sh
docker compose -f compose.yaml build worker
docker compose -f compose.yaml run --rm --no-deps worker adobe-check
```

첫 실행에는 OAuth 3개 값만 있어도 됩니다. 회사 목록을 확인해 Company ID와 RSID를 넣고 다시 실행하면 Report Suite의 통화·시간대와 접근 가능한 차원·지표 ID가 표시됩니다. 여러 회사 중 하나를 자동으로 선택하지 않습니다. 이 명령은 DB 연결, LLM 호출, Excel 생성, OneDrive 복사를 하지 않습니다.

### 3. 일별 원천 미리보기

```sh
docker compose -f compose.yaml run --rm --no-deps worker adobe-preview --date 2026-09-29
```

보고일과 7일 전의 **실제 Adobe 채널·디바이스 표시값, 지표, API 총계**를 조회합니다. 금액 소수와 누락 조합도 그대로 확인하며 DB에는 쓰지 않습니다. 날짜는 Report Suite의 하루 `[00:00, 다음 날 00:00)`이며 KST 예약 시각과는 별개입니다. 원천 시간대에 맞는 완료된 날짜를 선택하세요. 이 출력은 실제 업무 데이터이므로 공개 저장소에 저장하지 마세요.

### 4. 현재 MVP에 적재 가능한지 확인 후 활성화

현재 일일 파이프라인은 다음 계약을 유지합니다. 더 넓은 스키마로 자동 변경하지 않습니다.

- 5개 채널 `paid_search, organic_search, direct, email, social` × 3개 디바이스 `mobile, desktop, tablet`의 일대일 매핑과 두 날짜의 모든 조합이 필요합니다.
- 예시의 `Other → desktop` 등은 계정마다 의미가 다르므로 확인 없이 사용하지 마세요. 미매핑 값·누락·중복은 적재 전에 실패합니다. 누락 행을 0으로 만들지 않습니다.
- Report Suite 통화가 **KRW**, 금액·나머지 지표가 음수 없는 정수여야 합니다. 소수 금액을 반올림하거나 외화를 KRW로 이름만 바꾸지 않습니다.
- 시간대 설정이 API 메타데이터와 같아야 합니다. 각 날짜의 분해 행 합계와 API 총계를 지표별로 대조합니다. Visits의 중복 등으로 총계가 다르면 적재를 거부합니다. 미리보기 총계도 동일 조건의 Workspace와 대조하세요.

계약과 업무 기준이 맞는 경우에만 `.env`에서 `ADOBE_MAPPING_CONFIRMED=true`, `DATA_PROVIDER=adobe`로 변경합니다. 기존 웹·예약·저장 SQL의 수집 경로도 같은 어댑터를 사용합니다. `.env` 변경은 매번 새 Compose worker에 반영됩니다.

```sh
# 실제 Adobe 데이터 → 격리된 데모 MariaDB → 신규 Excel. 기존 파일은 보존합니다.
docker compose -f compose.yaml -f compose.demo.yaml run --rm worker run --date 2026-09-29 --regenerate
```

이 명령은 데모 DB가 이미 초기화된 상태를 전제로 하며 실제 Adobe 날짜 데이터로 해당 날짜의 테스트 테이블을 갱신합니다. 처음에는 수동 결과를 확인하고 예약을 활성화하세요. 기존 운영 MariaDB로 전환하는 작업은 위 별도 가이드를 따라야 합니다. Adobe 키만 넣어도 DB 연결이 자동 전환되지는 않습니다.

현재 계약과 맞지 않는 실제 차원·통화·지표는 **미리보기까지 사용**하고 스키마·SQL·Excel 매핑을 조정한 후 적재합니다. 대규모·hit 단위 수집은 이 Reports API 어댑터 범위 밖입니다. 한 breakdown은 최대 10페이지/10,000항목, 날짜당 최대 50개 채널로 제한합니다.

오프라인 계약 검증은 `uv run --locked test_adobe.py`로 실행합니다. 실제 자격 증명이나 API를 사용하지 않고 인증 payload, 페이지/breakdown, 토큰 갱신, 재시도, 정수 금액, 누락·총계 불일치 차단을 확인합니다.

공식 참고: [OAuth와 예약 보고서](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/reports/recurring),
[Discovery](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/discovery),
[차원 breakdown](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/reports/breakdowns),
[Report Suite 메타데이터](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/report-suites).


## 최소 운영 규칙

- MariaDB 이름 잠금으로 예약·수동 실행을 직렬화합니다. 잠금을 확보하지 못하면 실패 기록을 남기고 종료합니다.
- 대상 두 날짜의 원천 교체와 history 집계는 InnoDB 트랜잭션 하나로 처리합니다. Excel 임시 파일 생성까지 실패하면 롤백합니다.
- DB 커밋과 파일 공개를 하나의 원자적 트랜잭션으로 만들지는 않습니다. 커밋 후 파일 공개가 실패하면 해당 날짜를 재실행해 복구합니다. DB에는 중복 없이 다시 적재되며 기존 보고서는 보존됩니다.
- 완성된 임시 파일만 새 이름으로 공개합니다. 이미 존재하는 보고서는 덮어쓰지 않습니다. 비정상 종료로 임시 파일이 남으면 `.report-*`만 정리할 수 있습니다.
- JSON 로그에는 단계·상태·오류 종류를 기록합니다. 실행 중 프로세스가 강제 종료되면 `running` 기록이 남을 수 있으며 재실행할 수 있습니다. 자동 재시도·자동 상태 정리는 아직 없습니다.
- 수치 계산은 SQL·Python으로 처리합니다. 사람 기준 순방문자·전환율을 만들어내지 않으며 가상 방문의 합산 가정을 실제 AA 데이터에 적용하지 않습니다.

## 구조

```text
pyproject.toml / uv.lock  호스트·Docker 의존성 정의와 잠금
query_workspace.py    테이블 탐색·저장 SELECT·SQL 분석/보고서
providers.py          예시 API 정규화 및 OpenAI/Gemini HTTP 호출
adobe.py              Adobe 인증·메타데이터·일별 수집·매핑 검증
example_api.py        로컬 가상 쇼핑몰 API 서버
web.py                로컬 HTTP 화면·Compose 실행·다운로드
web/index.html        질문·보고서 화면
pipeline.py           추출·검증·잠금·트랜잭션·보고서·CLI
sql/schema.sql        데모 테이블 2개 (init-db 전용)
sql/aggregate_daily.sql 집계 SELECT 기본값
sql/transform.sql     검증한 집계 결과를 history에 반영
data/                 기존 90일 가상 CSV
compose.yaml          호스트 MariaDB에 연결하는 worker
compose.demo.yaml     독립 MariaDB 테스트 환경
test_pipeline.py      실제 MariaDB를 사용하는 통합 확인
test_adobe.py         실제 키·API 없이 Adobe 계약과 오류 처리 확인
schedule.py           KST 요일별 예약 실행·관리자 설정
sync_onedrive.py       호스트에서 완성된 Excel을 OneDrive 폴더로 복사
```

사용을 마치면 `make stop`으로 데모 DB와 예시 API를 중지합니다. 데이터 볼륨은 보존됩니다. 실제 Adobe API와 LLM을 쓰기 전까지 개인 API 키는 필요 없습니다.
