# 실행 및 데이터 적재 상태

마지막 확인: 2026-08-07

## 접속 주소

- 프런트엔드: `http://localhost:5173`
- 관리자 화면: `http://localhost:5173/admin`
- 백엔드 API: `http://localhost:8000/api/v1`
- OpenAPI 문서: `http://localhost:8000/docs`

## 현재 실행 상태

- 백엔드 PID: `10980`
- 프런트엔드 정적 미리보기 PID: `14920`
- `GET /api/v1/health`: `200`, `{"status":"ok"}`
- 자격증 API: `DEA-C01` 1건 노출 확인
- 백엔드는 루트 `.env`의 외부 MySQL 설정을 사용한다.

## 외부 MySQL 연결 및 스키마

- 외부 MySQL 8.0.23 연결 성공
- 기존 업무 테이블은 변경하지 않고 앱 테이블 15개만 추가
- 스키마 기준 버전: `0002_aws_domain_classification`
- 현재 실행 환경에서 Alembic 패키지 다운로드가 제한되어, 초기 스키마는 동일한 SQLAlchemy 메타데이터의 `create_all(checkfirst=True)`로 생성하고 버전을 기록했다.
- `mock_exam_questions`의 두 복합 UNIQUE 제약조건 이름이 MySQL에서 충돌하는 문제를 발견하여 각각 명시적 이름으로 수정했다.
- `.env`의 개별 `DATABASE_HOST/PORT/NAME/USER/PASSWORD`가 모두 있으면 이를 우선하여 연결 URL을 조립한다. 비밀번호 특수문자는 URL 인코딩된다.
- DB 비밀번호와 OpenAI API 키는 로그·문서·Git에 기록하지 않는다.

## AWS DEA-C01 실제 적재 결과

데이터 경로: `data/processed/dataset/aws-dea-c01/`

- dry-run: `total=295, added=295, updated=0, unchanged=0, excluded=0, failed=0`
- 첫 strict 적재: `total=295, added=295, updated=0, unchanged=0, excluded=0, failed=0`
- 동일 데이터 재적재: `total=295, added=0, updated=0, unchanged=295, excluded=0, failed=0`
- 자격증: 1개 (`DEA-C01`)
- 도메인: 4개
- 활성 문제: 295개
- 선택지: 1,218개
- 정답 버전: 885개
  - `provided`: 295개
  - `ai_verified`: 295개
  - `admin_final`: 295개
- 단일 선택: 257개
- 복수 선택: 38개
- `DEA-UNCLASSIFIED`: 0개

같은 패키지를 다시 적재해도 문제를 추가하지 않는 멱등성이 실제 외부 MySQL에서 확인됐다.

## 프런트엔드 관련 수정

- `React is not defined`: JSX automatic runtime으로 번들링하도록 수정
- 직접 경로 접근 404: 존재하지 않는 파일 경로를 `index.html`로 반환하는 SPA fallback 적용

## 종료 명령

```powershell
Stop-Process -Id (Get-Content .run/backend.pid), (Get-Content .run/frontend.pid)
```

## 재적재 명령

```powershell
.\scripts\import-dataset.ps1 -Mode dry-run
.\scripts\import-dataset.ps1 -Mode strict
```

문제 데이터는 적재 시 임의 변경하지 않는다. 실제 학습·모의고사에서만 조건에 맞는 활성 문제 풀에서 무작위로 선택하며, 최종 채점은 `admin_final` 답안을 사용한다.

## 2026-08-07 연속 학습 흐름 수정

- 원인: 프런트엔드가 학습 세션의 `question_count`를 1로 고정했고 채점 후 다음 문제를 조회하지 않았다.
- 기본 집중 학습 세션을 10문항으로 변경했다.
- `정답 확인` 후 채점 결과를 표시하고 `다음 문제` 버튼으로 다음 미응답 문제를 조회한다.
- 마지막 문제 채점 후 `학습 완료` 버튼을 누르면 완료 화면과 학습 문항 수를 표시한다.
- 실제 API 2문항 세션으로 첫 문제 제출 후 인덱스가 0에서 1로 증가하고 다음 문제 ID가 변경되는 것을 확인했다.
- 프런트엔드 번들을 갱신하고 SPA 직접 경로 응답 `200`을 확인했다.
- 빈 화면 원인: 직접 생성한 번들에서 Vite 전용 `import.meta.env.VITE_API_BASE_URL`이 정의되지 않아 앱 초기화가 중단됐다.
- API 기본 주소를 번들에 명시하고 JS/CSS 버전 쿼리와 `Cache-Control: no-store`를 적용해 오래된 1문항 번들 캐시를 제거했다.
- 인앱 브라우저에서 실제 `1 / 10` 문제 화면과 선택지 4개 표시를 확인했다.

## 2026-08-07 영역별 전체 학습 및 오답 관리

- 자격증 상세의 DEA-D1~DEA-D4 각 시험 영역 옆에 `학습하기` 버튼을 추가했다.
- 영역 학습은 선택한 영역에서 출제 가능한 활성 문제 전체를 한 세션에 포함한다.
- 세션을 시작할 때마다 전체 문제 집합을 새로 섞으므로 누락 없이 순서만 무작위로 달라진다.
- DEA-D1 검증 결과: 전체 106문항 포함, 두 세션의 문제 집합 일치, 순서 상이.
- 브라우저에서 DEA-D1 학습 화면의 `1 / 106` 표시를 확인했다.
- 오답노트 API가 문제 UID와 한글 본문을 명시적으로 반환하도록 응답 모델을 추가했다.
- 오답별 체크박스, 전체 선택, `선택 삭제 (N)` 기능을 추가했다.
- 오답 제목에 서울 시간 기준 `YYYY.MM.DD HH:mm · 누적 N회` 형식을 적용했다.
- 테스트용 오답 1건으로 선택 삭제 API의 `deleted_count=1`을 확인한 뒤 테스트 데이터를 제거했다.
- 브라우저에서 실제 시간 제목, 개별 선택, 전체 선택, 선택 삭제 버튼 표시를 확인했다.
