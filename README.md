# Certification Exam App

> 실제 실행 점검과 발견된 핵심 이슈는 [Runtime status](docs/runtime-status.md)에 계속 기록합니다.

> AWS DEA-C01 1차 적용 범위와 검증 상태는 [AWS DEA-C01 phase 1](docs/aws-dea-c01-phase1.md)을 참조하세요.

실제 AWS 데이터는 `data/processed/dataset/aws-dea-c01/`에 복사하면 됩니다. 가져오기 스크립트는 이 경로를 기본으로 사용합니다.

데이터는 무작위 일부만 저장하지 않고 검증된 DEA-C01 문제 전체를 적재합니다. 무작위 선택은 학습 또는 모의고사 세션을 생성할 때만 수행되며 자세한 흐름은 [AWS DEA-C01 phase 1](docs/aws-dea-c01-phase1.md#데이터를-받은-뒤-진행되는-과정)에 정리되어 있습니다.

AWS DEA-C01 및 SnowPro Core COF-C02 학습을 위한 개인용 문제은행입니다. 도메인 학습, 무작위 학습, 단일·복수 선택 즉시 채점, 오답 노트, 시간 제한 모의고사, 결과 검토, 관리자 문제 관리, JSONL 가져오기와 선택적 AI 해설을 제공합니다. 채점과 합격 판정의 최종 권한은 백엔드에 있습니다.

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

## 환경 변수와 MySQL

`.env.example`을 `.env`로 복사한 뒤 DB 계정, 비밀번호, URL을 동일하게 설정합니다. `.env`는 Git에 포함되지 않습니다. 로컬 MySQL 예시:

```sql
CREATE DATABASE cert_exam CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'cert_exam_user'@'localhost' IDENTIFIED BY 'change-me';
GRANT ALL PRIVILEGES ON cert_exam.* TO 'cert_exam_user'@'localhost';
FLUSH PRIVILEGES;
```

비밀번호에 `@`, `:`, `/` 같은 문자가 있으면 `DATABASE_URL`에서 URL 인코딩하십시오. 필수 설정이 없으면 백엔드는 명확한 오류와 함께 시작을 중단합니다. 마이그레이션은 다음과 같습니다.

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
Set-Location ..
```

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
