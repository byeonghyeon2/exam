# Runtime status

이 문서는 실제 로컬 실행 과정에서 확인한 핵심 상태와 조치 사항을 계속 기록한다.

## 2026-08-06 실행 점검

- Docker와 로컬 MySQL 실행 파일은 현재 호스트에 설치되어 있지 않다.
- 개발 확인은 백엔드 기본값인 로컬 SQLite를 사용한다. 운영 및 Docker 구성은 MySQL 8을 사용한다.
- 첫 샘플 가져오기에서 자격증·영역 메타데이터를 먼저 적재하지 않아 문제 2건이 거부되는 결함을 발견했다.
- CLI가 `certifications.json`, `domains.json`을 먼저 upsert한 뒤 `questions.jsonl`을 스트리밍하도록 수정했다.
- `dry-run`은 메타데이터를 포함한 모든 DB 변경을 rollback한다.
- 첫 API 기동에서 ORM 반환 타입을 FastAPI가 Pydantic 응답 모델로 해석해 시작이 중단되는 문제를 발견했다. 해당 원시 ORM 응답 경로는 명시적으로 자동 응답 모델 생성을 끄도록 수정했다.
- 실제 프런트엔드 계약과 API 응답을 대조해 자격증 `code`, 선택지 `id`, 채점 `is_correct`, 결과 `total_count`, 학습 세션 현재 문제 응답을 정렬했다.
- 실제 서버 프로세스 ID와 HTTP 점검 결과는 아래 실행 확인 절에 갱신한다.

## 핵심 실행 주소

- 프런트엔드: `http://localhost:5173`
- 백엔드 API: `http://localhost:8000/api/v1`
- OpenAPI 문서: `http://localhost:8000/docs`

## 현재 실행 확인

- 백엔드 PID: `14472`
- 프런트엔드 정적 미리보기 PID: `14068`
- `GET /api/v1/health`: `200`, `{"status":"ok"}`
- 자격증 목록: 2건 반환
- 샘플 학습 세션 생성 → 문제 조회 → 답안 제출 → 채점 전체 흐름 성공
- 프런트엔드 `GET /`: `200`

현재 Codex 샌드박스는 Vite가 내부적으로 시작하는 esbuild 자식 프로세스를 차단한다. 따라서 실행 확인에서는 동일한 esbuild 실행 파일로 번들을 직접 만든 뒤 Python 정적 서버로 제공했다. 일반 Windows 터미널에서는 문서화된 `npm run dev` 또는 `scripts/start-frontend.ps1`을 사용한다.

### 미리보기 오류 수정

- `React is not defined`: 직접 번들링할 때 JSX 자동 런타임 옵션이 누락된 것이 원인이었다. `--jsx=automatic`으로 다시 번들링했다.
- React Router 경로 404: 기본 정적 서버는 `/study/...`, `/certifications/...` 같은 경로를 실제 파일로 찾는다. 존재하지 않는 경로를 `index.html`로 반환하는 SPA fallback 서버로 교체했다.
- 브라우저 재검증: 대시보드와 `/certifications/DEA-C01` 직접 접근·새로고침이 정상 렌더링되며 콘솔 오류 0건을 확인했다.

현재 서버를 중지하려면 프로젝트 루트에서 다음을 실행한다.

```powershell
Stop-Process -Id (Get-Content .run/backend.pid), (Get-Content .run/frontend.pid)
```

## AWS DEA-C01 전용 전환

- 현재 로컬 실행은 새 스키마와 AWS 합성 샘플이 들어간 격리 SQLite DB를 사용한다.
- 공개 자격증 API와 화면에는 `DEA-C01`만 표시되고 SnowPro는 숨겨진다.
- 관리자 화면에 미분류 목록, AI 개별·전체 분류, 수동 단원 지정, 단원별 건수, 공식 모의고사 준비도를 추가했다.
- 실제 지정 경로 `data/processed/dataset/aws-dea-c01/`에서 데이터 패키지를 확인했다.
- manifest 295문항과 JSONL 295행이 일치하며 실제 dry-run 결과는 실패 0건이다.
- 패키지는 `validation_report.json` 명칭을 사용하므로 importer가 `verification_report.json`과 두 명칭을 모두 허용하도록 조정했다.
- 현재 호스트에는 MySQL과 Docker 실행 파일이 없어 실제 MySQL 적재 검증은 수행할 수 없다.

## 데이터 적재 순서

1. `certifications.json`
2. `domains.json`
3. `questions.jsonl`

실제 데이터는 먼저 `dry-run`으로 검증한 후 `partial` 또는 `strict`로 적재한다.
