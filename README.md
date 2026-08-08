# Certification Exam App

## 프로젝트 한눈에 보기

Certification Exam App은 자격증 문제를 반복 학습하고 실전 모의고사를 치를 수 있는 개인용 웹 문제은행입니다. 현재 1차 지원 범위는 **AWS Certified Data Engineer - Associate(DEA-C01)**이며, 문제·선택지·정답 이력을 데이터베이스에 보존하고 채점과 합격 판정은 백엔드가 담당합니다.

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

시스템은 다음과 같이 구성됩니다.

```text
React/TypeScript 웹 클라이언트
             ↓ HTTP API
FastAPI 백엔드 ── 선택적 OpenAI API
             ↓
     MySQL 8 또는 SQLite
```

프론트엔드는 React 18, TypeScript, Vite, TanStack Query로 구성되며 백엔드는 FastAPI, Pydantic, SQLAlchemy, Alembic을 사용합니다. 개발 중에는 SQLite로 빠르게 실행할 수 있고, 여러 기기 또는 상시 서버 환경에서는 MySQL 8을 사용하도록 설계되어 있습니다.

현재 사용자 계정별 데이터 분리는 구현되어 있지 않습니다. 학습 기록, 모의고사와 오답 노트는 연결된 DB를 사용하는 단일 사용자 기준이며, 인터넷에 공개할 때는 최소한 개인 접근 제어 또는 사설 네트워크를 추가해야 합니다. PWA 설치와 오프라인 학습은 아직 지원하지 않습니다.

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

새 서버가 만들어질 때 자동으로 같은 DB에 연결하려면 `.env`를 Git에 올리는 대신 배포 플랫폼의 Environment Variables 또는 Secrets에 위 값을 한 번 등록합니다. 플랫폼은 시작할 때 값을 백엔드 프로세스에 주입하므로 재배포나 서버 재시작 때 사람이 다시 연결할 필요가 없습니다. DB 비밀번호, `OPENAI_API_KEY`, `ADMIN_ACCESS_KEY`는 프론트엔드 환경변수나 브라우저 코드에 넣지 않습니다.

`OPENAI_API_KEY`와 모델 이름은 선택 사항입니다. 비어 있어도 문제 조회·학습·채점·모의고사는 동작하며, 새 AI 해설 생성 요청만 설정 필요 응답을 반환합니다. 키는 브라우저, API 응답 또는 로그에 노출하지 않습니다. `ADMIN_ACCESS_KEY` 방식은 개인 로컬 사용을 위한 최소 보호이며 인터넷 공개용 완전한 인증이 아닙니다.

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
