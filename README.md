# CreditDocStruct

**신평서 데이터 구조화 프로젝트**

NICE신용평가 · 한국신용평가 · 한국기업평가 신용평가서 PDF에서  
평가대상 라벨·신용등급·등급전망·재무지표를 추출·구조화합니다.

표·시각 레이아웃으로 **구조 추출**(`ExtractedRatingRow`)한 뒤,  
`config/instruments.yaml`의 `label_dictionary`와 **정확 일치**로 분류(`RatingRecord`)합니다.  
검출된 상품마다 신용등급 1건을 `products` 배열로 반환합니다.

---

## 설치

```bash
cd C:\mycode\CreditDocStruct\CreditDocStruct
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

`.env`의 `INPUT_DIR`에 처리할 PDF 폴더 경로를 지정합니다 (필수, 코드 기본값 없음).

의존성: PyMuPDF, pandas, openpyxl, PyYAML, python-dotenv, pytest.

---

## 사용법

모든 오케스트레이션은 **`main.py`** 에서만 수행합니다.

```bash
cd C:\mycode\CreditDocStruct\CreditDocStruct

# .env의 INPUT_DIR 폴더를 처리 (인자 생략)
.venv\Scripts\python.exe main.py

# 단일 PDF 또는 다른 폴더를 직접 지정
.venv\Scripts\python.exe main.py report.pdf
.venv\Scripts\python.exe main.py ./other_pdfs

# 결과 파일명 stem 지정 (result/batch.json, result/batch.xlsx)
.venv\Scripts\python.exe main.py -o batch
```

| 옵션 | 설명 |
|------|------|
| `input` (선택) | PDF 파일/폴더. 생략 시 `.env`의 `INPUT_DIR` |
| `-o`, `--output` | 결과 파일명 stem (기본: `result_YYYYMMDD`, 실행일 기준) |
| `--non-recursive` | 폴더 처리 시 하위 디렉터리 제외 |

상품은 YAML exact match로 분류되며, 상품당 1개 등급이 `products`에 쌓입니다.  
설정은 `CreditDocStruct/.env` (템플릿: `.env.example`)에서 로드합니다.

### 공개 API

```python
from main import extract_credit_report

result = extract_credit_report("report.pdf")  # dict
```

배치 저장만 필요하면 `commit_batch_outputs(results, stem=...)` 를 사용합니다.

---

## 처리 흐름

```
입력 PDF/폴더
 └─ PDF 순회
    ├─ 텍스트·표 추출 → ExtractedRatingRow[] (rating_status: none/single/ambiguous)
    │    · 현재·직전 등급이 함께 있으면 헤더의 「현재등급」열만 사용
    ├─ 회사명(`company_name`)·신평사(`agency`, 3사 표준명 ㈜)
    ├─ 라벨 exact match → RatingRecord (matched/undefined)
    ├─ Primary·유효등급 동시 추출 → YAML 라벨 분리·행 전체 등급 탐색
    ├─ canonical 병합 (`confirmed_by`, `validation_warnings`)
    ├─ 상품별 `products` 집계 (평가종류 우선순위) + success/partial/fail
    ├─ undefined 발생 건 수집
    └─ 배치 종료 후 원자적 저장
         result/result_YYYYMMDD.json
         result/result_YYYYMMDD.xlsx  (시트: 신용등급_결과, 상품당 1행)
         admin/data/admin.db    (미분류 라벨 SQLite 누적)
```

### 표·행 선택 우선순위

1. **Primary:** `평가 개요`/`평가 등급` 표 (`pdf_table`). 불완전 orphan 행만 있으면 `visual_layout`으로 fallback.
2. **유효등급:** Primary 유무와 관계없이 **항상** 추출 (`valid_rating_section`).
3. **Fallback:** Primary·유효등급 모두 없을 때만 `plain_text`.
4. **라벨 분리:** 평가대상 셀 앞부분 YAML 최장 alias → `raw_label`, 나머지 → `issue_name`.
5. **등급 탐색:** 행 전체 후보 → 1개면 채택, 2개+면 `현재등급` 열. 종목코드(`영구A-05` 등) 오탐 제외.
6. **병합:** `instrument_key`별 canonical. Primary 우선, 유효등급 일치 시 `confirmed_by`. 불일치 시 `validation_warnings`.
7. **Products:** 상품당 1건. 평가종류 우선순위 `본 > 수시 > 신규 > 정기 > 유효등급`.

### 신평사·회사명

| 필드 | 값 |
|------|-----|
| `agency` / Excel `신평사` | `NICE신용평가㈜` · `한국신용평가㈜` · `한국기업평가㈜` 중 하나만 |
| `company_name` / Excel `회사명` | 평가대상 기업명 (`CREDIT OPINION` 등 제외, 파일명 fallback) |

### 파일 상태

| status | 조건 |
|--------|------|
| `success` | 모든 `products` 항목이 등급 확정 |
| `partial` | 일부 상품만 확정 |
| `fail` | 확정 상품 없음 또는 파일/파싱 오류 |

### fail_reason

PDF급: `file_error` → `text_extraction_failed` → `parse_error` →  
`label_not_found` → `undefined_label`

상품급(`products[].fail_reason`): `multiple_rating_columns` · `multiple_ratings` · `rating_not_found`

| code | 의미 |
|------|------|
| `file_error` | PDF 열기 실패(손상·암호 등) |
| `text_extraction_failed` | 평가 행이 없고, 추출 문자 수·등급 토큰도 부족 |
| `parse_error` | 텍스트는 있으나 평가대상 행/표 구조를 구성하지 못함 |
| `multiple_rating_columns` | 현재등급 열 적용 후에도 등급을 하나로 확정 못함 |
| `multiple_ratings` | 동일 상품·동일 평가종류 우선순위에서 서로 다른 등급/전망 |
| `rating_not_found` | YAML 매칭은 됐지만 등급 없음 |
| `label_not_found` | 등급은 있으나 라벨을 못 찾음 |
| `undefined_label` | 등급 있는 라벨이 YAML에 미등록 |

### 결과 스키마 (JSON, PDF당 1객체)

| 필드 | 설명 |
|------|------|
| `result_no` | 정수 배치 순번 (`1`, `2`, `3`...) |
| `company_name` / `agency` | 평가대상 회사명 · 신평사(3사 표준명 ㈜) |
| `status` / `fail_reason` | `success` / `partial` / `fail` + PDF급 `{code, message}` |
| `products` | 상품별 확정 결과 (`instrument_key`, `rating`, `outlook`, `evaluation_type`, `status` …) |
| `records` | 전체 `RatingRecord` (`issue_name`, `confirmed_by`, `raw_outlook` 등) |
| `validation_warnings` | Primary·유효등급 등급 불일치 등 (`conflicting_rating_sources`) |
| `undefined_records` | YAML 미등록 라벨 + `suggestions` (이메일·재무지표·rating none 제외) |
| `file_hash` | SHA-256 (undefined 중복 방지용) |

Excel(`신용등급_결과`)은 **상품당 1행**입니다.  
열: No, 회사명, 신평사, 처리상태, 상품분류_Key, 상품분류, 원본라벨, 평가종류, 신용등급, 등급전망, 원본파일명, 실패사유.

---

## 상품·라벨 (`config/instruments.yaml`)

등록 상품 키: `issuer`, `insurance_payment`, `senior_unsecured`, `guaranteed_bond`,  
`subordinated`, `coco_t1`, `coco_t2`, `commercial_paper`, `short_term_bond`.

YAML에는 **상품 목록과 라벨 딕셔너리만** 둡니다.  
정규화·추천·검증 정책은 `common/matching_policy.py`에서 관리합니다.

라벨 추가·수정은 `label_dictionary`에만 등록하면 됩니다.  
동일 정규화 라벨이 서로 다른 `instrument_key`로 매핑되면 기동 시 거부됩니다.

undefined 라벨에는 char n-gram cosine 추천(`suggestions`,
`RECOMMENDATION.min_score` 미만 제외)이 붙지만 **자동 확정에는 사용하지 않습니다**.  
수동으로 YAML에 등록한 뒤 재실행하세요.

---

## 디렉터리

```
CreditDocStruct/
├── README.md
├── .gitignore
├── .cursorignore
├── .cursor/rules/          # architecture, taxonomy, extraction, testing, documentation
└── CreditDocStruct/       # 앱 루트 (실행 cwd)
    ├── main.py
    ├── requirements.txt
    ├── .env / .env.example
    ├── config/instruments.yaml
    ├── common/             # settings, matching_policy, models, fail_reasons, rating_tokens
    ├── agency/             # 신평사·레이아웃·회사명
    ├── classify/           # exact match, undefined 추천·필터
    ├── extract/            # tables, visual, layout, fallback, row_parser, row_rebuild, label_fields, merge
    ├── export/             # json_io, excel, undefined_store
    ├── admin/                # 관리자 앱 (Streamlit, SQLite, YAML 백업)
    ├── result/
    └── tests/
```

---

## 관리자 애플리케이션

비개발자가 브라우저에서 **미분류 라벨을 한 건씩 검수**하고,
등록 라벨·작업 이력을 관리하며, **신용등급 추출 결과를 조회·엑셀 다운로드**합니다.

| 항목 | 내용 |
|------|------|
| 진입점 | `admin/admin_main.py` (Streamlit) |
| 설치·실행 | [`admin/README.md`](CreditDocStruct/admin/README.md) 참고 |
| 최초 설치 | `admin\setup_admin.bat` 더블클릭 |
| 평소 실행 | `admin\run_admin.bat` 더블클릭 |
| 미분류 누적 | `admin/data/admin.db` (PDF 추출 시 자동 저장) |
| 메뉴 | 검수하기 · 등록된 라벨 · 작업 이력 · 결과 조회 |

비개발자 업무: 발견된 라벨을 상품에 등록, 노이즈 라벨 제외, 결과 확인·엑셀 저장.  
상품 코드 생성·정규화/추천 정책 변경(`common/matching_policy.py`)은 개발자 전용입니다.

검수 상태는 `pending`(검수 대기) · `approved`(승인 완료) · `ignored`(제외) 3종이며,
라벨 등록·삭제 시 `instruments.yaml`을 자동 백업(`admin/backup/`) 후
원자적으로 교체합니다. 관리자 서버가 시작될 때 `admin.db`와 현재 YAML을
1회 양방향 동기화합니다(멱등).

- 검수 대기 라벨이 YAML에 있으면 → 승인 완료
- 승인된 등록 라벨이 YAML에서 제거되면 → 검수 대기로 복구
- 제외된 라벨은 변경하지 않음

기존 `admin/undefined.json`은 SQLite로 이관되었으며,
`admin/services/migrate_undefined_json.py`로 1회 마이그레이션합니다.

---

## 테스트

```bash
cd C:\mycode\CreditDocStruct\CreditDocStruct
.venv\Scripts\python.exe -m pytest tests -q
```

단위 테스트: 라벨 exact match, 현재등급 열 선택, 상품별 `products` 집계, source 병합,  
fail_reason, Excel 상품당 1행, undefined dedup, 원자적 저장.

---

## 설정 (.env)

| 키 | 용도 |
|----|------|
| `INPUT_DIR` | 처리할 PDF 폴더 (**필수**, 코드 기본값 없음. 상대경로는 앱 루트 기준) |
| `INSTRUMENTS_YAML_PATH` | 상품·라벨 딕셔너리 YAML 경로 (기본 `config/instruments.yaml`) |
| `RESULT_DIR` | 결과 저장 폴더. 파일명은 `result_YYYYMMDD`로 코드 고정 |
| `ADMIN_DB_PATH` | 미분류 라벨 SQLite DB (기본 `admin/data/admin.db`) |
| `ADMIN_BACKUP_DIR` | YAML 백업 폴더 (기본 `admin/backup`) |
| `MAX_PDF_PAGES` | 스캔 페이지 상한 (기본 1) |
| `MIN_EXTRACTED_TEXT_CHARS` | 텍스트 추출 실패 판정용 문자 수 하한 (기본 50) |

---

## 알려진 한계

| 항목 | 상태 |
|------|------|
| **동일 상품·동일 우선순위 등급 충돌** | 해당 상품만 `products[].fail_reason=multiple_ratings` (PDF는 `partial`/`fail`) |

미분류 라벨은 `admin/data/admin.db`에 쌓이므로, 관리자 앱에서 검토 후 `label_dictionary`에 반영하는 운영 루프를 사용합니다.
