# Ubuntu 승인형 배포

## 실행

설치가 끝난 신규 서버에서 `bhadmin`으로 실행:

```bash
sudo /usr/local/sbin/exam-deploy
```

인자는 받지 않으며 고정 저장소 `https://github.com/byeonghyeon2/exam.git`의 `main`만 배포한다. 로컬 변경은 먼저 검증/커밋/push해야 한다. 설치 자체가 push하거나 자동 배포하지는 않는다.

운영 작업 폴더에 직접 `git pull`하는 대신 별도 bare 저장소에서 fetch하고 정확한 커밋을 새 릴리스로 추출한다. `/opt/apps/exam` 원본 체크아웃과 `.env`는 변경하지 않는다. 서버 원본에 미반영 변경이 있으면 중단한다.

## 설치

검토한 `deploy/ubuntu` 디렉터리 전체를 신규 서버로 전송한 후, `bhadmin`에서:

```bash
sudo bash /path/to/deploy/ubuntu/install.sh
```

설치기는 root 소유 실행 파일, 수동 실행 systemd unit, 전용 `exam-build` 계정과 backend drop-in을 설치한다. 최초 `/opt/apps/exam-current`는 기존 `/opt/apps/exam`을 가리키므로 설치만으로 서비스를 재시작하거나 새 코드를 배포하지 않는다. 임시 전체 NOPASSWD는 필수 조건이 아니며, 일반 sudo 비밀번호로 실행 가능하다.

## 동작과 계약

배포 잠금을 획득한 뒤 다음 8단계를 실행한다. 중복 실행은 종료 코드 75로 거절한다.

1. `[1/8]` 사전 점검: 중단된 전환, 운영 경로, 고정 origin, 작업 트리, 디스크, 서비스 확인.
2. `[2/8]` main fetch, 현재/대상 커밋 표시, fast-forward 확인.
3. `[3/8]` `/opt/apps/exam-releases/<run-id>-<commit>`에서 실행 준비/빌드. Python 의존성 재사용(변경 시만 새 환경 설치·pip check) → Node 의존성 복사 재사용(변경 시만 npm ci) → 프론트 build → 백엔드 import 확인 → Alembic head 조회 → 릴리스 권한 고정. 전체 lint/type/test는 서버에서 반복하지 않고 기존 GitHub CI에서 수행한다.
4. `[4/8]` 기존 Alembic 파일 변경 여부와 DB revision/head 비교. 불일치 시 코드 20으로 중단. migration 자동 실행 없음.
5. `[5/8]` `exam-db-backup.service` 성공 확인.
6. `[6/8]` 복구 정보 기록, backend/frontend symlink 전환, backend 재시작. **이 단계부터 운영에 반영된다.**
7. `[7/8]` backend 프로세스 작업 경로, health API, DB 상태 API, HTTPS frontend 실제 내용 확인. 재시도 중에도 진행 상황을 표시한다.
8. `[8/8]` 최근 릴리스 3개와 직전 운영 릴리스를 보존하며 오래된 릴리스 정리 후 완료 표시. 알려진 릴리스 이외의 데이터는 삭제하지 않음.

전환 전에 실패하면 기존 서비스는 유지된다. 전환 후 실패하면 `[복구]`를 표시하고 두 symlink를 이전 대상으로 복구한 뒤 재시작/검증한다. DB 복원이나 downgrade는 실행하지 않는다.

로그 예시 (숫자는 작업 순서이며 시간 기준 진행률이 아님):

```text
[3/8][build][running] 3-1 Python 의존성 변경 없음 — 기존 환경 재사용 (설치 생략)
[3/8][build][running] 3-4 Node 의존성 변경 없음 — 복사 재사용 (설치 생략) — 시작 (운영 서비스는 계속 실행 중)
[6/8][activate][running] 백엔드 재시작 — 짧은 접속 중단 및 재로그인이 발생할 수 있음
[8/8][complete][succeeded] 배포 완료 — 운영 검증 통과, DB 스키마 변경 없음
```

주석은 스크립트 내부 설명이며 실행 화면에는 진행 로그가 나온다. 설치기는 별도로 `[설치 1/4]`~`[설치 4/4]`를 표시한다. 코드 업데이트만으로 설치된 controller가 교체되지는 않으므로, 로그 개선 적용에도 `install.sh` 재실행이 필요하다.

최초 전환과 각 backend 재시작 때 짧은 중단과 앱 정책에 따른 로그인 세션 초기화가 발생한다. 무중단 rolling 배포는 아니다.

## 경로

| 목적 | 경로 |
|---|---|
| 셸 진입점 | `/usr/local/sbin/exam-deploy` |
| root controller | `/usr/local/lib/exam-deploy/exam_deploy.py` |
| 원본 서버 소스(보존) | `/opt/apps/exam` |
| 빌드 전용 저장소/캐시 | `/var/lib/exam-build` |
| backend current | `/opt/apps/exam-current` |
| frontend current | `/var/www/apps/exam/current` |
| 릴리스 | `/opt/apps/exam-releases` |
| 읽기 전용 Python 의존성 환경 | `/opt/apps/exam-python-envs/<key>-<run-id>` |
| 빌드 전 Node 의존성 원본 | `<release>/.node-dependencies` |
| 최신 상태 | `/var/lib/exam-deploy/status.json` |
| 실행 이력 | `/var/lib/exam-deploy/history/<run-id>.json` |
| 강제 종료 복구 정보 | `/var/lib/exam-deploy/pending.json` |

운영 secret은 `/etc/exam`에 그대로 둔다. repo의 `.env` 실제 파일은 배포 아카이브에 들어갈 수 없다. `.env.example`은 허용한다. root controller는 자동으로 저장소 버전으로 교체되지 않으며, controller 업데이트는 별도 설치/승인이 필요하다.

## 경량 배포 설계와 구 서버 대비

목표는 의존성 파일이 같은 일반 코드 수정에서 pip/npm 설치와 전체 검사를 반복하지 않는 것이다. 변경 범위는 배포 도구/설치기/테스트/이 문서이며, 앱 API·DB 스키마·프로젝트 의존성은 바꾸지 않는다.

구 서버 실제 쉘은 저장소에 없고 현재 SSH 키도 제거돼 원문/소요 시간 비교는 미확인이다. 확인 가능한 `centos7-nginx-deployment.md`의 프론트 절차는 `npm ci → npm run build → rsync`다. 다음 비교는 해당 문서와 Ubuntu controller를 기준으로 하며 구 쉘 내부를 추정하지 않는다.

| 작업 | 처음 만든 Ubuntu 배포 | 경량 배포 |
|---|---|---|
| Python 설치 | 매 배포 새 venv + 개발 도구까지 설치 | pyproject/Python 변경 시만 운영 의존성 설치 |
| Node 설치 | 매 배포 npm ci | manifest/lock/실행환경 변경 시만 설치, 나머지는 복사 |
| lint·mypy·전체 테스트 | 서버에서 매번 실행 | 기존 GitHub CI에서 실행, 서버에서는 제외 |
| 프론트 build / 백엔드 import 확인 | 빌드 + 전체 검사 | 운영 산출물 빌드 + 간단한 로딩 확인 |
| DB 버전·백업·헬스체크·롤백 | 수행 | 데이터 보호와 실패 복구를 위해 유지 |

### 의존성 재사용 계약

- 최초 경량 배포는 재사용할 새 형식의 환경/스냅샷이 없어 한 번 설치한다. 그 다음부터 동일 입력이면 설치를 생략한다.
- Python 키는 `pyproject.toml` 전체와 Python 버전/플랫폼을 포함한다. 가상환경은 고정된 최종 경로에서 만들고 이동하지 않는다. 운영 의존성만 설치하며 앱은 작업 경로의 소스를 `python -m app.run`으로 실행한다. 현재 `requires-python >=3.12` 형태를 검증하고, 동적 의존성·배포 패키지 entry point·직접 URL/로컬 의존성 등 지원하지 않는 계약은 자동 진행하지 않는다.
- Python 설치에는 `-I`를 사용하고, 설치 완료 후 root 소유로 고정한 뒤 앱 코드를 실행한다. 재사용 환경에 쓰기 권한을 주지 않는다. 후보 `.venv`가 선택한 환경을 가리키는지도 재검증한다.
- Node 키는 package.json/package-lock/.npmrc와 Node/npm/플랫폼을 포함한다. workspace, 설치 훅, overrides, shrinkwrap, 로컬/link 의존성, 지원하지 않는 lock 형식에는 재사용을 적용하지 않는다.
- Node는 설치 직후 **앱 빌드 전** 원본 스냅샷을 root 소유로 보존한다. 다음 릴리스는 원본을 복사해 빌드하며, hardlink나 공유 쓰기 디렉터리는 사용하지 않는다. 빌드 후 변경된 node_modules는 재사용하지 않는다.
- 앱 빌드의 HOME은 후보의 임시 `.build-home`이며 영구 빌드 홈을 수정할 수 없다. 빌드 후 임시 HOME/node_modules는 삭제한다. 원본 스냅샷은 릴리스 보관/정리 정책을 따른다.
- Python 환경은 보관 중인 모든 릴리스가 더 이상 참조하지 않을 때만 정리한다. 새 환경 설치 실패 시 해당 미완성 환경만 정리하며 기존 환경은 유지한다. 강제 종료로 남은 식별 불가능한 환경은 자동 삭제하지 않는다.

배포 명령은 **CI 결과를 자동 조회하거나 기다리지 않는다**. 운영자는 CI 성공을 확인하고 실행해야 한다. 프론트 빌드에는 기존 `tsc`가 포함되며 빌드/import/schema/backup/health 실패 시 배포를 중단하거나 복구한다. 무중단/성능 동일 보장은 아니며 실제 운영 전환 및 속도 비교는 별도 검증 대상이다.

## 상태 및 오류

```bash
cat /var/lib/exam-deploy/status.json
systemctl status exam-deploy.service --no-pager
sudo journalctl -u exam-deploy.service -n 100 --no-pager
```

직접 셸로 실행하면 진행 로그는 터미널에 표시된다. systemd로 실행하면 journal에 기록된다.

```bash
sudo systemctl start --no-block exam-deploy.service
```

`status.json`은 `schema_version=1`, `run_id`, `status`, `phase`, `target_commit`, `previous_release`, `candidate_release`, 시작/갱신 시각을 포함한다. 상태는 `running`, `noop`, `succeeded`, `blocked`, `failed`, `rolled_back`, `rollback_failed`이다. 종료 코드: 0=성공/noop, 1=실패(롤백 성공도 배포 자체는 실패), 2=롤백 검증 실패, 20=DB 검토 필요, 21=미반영 서버 변경, 22=중단된 전환 수동 복구 필요, 75=중복 실행, 130=인터럽트.

정전/SIGKILL은 프로그램이 포착할 수 없다. 전환 전 `pending.json`을 기록하며, 남아 있으면 다음 배포를 차단한다. 관리자는 해당 파일의 이전 두 경로와 현재 링크/서비스를 확인한 후 이전 링크로 복원하고 backend 재시작/HTTPS 검증을 수행한다. 정상 복구 확인 전 pending 파일이나 릴리스는 삭제하지 않는다.

## 미래 관리 UI 경계

- 이번 작업에는 웹 UI/HTTP API가 포함되지 않는다.
- 관리 UI는 인증된 관리자만 고정 작업 `exam-deploy.service` 시작을 요청해야 한다.
- root shell, 명령 문자열, ref, repository URL, 경로를 HTTP 입력으로 받지 않는다.
- UI 자체에는 일반 sudo나 Docker socket 권한을 주지 않는다. 별도 최소권한 broker/Polkit 정책 검토 후 연결한다.
- 상태 JSON은 읽기 전용으로 노출하고, 세션 인증/CSRF/감사 로그/중복 클릭 제어가 필요하다.
- DB migration 승인은 별도 작업이며, 배포 버튼으로 권한을 확장하지 않는다.

## 검증과 한계

격리 테스트: `python -m unittest discover -s deploy/ubuntu/tests -v` (Linux, 운영 서비스/DB 호출 없음).

구현 검증: Ubuntu에서 격리 테스트 27개, Bash/POSIX 셸 문법, Python 핵심 lint 통과. Windows에서는 symlink 권한 제한으로 트랜잭션 테스트를 실행할 수 없어 Linux에서 검증했다. 이 결과는 실제 운영 배포 성공을 의미하지 않으며, 설치 후 최초 실행/헬스체크가 별도로 필요하다.

### 2026-08-27 경량화 검증

- PASS: 의존성 키 변경, Python 최초 설치/재사용, 설치 실패 정리, 환경 소유권/마커 검사, Node 원본 복사와 변조 격리, 지원하지 않는 설치 계약, 참조 중 환경 보존, 기존 백업/스키마 차단/롤백 등 27개 회귀 테스트.
- PASS: 별도 임시 폴더에서 실제 운영용 Python 의존성만 설치한 뒤 앱 import와 프론트 build 성공. 두 번째 실행에서 pip/venv/npm ci 호출이 없는 것을 확인했다.
- 측정: 동일 소스의 의존성 준비·빌드·import 구간은 최초 설치 **167.70초**, 재사용 **72.49초**. 재사용 실행의 Node 복사 3.5초, 프론트 빌드 48.7초. 원본 쉘 또는 전체 운영 배포 시간과의 비교는 아니다.
- PASS: 집중 보안 리뷰에서 발견한 source import를 통한 캐시 오염 및 빌드 후 node_modules 오염 전파를 수정했다. Python `-I`, 임시 HOME, 빌드 전 root 고정 스냅샷, 부모 디렉터리 권한 고정으로 재검토 통과.
- 최초 실설치 검증은 정상 Python 별칭 링크를 과도하게 거절해 FAIL이었다. 동일 시스템 Python으로 해석되는 bin 링크만 허용하도록 수정한 후 cold/warm 검증 PASS.
- NOT_RUN: 신규 캐시를 사용하는 실제 운영 전환·systemd 권한 통합 검증. 임시 실빌드는 bhadmin으로 실행하고 root 소유권 작업은 대체했으므로 해당 권한 검증을 대신하지 않는다. 운영 서비스/DB/백업 정책은 변경하지 않았다.

### 2026-08-27 배포 검사 오류 수정

- 최초 운영 배포 시도는 Ruff 오류 10개로 build 단계에서 중단됐다. 운영 전환/DB 변경 없이 기존 backend가 active인 것을 확인했다.
- import 정리, 미사용 import/noqa 제거, Python 3.12+ ISO 날짜 파싱 정리. 기존 배치 실패 처리 의미를 유지하도록 classifier의 넓은 예외 처리에 한정된 설명과 `BLE001` 예외를 명시했다.
- `0001_initial.py`는 운영 마이그레이션 체크섬 보존을 위해 수정하지 않았다. 해당 파일의 import 정렬 규칙 `I001`만 예외 처리하고 다른 검사는 유지했다. 서버 원본과 byte 비교 PASS.
- 수정본 검증 PASS: Ubuntu Ruff 0.16.4 검사, mypy 31개 파일, SQLite 기반 backend 전체 테스트 88개, 배포 격리 테스트 17개, 셸 문법/배포 코드 핵심 lint, 범위 한정 독립 리뷰.
- 최초 테스트용 아카이브에 frontend/Nginx 설정이 빠져 1개 테스트가 실패했다. 참조 설정 파일을 포함한 후 전체 88개 PASS. 운영 데이터나 외부 AI는 사용하지 않았다.
- 이 수정본의 실제 운영 재배포와 frontend 전체 검사는 NOT_RUN. GitHub 반영과 설치된 controller 업데이트 후 실제 배포 검증이 필요하다.

Python 의존성은 기존 pyproject의 범위 지정 방식을 따르므로 완전한 재현 빌드를 위한 lockfile은 아직 없다. 동일 manifest는 검증된 기존 환경을 재사용하므로 패키지 최신 버전을 매 배포 자동 설치하지 않는다. npm은 변경 시 package-lock 기반 `npm ci`를 사용한다. 외부 백업과 알림 채널은 별도 구성 사항이다.
