# CreditDocStruct 관리자 애플리케이션

**신평서 데이터 구조화 프로젝트** — 비개발자가 브라우저에서 **추출 결과를 확인·다운로드**하고,
**미분류 라벨을 검수**해 YAML에 등록하는 도구입니다.

재무지표 분류 키는 코드 상수(`common/metric_catalog.py`)이며, 관리자에서 지표 YAML을 편집하지 않습니다.

## 필요 사항

- **Python 3.11 64-bit** ([python.org](https://www.python.org/downloads/))
- **SQLite는 Python에 포함**되어 있어 별도 설치가 필요 없습니다.

## 설치 (최초 1회)

1. `admin\setup_admin.bat` 을 더블클릭합니다.
2. "설치가 완료되었습니다." 메시지가 나오면 닫습니다.

## 실행 (평소)

1. `admin\run_admin.bat` 을 더블클릭합니다.
2. 브라우저에서 관리 화면이 열립니다 (`http://localhost:8501`).

## 화면 구성

| 메뉴 | 설명 |
|------|------|
| **결과 조회** | `results/*.json` 공개 컬럼 요약, 필터, 비개발자 Excel 다운로드 |
| **라벨 검수** | 검수 대기 라벨을 표 형태로 확인하고 상품에 등록하거나 제외 |

**제거된 메뉴 (비개발자 UI 축소):** 라벨 조회, 작업 이력, YAML 백업 복원. YAML 쓰기 시 백업은 자동 생성되며, 복원은 개발자가 파일·CLI로 처리합니다.

### 라벨 검수

1. 검수 대기 목록이 **3열 표**(라벨 · 상품선택 · 승인/거절)로 표시됩니다.
2. 상품 선택란 아래 **추천 1건** 캡션을 참고합니다.
3. **승인** → `raw_label`이 선택한 상품에 YAML 등록되고 목록에서 사라집니다.
4. **거절** → 제외 처리되어 목록에서 사라집니다.

사이드바: **새로고침**, **검수 대기 N건**.

### 결과 조회

1. 결과 JSON 파일을 선택합니다.
2. **처리상태**(전체/success/partial/fail)와 **회사명 검색**으로 필터합니다.
3. 표에서 공개 컬럼(`No`, 회사명, 신평사, 상품분류, 신용등급, 등급전망, 평가일, 원본파일명)을 확인합니다.
4. **Excel 다운로드**는 현재 필터 결과로 **비개발자 Excel**(신용등급 목록 + 기업별 시트)을 받습니다.

재무지표 facts 재생성은 CLI `python main.py --renormalize` 를 사용합니다.

## 사내 서버에서 실행

한 대의 PC에서 `run_admin.bat`을 실행한 뒤, 다른 사용자는 브라우저만 쓰면 됩니다.

- 서버 PC IP: `http://<서버주소>:8501`
- 외부 접속이 필요하면 `run_admin.bat` 안의 안내대로 `--server.address 0.0.0.0` 옵션을 사용하세요.

## 할 수 없는 작업 (개발자 전용)

- 새 상품 종류(상품 코드) 만들기
- 등록 라벨 일괄 조회·삭제 (이전 라벨 조회 탭 — 개발자는 `instruments.yaml` 직접 편집)
- 재무지표 카탈로그·요약 규칙 변경 (`common/metric_catalog.py`, `export/fin_excel_utils.py`)
- 정규화·추천·검증 정책 변경 (`common/matching_policy.py`)
- YAML 파일 구조 직접 편집

## 데이터 저장 위치

| 항목 | 경로 |
|------|------|
| 미분류 라벨 DB | `admin/data/admin.db` |
| 문서·재무지표 DB | `admin/data/documents.db` |
| YAML 백업 | `admin/backup/` |
| 추출 결과 | `results/result_YYYYMMDD.json` · `.xlsx` |
| 테마 | `.streamlit/config.toml` |

PDF 추출(`main.py`)을 실행하면 미분류 라벨과 문서 raw가 자동으로 SQLite에 쌓입니다. 관리자 앱이 꺼져 있어도 저장됩니다.

## 서버 시작 시 YAML 동기화

관리자 앱은 서버 프로세스가 처음 실행될 때 `admin.db`와 현재
`config/instruments.yaml`을 한 번 동기화합니다.

- 검수 대기 라벨이 YAML에 있으면 → 승인 완료
- 승인된 등록 라벨이 YAML에서 제거되면 → 검수 대기로 복구
- 승인 경로 상품이 바뀌면 → 현재 YAML 연결로 갱신
- 제외된 라벨은 변경하지 않음

동기화는 백그라운드에서 수행되며 별도 UI는 없습니다.
서버 실행 중 개발자가 YAML을 직접 변경했다면 관리자 서버를 재시작해야 동기화됩니다.

## 기존 undefined.json 이관 (개발자)

```bat
cd CreditDocStruct\CreditDocStruct
.venv\Scripts\python.exe -m admin.services.migrate_undefined_json --source admin/undefined.json
```

이관 후 `admin/` 폴더의 구 `undefined.json`은 더 이상 사용하지 않습니다.
