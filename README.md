# 합격비서

## 프로젝트 한눈에 보기

합격비서는 자격증 문제를 반복 학습하고 실전 모의고사를 치를 수 있는 개인용 웹 문제은행입니다. 현재 1차 지원 범위는 **AWS Certified Data Engineer - Associate(DEA-C01)**이며, 문제·선택지·정답 이력을 데이터베이스에 보존하고 채점과 합격 판정은 백엔드가 담당합니다.

사용자는 다음 흐름으로 앱을 사용합니다.

1. 자격증 또는 시험 영역을 선택합니다.
2. 10문항 집중 학습이나 선택 영역 전체 학습을 시작합니다.
3. 단일·복수 정답을 제출하고 즉시 채점 결과를 확인합니다.
4. 틀린 문제는 오답 노트에서 다시 학습합니다.
5. 시간 제한 모의고사를 치르고 환산 점수, 합격 여부, 영역별 성취도를 확인합니다.

주요 기능:

- 자격증 및 시험 영역별 문제 조회
- 무작위 학습, 영역 전체 학습, 단일·복수 선택 즉시 채점
- 시간 제한 모의고사, 답안 임시 저장, 검토 표시, 자동 제출
- 결과·문항별 검토와 오답 노트 관리
- 문제 오류 신고와 저장된 해설 조회
- 관리자 문제 수정, 최종 정답 검증, 신고 처리, JSONL 데이터 가져오기
- 선택적 OpenAI 기반 한국어·영어 해설 생성
- 760px 이하 화면을 위한 모바일 반응형 UI
- Chrome에서 홈 화면 앱으로 설치할 수 있는 PWA
- 일반 계정 최초 Passkey 등록과 계정당 단일 활성 로그인 세션

시스템은 다음과 같이 구성됩니다.

```text
React/TypeScript 웹 클라이언트
             ↓ HTTP API
FastAPI 백엔드 ── 선택적 OpenAI API
             ↓
     MySQL 8 또는 SQLite
```

프론트엔드는 React 18, TypeScript, Vite, TanStack Query로 구성되며 백엔드는 FastAPI, Pydantic, SQLAlchemy, Alembic을 사용합니다. 개발 중에는 SQLite로 빠르게 실행할 수 있고, 여러 기기 또는 상시 서버 환경에서는 MySQL 8을 사용하도록 설계되어 있습니다.

학습 세션, 학습 답안, 모의고사와 오답 노트는 로그인 계정의 `user_id`로 분리됩니다. 일반 사용자와 admin 모두 기본 학습 화면에서는 자신이 푼 기록만 조회·수정할 수 있고, 다른 사용자의 세션이나 모의고사 ID로 직접 접근해도 조회되지 않습니다. PWA는 설치형 실행 화면을 제공하지만 문제/API/인증 응답은 오프라인 캐시에 저장하지 않습니다.

학습 도중 사이드 메뉴로 이동하면 현재 진행 상황을 처리하는 확인 창이 열립니다. `저장 후 나가기`는 지금까지 답한 문제만 하나의 학습 묶음으로 확정해 오답 노트에 반영하고, `저장하지 않고 나가기`는 학습 묶음을 폐기하며, `계속 학습`은 현재 화면으로 돌아갑니다. 새로고침이나 탭 닫기는 브라우저 기본 이탈 경고로 보호합니다.

> 실제 실행 점검과 발견된 핵심 이슈는 [Runtime status](docs/runtime-status.md)에 계속 기록합니다.

> AWS DEA-C01 1차 적용 범위와 검증 상태는 [AWS DEA-C01 phase 1](docs/aws-dea-c01-phase1.md)을 참조하세요.

실제 AWS 데이터는 `data/processed/dataset/aws-dea-c01/`에 복사하면 됩니다. 가져오기 스크립트는 이 경로를 기본으로 사용합니다.

데이터는 무작위 일부만 저장하지 않고 검증된 DEA-C01 문제 전체를 적재합니다. 무작위 선택은 학습 또는 모의고사 세션을 생성할 때만 수행되며 자세한 흐름은 [AWS DEA-C01 phase 1](docs/aws-dea-c01-phase1.md#데이터를-받은-뒤-진행되는-과정)에 정리되어 있습니다.

AWS DEA-C01을 우선 지원하고 향후 다른 자격증 데이터셋을 추가할 수 있도록 설계한 개인용 문제은행입니다. 도메인 학습, 무작위 학습, 단일·복수 선택 즉시 채점, 오답 노트, 시간 제한 모의고사, 결과 검토, 관리자 문제 관리, JSONL 가져오기와 선택적 AI 해설을 제공합니다. 채점과 합격 판정의 최종 권한은 백엔드에 있습니다.

화면은 자격증 선택 대시보드, 학습, 모의고사, 결과/문항 검토, 오답 노트, `/admin` 관리 화면으로 구성됩니다. React/TypeScript/Vite 클라이언트, FastAPI/Pydantic/SQLAlchemy/Alembic API, MySQL 8을 사용합니다.

## 사전 요구사항

Docker 방식은 Docker Desktop과 Compose가 필요합니다. 직접 실행 방식은 Windows, Python 3.12, Node.js 22/npm, MySQL 8, Git이 필요합니다. 기본 포트는 프론트엔드 5173, API 8000, MySQL 3306입니다.

## Docker Compose 실행

```powershell
Copy-Item .env.example .env
# .env의 비밀번호를 변경합니다.
docker compose up --build
```

브라우저에서 `http://localhost:5173`, API 문서에서 `http://localhost:8000/docs`를 엽니다. 중지는 `docker compose down`입니다. DB 볼륨까지 삭제하는 `docker compose down -v`는 데이터가 영구 삭제되므로 백업 후에만 사용하십시오.

## Windows 직접 실행

```powershell
Set-ExecutionPolicy -Scope Process Bypass
Copy-Item .env.example .env
.\scripts\setup.ps1
.\scripts\start-all.ps1
```

중지는 `.\scripts\stop-all.ps1`입니다. 각 서버 로그를 직접 보려면 서로 다른 PowerShell 창에서 `.\scripts\start-backend.ps1`와 `.\scripts\start-frontend.ps1`를 실행하십시오. 자세한 내용은 [Windows setup](docs/windows-setup.md)을 참고하십시오.

## 데이터베이스 연결 방법

백엔드는 프로젝트 루트의 `.env`를 읽어 DB에 연결합니다. 실제 비밀번호와 API 키가 들어 있는 `.env`는 `.gitignore`에 포함되어 있으므로 Git에 커밋하지 마십시오. 저장소에는 변수 이름만 제공하는 `.env.example`만 올립니다.

애플리케이션이 소유하는 테이블은 모두 `exam_` 접두사를 사용합니다. 예: `exam_questions`, `exam_users`, `exam_auth_sessions`. Alembic 자체 상태 테이블인 `alembic_version`과 같은 DB에 존재하는 다른 시스템의 테이블은 이 규칙 및 마이그레이션 대상에서 제외합니다.

### SQLite로 로컬 실행

별도 DB 서버 없이 개발하려면 다음 값만 사용합니다.

```env
DATABASE_URL=sqlite:///./cert_exam.db
```

마이그레이션을 실행하면 `backend/cert_exam.db`가 생성됩니다. SQLite는 한 PC에서 개발하거나 시험하는 용도에 적합하며, 여러 서버 인스턴스나 여러 기기에서 공유하는 운영 DB로는 권장하지 않습니다.

### 외부 MySQL 서버 연결

1. `.env.example`을 프로젝트 루트의 `.env`로 복사합니다.

```powershell
Copy-Item .env.example .env
```

2. MySQL 서버에서 DB와 전용 계정을 생성합니다. 아래 `BACKEND_HOST`에는 백엔드가 접속해 오는 IP 또는 허용할 호스트를 사용합니다. 로컬 MySQL이면 `localhost`를 사용할 수 있습니다.

```sql
CREATE DATABASE cert_exam CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'cert_exam_user'@'BACKEND_HOST' IDENTIFIED BY '강력한-비밀번호';
GRANT ALL PRIVILEGES ON cert_exam.* TO 'cert_exam_user'@'BACKEND_HOST';
FLUSH PRIVILEGES;
```

3. 프로젝트 루트 `.env`에 연결 정보를 입력합니다.

```env
DATABASE_HOST=db.example.internal
DATABASE_PORT=3306
DATABASE_NAME=cert_exam
DATABASE_USER=cert_exam_user
DATABASE_PASSWORD=실제-비밀번호
```

네 개의 `DATABASE_HOST`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`가 모두 설정되면 백엔드가 비밀번호를 URL 인코딩하고 `DATABASE_URL`을 자동으로 구성합니다. 따라서 이 방식에서는 `DATABASE_URL`에 비밀번호를 중복해서 적지 않아도 됩니다.

연결 URL 하나만 제공하는 호스팅 서비스라면 개별 `DATABASE_*` 값을 비워 두고 다음처럼 설정할 수도 있습니다.

```env
DATABASE_URL=mysql+pymysql://cert_exam_user:URL인코딩된-비밀번호@DB주소:3306/cert_exam?charset=utf8mb4
```

비밀번호에 `@`, `:`, `/`, `#` 같은 문자가 있으면 직접 작성하는 `DATABASE_URL`에서는 반드시 URL 인코딩해야 합니다. DB 서버의 3306 포트는 인터넷 전체가 아니라 백엔드 서버 IP에만 허용하는 것이 안전합니다.

4. 백엔드 디렉터리에서 스키마 마이그레이션을 적용합니다.

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
Set-Location ..
```

DB 계정에는 최초 마이그레이션에 필요한 테이블·인덱스·외래 키 생성 권한이 있어야 합니다. 기존 업무용 DB를 함께 사용하는 경우에는 별도 DB 또는 스키마와 전용 계정을 사용하십시오.

5. 백엔드를 재시작하고 연결 상태를 확인합니다.

```powershell
.\scripts\start-backend.ps1
Invoke-RestMethod http://localhost:8000/api/v1/health
```

`{"status":"ok"}`가 반환된 뒤 `http://localhost:8000/docs`에서 자격증 조회 API를 확인합니다. 연결 실패 시 MySQL 실행 상태, 방화벽, 허용 호스트, 계정 권한과 포트 번호를 먼저 점검하십시오.

### 배포 서버에서 비밀정보 저장

새 서버가 만들어질 때 자동으로 같은 DB에 연결하려면 `.env`를 Git에 올리는 대신 배포 플랫폼의 Environment Variables 또는 Secrets에 위 값을 한 번 등록합니다. 플랫폼은 시작할 때 값을 백엔드 프로세스에 주입하므로 재배포나 서버 재시작 때 사람이 다시 연결할 필요가 없습니다. DB 비밀번호, `OPENAI_API_KEY`, `INITIAL_ADMIN_PASSWORD`는 프론트엔드 환경변수나 브라우저 코드에 넣지 않습니다.

`OPENAI_API_KEY`와 모델 이름은 선택 사항입니다. 비어 있어도 문제 조회·학습·채점·모의고사는 동작하며, 새 AI 해설 생성 요청만 설정 필요 응답을 반환합니다. 키는 브라우저, API 응답 또는 로그에 노출하지 않습니다.

## 로그인과 관리자 계정

공개 회원가입은 제공하지 않습니다. 시스템 admin 계정 하나만 환경변수로 생성하고, 이후 일반 학습자 계정은 로그인한 admin이 관리자 화면에서 등록합니다. 일반 계정은 관리자 메뉴가 보이지 않으며 `/admin` 화면과 `/api/v1/admin/*` API 모두 접근할 수 없습니다.

`.env`에 다음 값을 설정한 뒤 마이그레이션과 서버 재시작을 수행합니다.

```dotenv
AUTH_REQUIRED=true
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=충분히-긴-초기-비밀번호
AUTH_SESSION_MINUTES=30
AUTH_COOKIE_SECURE=false
PASSKEY_RP_ID=localhost
PASSKEY_RP_NAME=합격비서
PASSKEY_CHALLENGE_MINUTES=5
AUTH_RATE_LIMIT_REQUESTS=10
AUTH_RATE_LIMIT_WINDOW_SECONDS=60
```

최초 admin은 DB에 admin 역할 계정이 하나도 없을 때 첫 로그인 요청에서 생성됩니다. 이후에도 admin 로그인 비밀번호는 DB 해시가 아니라 서버의 `INITIAL_ADMIN_PASSWORD`를 항상 기준으로 사용합니다. 값을 변경한 경우 백엔드 서버를 재시작하면 새 비밀번호가 바로 적용됩니다. `INITIAL_ADMIN_PASSWORD`가 비어 있으면 admin으로 로그인할 수 없습니다.

로컬 HTTP 개발에서는 `AUTH_COOKIE_SECURE=false`를 사용합니다. HTTPS로 외부에 배포할 때는 반드시 `AUTH_COOKIE_SECURE=true`로 바꾸십시오. 로그인 세션은 원문 토큰이 아니라 SHA-256 해시로 DB에 저장되고, 브라우저에는 JavaScript로 읽을 수 없는 `HttpOnly` 쿠키로 전달됩니다. 세션 유효시간은 기본 30분이며, 백엔드 프로세스가 시작될 때 기존 활성 세션을 모두 폐기하므로 서버 재시작 후에는 모든 사용자가 로그인 화면부터 다시 시작합니다. 이 동작은 `python -m app.run`과 `uvicorn app.main:app` 실행 모두에 적용됩니다.

admin은 항상 활성화되는 시스템 계정이므로 `관리 → 계정 관리` 목록에 표시되지 않으며 비활성화할 수도 없습니다. 이 화면에서는 일반 학습자 계정만 등록·활성화·비활성화할 수 있고, 일반 계정 비밀번호는 DB의 PBKDF2 해시로 관리합니다.

일반 계정은 관리자가 발급한 임시 비밀번호로 최초 한 번 로그인한 뒤 현재 기기의 지문, Face ID, Windows Hello 또는 화면 잠금으로 Passkey를 등록해야 합니다. 등록 완료 전에는 Passkey API와 로그아웃 외의 보호 API가 모두 거절됩니다. 이후에는 아이디·비밀번호 입력 없이 `Passkey로 로그인`을 사용합니다. 새 기기의 Passkey 인증이 성공한 시점에만 기존 활성 세션이 폐기되므로, 단순 비밀번호 입력이나 실패한 인증으로 기존 기기가 로그아웃되지 않습니다. 기기를 분실하거나 교체할 때는 admin이 계정 목록의 `기기 초기화`를 실행한 뒤 새 기기에서 다시 등록합니다. 초기화는 계정과 학습 기록을 보존하고 Passkey 및 로그인 세션만 제거합니다.

Passkey는 Android의 지문/화면 잠금, iOS·iPadOS의 Face ID/Touch ID/기기 암호, Windows Hello를 지원합니다. 웹 애플리케이션은 특정 생체 수단을 강제하지 않으며 운영체제가 허용한 인증 수단을 표시합니다. 모바일에서는 HTTPS, 최신 브라우저, 정확한 `PASSKEY_RP_ID`가 필요합니다. 현재 서버 호환성을 위해 백엔드 WebAuthn 패키지는 `2.8.0`으로 고정되어 있습니다.

운영 HTTPS 환경에서는 실제 접속 주소에 맞춰 다음처럼 설정합니다. `PASSKEY_RP_ID`에는 스킴이나 포트를 넣지 않습니다.

```dotenv
FRONTEND_ORIGIN=https://exam.example.com
AUTH_COOKIE_SECURE=true
PASSKEY_RP_ID=exam.example.com
PASSKEY_RP_NAME=합격비서
```

PWA는 Chrome 주소창의 설치 아이콘 또는 브라우저 메뉴의 `앱 설치`로 설치합니다. 서비스 워커는 화면 셸과 정적 자산만 캐시하며 `/api/*` 요청과 인증·문제 데이터는 캐시하지 않습니다. localhost 이외 환경에서는 HTTPS가 필요합니다.

PWA 설치 시 브라우저가 `위험한 사이트`로 경고하는 것은 manifest나 앱 아이콘만으로 해제할 수 없습니다. 인증서 전체 체인과 도메인 일치 여부, HTTP로 되돌아가는 리다이렉트·혼합 콘텐츠, 도메인의 Safe Browsing 상태를 확인해야 합니다. 제공된 Nginx 예시는 동일 출처 CSP와 정적 HTML 무캐시 정책을 포함하지만, 도메인이 차단 목록에 등재된 경우에는 Google Search Console/Safe Browsing 검토 요청이 별도로 필요합니다.

## 데이터 검증과 가져오기

실제 전처리 데이터는 `data/processed/dataset/`에 두십시오. 저장소의 `data/samples/`는 실제 시험 문항이 아닌 합성 샘플입니다. 먼저 쓰기 없는 검증을 실행한 다음 가져옵니다.

```powershell
.\scripts\import-dataset.ps1 -Path ".\data\processed\dataset" -Mode "dry-run"
.\scripts\import-dataset.ps1 -Path ".\data\processed\dataset" -Mode "partial"
```

전체 원자적 가져오기는 `-Mode "strict"`를 사용합니다. 내부의 정확한 CLI는 `python -m app.cli import-dataset --path <ABSOLUTE_PATH> --mode <dry-run|strict|partial>`입니다. 포맷과 모드의 의미는 [Dataset format](docs/dataset-format.md)에 있습니다. 원본과 기존 정답 버전은 덮어쓰지 않습니다.

## 테스트와 품질 검사

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest
Set-Location ..\frontend
npm run lint
npx tsc -b --pretty false
npm test
npm run test:auth-coverage
npm run build
Set-Location ..
```

CI는 실제 `.env`나 OpenAI 키 없이 동일 검사를 수행합니다. 테스트는 외부 AI를 호출하지 않습니다.

## Git 배포

```bash
git init
git add .
git commit -m "Initial certification exam app"
git branch -M main
git remote add origin <REMOTE_URL>
git push -u origin main
```

자세한 배포 주의사항은 [Git deployment](docs/git-deployment.md), 시스템 책임은 [Architecture](docs/architecture.md), DB 원칙은 [Database](docs/database.md), API 개요는 [API](docs/api.md)를 참고하십시오.

## 자주 발생하는 오류

- MySQL 연결 실패: 서비스 실행 여부, 3306 충돌, 사용자 호스트 권한, `DATABASE_URL` 인코딩을 확인합니다.
- Alembic 오류: 명령을 `backend`에서 실행했는지와 DB 계정의 DDL 권한을 확인합니다.
- PowerShell 실행 차단: 현재 창에서 `Set-ExecutionPolicy -Scope Process Bypass`를 실행합니다.
- 프론트엔드 API 실패: `VITE_API_BASE_URL`과 `FRONTEND_ORIGIN`을 확인하고 Vite를 재시작합니다.
- 가져오기 실패: 먼저 `dry-run`을 실행하고 생성된 검증/행 오류를 수정합니다. 소스 파일을 자동 수정하지 않습니다.
- AI 해설 실패: 키와 모델 환경 변수를 설정하고 서버를 재시작합니다. 학습·채점은 계속 사용할 수 있습니다.

PDF 레이아웃 파싱은 이 프로젝트 범위가 아닙니다. 향후 PDF 파이프라인은 지정된 dataset 패키지를 생성해 `data/processed/dataset/`에 놓으면 현재 검증·가져오기 경계에 연결됩니다.

## CentOS 7 · Nginx 운영 배포

운영 환경에서는 Nginx가 React 정적 파일을 제공하고 `/api/v1/*` 요청을 `127.0.0.1:8000`의 FastAPI로 전달합니다. 프론트엔드는 `VITE_API_BASE_URL=/api/v1`로 빌드하며, 로컬 개발에서는 `http://localhost:8000/api/v1`을 계속 사용할 수 있습니다. 환경파일, Nginx, systemd 설정과 HTTP에서 HTTPS로 전환할 때의 쿠키 설정은 [CentOS 7 + Nginx 배포 안내](docs/centos7-nginx-deployment.md)를 참고하십시오.
