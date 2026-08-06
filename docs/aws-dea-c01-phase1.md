# AWS DEA-C01 phase 1

## 범위

- 1차 개발의 활성 자격증은 `DEA-C01` 하나다.
- SnowPro Core 데이터는 가져오기에서 제외하고 공개 API 목록에도 노출하지 않는다.
- PDF 분석이나 신규 문제 생성은 수행하지 않는다.
- 입력은 `data/processed/dataset/aws-dea-c01/`의 전처리 완료 패키지만 사용한다.

## 데이터를 받은 뒤 진행되는 과정

데이터 적재 단계에서는 문제를 무작위로 일부만 추출하지 않는다. 검증을 통과한 DEA-C01 문제를 모두 MySQL에 저장하고, 실제 학습 세션이나 모의고사를 만들 때 DB의 출제 가능 문제 풀에서 문제를 선택한다.

```text
데이터 파일 배치
  → 패키지와 JSONL 검증(dry-run)
  → 관리자 확인
  → MySQL 전체 적재(strict)
  → 미분류 문제 분류
  → 출제 가능 문제 풀 확정
  → 학습/모의고사 시작 시 문제 선택
```

### 1. 데이터 파일 배치

사용자가 아래 폴더에 전처리 완료 파일을 복사한다.

```text
data/processed/dataset/aws-dea-c01/
```

원본 파일은 수정하거나 삭제하지 않는다. PDF를 다시 분석하거나 데이터에 없는 신규 문제를 생성하지 않는다.

### 2. dry-run 검증

```powershell
.\scripts\import-dataset.ps1 -Mode dry-run
```

다음 내용을 검사하지만 DB 변경은 마지막에 모두 rollback한다.

- 필수 파일과 JSON 형식
- manifest의 문제 수와 실제 JSONL 행 수
- 자격증 및 단원 코드
- 단일·복수 선택 유형
- 선택지 ID 중복
- `required_answer_count`와 `final_answers` 개수 일치
- 정답이 실제 선택지를 참조하는지 여부
- UID 및 콘텐츠 중복
- 제외 문제 여부

결과에는 `added`, `updated`, `unchanged`, `excluded`, `failed` 예상 건수가 표시된다. `failed`가 있으면 실제 적재 전에 데이터를 수정한다.

### 3. strict 실제 적재

```powershell
.\scripts\import-dataset.ps1 -Mode strict
```

`certifications.json`과 `domains.json`을 먼저 저장한 뒤 `questions.jsonl`을 한 줄씩 처리한다. 문제와 선택지, 정답 버전을 하나의 transaction으로 적재하며 한 건이라도 실패하면 전체 작업을 rollback한다.

- 처음 보는 `question_id`: 추가
- 이미 존재하고 내용이 변경됨: 갱신
- 이미 존재하고 내용도 동일함: 변경하지 않음
- `excluded_questions.csv`에 있음: 제외
- UID가 다른 동일 콘텐츠 또는 스키마 오류: 실패

동일한 패키지를 다시 실행해도 같은 문제가 추가 생성되지 않는다.

### 4. 정답 버전 저장

각 문제에는 다음 출처가 분리되어 보존된다.

- `provided`: 원본 제공 정답
- `ai_verified`: AI 검증 정답
- `admin_final`: 웹앱 채점에 사용하는 `final_answers`

AI 결과가 최종 답과 달라도 `admin_final`을 자동 변경하지 않는다. 충돌 상태로 관리자가 검토하도록 한다.

### 5. 미분류 문제 처리

`DEA-UNCLASSIFIED` 문제는 일반 학습에는 사용할 수 있지만 공식 비율 모의고사에서는 제외한다. OpenAI 설정이 있으면 배치 분류를 실행하고, 신뢰도가 기준 이상인 문제만 `DEA-D1`~`DEA-D4`에 자동 반영한다. 신뢰도가 낮으면 미분류 상태를 유지한다.

```powershell
.\scripts\classify-domains.ps1 -CertificationCode "DEA-C01" -OnlyUnclassified
.\scripts\classify-domains.ps1 -CertificationCode "DEA-C01" -ReportOnly
```

### 6. 일반 학습의 문제 선택

일반 학습을 시작할 때 다음 조건을 만족하는 DB 문제 풀을 조회한 후 세션용 문제 순서를 무작위로 섞는다.

- DEA-C01 문제
- `is_active=true`
- 출제 가능한 검증 상태
- 현재 `admin_final` 답안 존재
- `required_answer_count`와 최종 정답 개수 일치
- 단원 학습을 선택한 경우 해당 `domain_code`

세션이 시작된 후에는 선택된 문제 ID와 순서를 고정한다. 문제 화면을 이동하거나 새로 요청할 때마다 다른 문제로 바뀌지 않는다. 반복 가능한 테스트가 필요하면 고정된 seed를 전달할 수 있다.

### 7. 공식 비율 모의고사의 문제 선택

모의고사는 단순 전체 무작위 추출이 아니다. DEA-C01 공식 단원 비율로 필요한 문제 수를 먼저 계산하고, 각 단원 풀 안에서 문제를 무작위 선택한다.

- `DEA-UNCLASSIFIED` 제외
- D1~D4별 필요 문항 수 계산
- 각 단원 안에서 무작위 선택
- 시험 생성 시 문제 순서 고정
- 시험 도중 선택지와 문제 순서를 다시 섞지 않음
- 특정 단원이 부족하면 다른 단원 문제로 임의 대체하지 않고 생성 중단
- 관리자 화면에 단원별 필요·보유·부족 문항 수 표시

따라서 문제 수가 충분하고 모든 문제가 공식 단원으로 분류되어야 65문항 공식 비율 모의고사가 활성화된다.

### 8. 사용자 풀이 이후

- 일반 학습: 제출 즉시 백엔드에서 정확 일치 채점
- 틀린 문제: 오답노트 자동 등록 또는 횟수 증가
- 모의고사: 제한 시간 종료 또는 직접 제출 시 일괄 채점
- 결과: 원점수, 환산점수, 합격 여부 및 문제별 검토 제공
- 설명 보기: 저장된 해설이 있으면 재사용하고, 없을 때만 OpenAI 호출 후 DB 저장

### 핵심 구분

| 단계 | 문제 선택 방식 |
|---|---|
| 데이터 적재 | 검증 통과 문제 전체 저장, 무작위 추출 없음 |
| 무작위 학습 | 출제 가능 전체 풀을 섞어 세션 문제 선택 |
| 단원 학습 | 선택한 단원의 출제 가능 풀만 섞음 |
| 공식 모의고사 | 공식 단원 비율을 먼저 충족한 뒤 단원별 무작위 선택 |

무작위 선택은 저장된 정답이나 문제 내용을 변경하지 않는다. 어떤 문제가 선택되는지만 결정하며 최종 채점은 항상 백엔드의 `admin_final` 답안을 기준으로 수행한다.

## 구현된 핵심 흐름

1. `certifications.json`, `domains.json` upsert
2. `manifest.json`, `verification_report.json` 또는 `validation_report.json` JSON 검증과 `excluded_questions.csv`의 UID 집합 확인
3. `questions.jsonl` 줄 단위 스트리밍
4. `question_id` 기반 문제 upsert 및 선택지 동기화
5. `provided`, `ai_verified`, `admin_final` 정답 버전 분리 보존
6. `admin_final`만 최종 채점 답안으로 지정
7. 추가·갱신·동일·제외·실패 건수 출력
8. dry-run rollback 및 strict 전체 transaction

`duplicate_report.csv`와 `verification_report.json`은 원본 데이터 패키지에 그대로 보존하며 자동 수정하지 않는다. UID가 다른 동일 콘텐츠는 importer가 실패 건으로 보고한다.

## 단원 분류

- `DEA-UNCLASSIFIED`만 기본 분류 대상으로 선택한다.
- OpenAI 구조화 배치 출력, SDK 재시도와 지수 백오프, 최대 배치 크기 제한을 사용한다.
- 기본 자동 반영 임계값은 `0.80`이며 `app_settings.classification_confidence_threshold`로 변경할 수 있다.
- 임계값 미만은 미분류 단원에 남기고 `needs_review`로 저장한다.
- 관리자 직접 지정은 `manual`, 신뢰도 `1.0`으로 기록한다.
- 이미 `classified` 또는 `manual`인 문제는 명시적 강제 재분류 전에는 호출하지 않는다.

## 공식 비율 모의고사

- `DEA-D1`~`DEA-D4` 문제만 사용한다.
- 활성 상태, 출제 가능한 검증 상태, 현재 `admin_final`, 정답 개수 일치 조건을 모두 검사한다.
- 부족 단원의 문제를 다른 단원으로 임의 대체하지 않는다.
- 준비도 API는 단원별 필요·사용 가능·부족 건수를 반환한다.

## 명령

실제 파일을 다음 폴더에 복사한다.

```text
data/processed/dataset/aws-dea-c01/
```

PowerShell 스크립트는 이 경로를 기본값으로 사용하므로 `-Path`를 생략할 수 있다.

```powershell
./scripts/import-dataset.ps1 -Mode dry-run
./scripts/import-dataset.ps1 -Mode strict
python -m app.importers.dataset_importer --path ../data/processed/dataset/aws-dea-c01 --mode dry-run
python -m app.importers.dataset_importer --path ../data/processed/dataset/aws-dea-c01 --mode strict
python -m app.classifiers.domain_classifier --certification DEA-C01 --only-unclassified
python -m app.classifiers.domain_classifier --certification DEA-C01 --report-only
```

## 현재 검증 상태

- 합성 샘플을 별도 빈 DB에 strict 적재: 성공
- dry-run 직후 DB 문제 수 0건 확인: rollback 성공
- 같은 패키지 재적재: `added=0`, `unchanged=1`, 중복 0건
- 문제 1, 선택지 2, 정답 버전 `provided/ai_verified/admin_final` 각 1건 확인
- TypeScript 검사와 Python compileall: 통과
- ESLint: 오류 및 경고 없이 통과
- 브라우저: AWS DEA-C01 표시, SnowPro 미표시, 관리자 분류·모의고사 준비도·미분류 패널 렌더링, 콘솔 오류 0건
- 실제 AWS 패키지: 지정 경로에서 확인 완료
- 실제 패키지 dry-run: `total=295, added=295, updated=0, unchanged=0, excluded=0, failed=0`
- manifest 문제 수 295와 JSONL 유효 행 295가 일치
- 제외 보고서 2건, 중복 보고서 7건, 분류 검토 잔여 0건 확인
- dry-run 후 검증 DB 문제 수 0건으로 rollback 확인
- 실제 데이터에는 `verification_report.json` 대신 manifest에 선언된 `validation_report.json`이 있으며 importer가 두 이름을 모두 지원
- assets 파일 0건이며 현재 문제의 `asset_refs` 요구 여부는 JSONL 검증 결과 이상 없음
- MySQL/Docker: 현재 실행 환경에 설치되어 있지 않아 실제 MySQL 적재는 대기

실제 패키지와 MySQL이 준비되기 전에는 “초기 개발 완료 조건”의 데이터 건수·실제 적재·65문항 공식 모의고사 항목을 완료로 표시하지 않는다.
