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
3. `[3/8]` `/opt/apps/exam-releases/<run-id>-<commit>`에서 build/test. Python 가상환경 → 의존성 설치 → pip check → Ruff → mypy → pytest → npm ci → 프론트 lint → test → build → Alembic head 조회 → 릴리스 권한 고정. 각 검사 시작/완료와 소요 시간을 표시한다.
4. `[4/8]` 기존 Alembic 파일 변경 여부와 DB revision/head 비교. 불일치 시 코드 20으로 중단. migration 자동 실행 없음.
5. `[5/8]` `exam-db-backup.service` 성공 확인.
6. `[6/8]` 복구 정보 기록, backend/frontend symlink 전환, backend 재시작. **이 단계부터 운영에 반영된다.**
7. `[7/8]` backend 프로세스 작업 경로, health API, DB 상태 API, HTTPS frontend 실제 내용 확인. 재시도 중에도 진행 상황을 표시한다.
8. `[8/8]` 최근 릴리스 3개와 직전 운영 릴리스를 보존하며 오래된 릴리스 정리 후 완료 표시. 알려진 릴리스 이외의 데이터는 삭제하지 않음.

전환 전에 실패하면 기존 서비스는 유지된다. 전환 후 실패하면 `[복구]`를 표시하고 두 symlink를 이전 대상으로 복구한 뒤 재시작/검증한다. DB 복원이나 downgrade는 실행하지 않는다.

로그 예시 (숫자는 작업 순서이며 시간 기준 진행률이 아님):

```text
[3/8][build][running] 3-4 백엔드 코드 검사 (Ruff) — 시작 (운영 서비스는 계속 실행 중)
[3/8][완료] 3-4 백엔드 코드 검사 (Ruff) (0.5초)
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
| 최신 상태 | `/var/lib/exam-deploy/status.json` |
| 실행 이력 | `/var/lib/exam-deploy/history/<run-id>.json` |
| 강제 종료 복구 정보 | `/var/lib/exam-deploy/pending.json` |

운영 secret은 `/etc/exam`에 그대로 둔다. repo의 `.env` 실제 파일은 배포 아카이브에 들어갈 수 없다. `.env.example`은 허용한다. root controller는 자동으로 저장소 버전으로 교체되지 않으며, controller 업데이트는 별도 설치/승인이 필요하다.

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

구현 검증: Ubuntu에서 격리 테스트 17개, Bash/POSIX 셸 문법, Python 핵심 lint 통과. Windows에서는 symlink 권한 제한으로 트랜잭션 테스트를 실행할 수 없어 Linux에서 검증했다. 이 결과는 실제 운영 배포 성공을 의미하지 않으며, 설치 후 최초 실행/헬스체크가 별도로 필요하다.

### 2026-08-27 배포 검사 오류 수정

- 최초 운영 배포 시도는 Ruff 오류 10개로 build 단계에서 중단됐다. 운영 전환/DB 변경 없이 기존 backend가 active인 것을 확인했다.
- import 정리, 미사용 import/noqa 제거, Python 3.12+ ISO 날짜 파싱 정리. 기존 배치 실패 처리 의미를 유지하도록 classifier의 넓은 예외 처리에 한정된 설명과 `BLE001` 예외를 명시했다.
- `0001_initial.py`는 운영 마이그레이션 체크섬 보존을 위해 수정하지 않았다. 해당 파일의 import 정렬 규칙 `I001`만 예외 처리하고 다른 검사는 유지했다. 서버 원본과 byte 비교 PASS.
- 수정본 검증 PASS: Ubuntu Ruff 0.16.4 검사, mypy 31개 파일, SQLite 기반 backend 전체 테스트 88개, 배포 격리 테스트 17개, 셸 문법/배포 코드 핵심 lint, 범위 한정 독립 리뷰.
- 최초 테스트용 아카이브에 frontend/Nginx 설정이 빠져 1개 테스트가 실패했다. 참조 설정 파일을 포함한 후 전체 88개 PASS. 운영 데이터나 외부 AI는 사용하지 않았다.
- 이 수정본의 실제 운영 재배포와 frontend 전체 검사는 NOT_RUN. GitHub 반영과 설치된 controller 업데이트 후 실제 배포 검증이 필요하다.

실제 앱의 Ruff/mypy/pytest/frontend lint/test/build가 실패하면 배포가 중단된다. 기존 오류를 숨기거나 검사를 우회하지 않는다. Python 의존성은 기존 pyproject의 범위 지정 방식을 따르므로 완전한 재현 빌드를 위해 별도 lockfile 도입 검토가 남아 있다. npm은 package-lock 기반 `npm ci`를 사용한다. GitHub CI 성공을 API로 조회하는 기능은 없지만 동일 핵심 검사를 릴리스 안에서 직접 실행한다. 외부 백업과 알림 채널은 별도 구성 사항이다.
