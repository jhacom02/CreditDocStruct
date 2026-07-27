# CreditDocStruct

**신평서 데이터 구조화 프로젝트 — 개발자·AI 에이전트용 문서**

NICE신용평가 · 한국신용평가 · 한국기업평가가 발행한 **신용평가서 PDF**에서  
평가대상 라벨·신용등급·등급전망·재무지표를 추출해 구조화된 JSON/Excel·SQLite로 저장한다.

**이 문서의 목적:** 프로젝트의 구조·처리 로직·기술·운영/유지보수 원칙을 한곳에 둔다.  
AI 에이전트와 후임 개발자가 **기존 구조와 규칙을 해치지 않고** 수정할 수 있도록,  
현재 코드와 일치하는 사실만 기술한다. 업무 배경·PoC 범위는 `About_CreditDocStruct.md`를 참고한다.

유지보수 시 이 README의 **§3 아키텍처·개발 규칙**과 해당 주제 절(§7~§12, §16~§18)을 함께 본다.
코드·문서·테스트는 아래에 적은 **현재 계약**만 따른다.

---

## 목차

1. [추출 대상과 범위](#1-추출-대상과-범위)
2. [기술 스택](#2-기술-스택)
3. [아키텍처·개발 규칙](#3-아키텍처개발-규칙)
4. [디렉터리 구조](#4-디렉터리-구조)
5. [전체 처리 흐름](#5-전체-처리-흐름)
6. [데이터 모델](#6-데이터-모델)
7. [추출 파이프라인 (extract)](#7-추출-파이프라인-extract)
8. [분류 파이프라인 (classify)](#8-분류-파이프라인-classify)
9. [상품 집계 (products)](#9-상품-집계-products)
10. [재무지표 처리](#10-재무지표-처리)
11. [결과 스키마·상태·실패 사유](#11-결과-스키마상태실패-사유)
12. [출력·저장](#12-출력저장)
13. [설정 (.env)](#13-설정-env)
14. [실행 방법](#14-실행-방법)
15. [공개 API](#15-공개-api)
16. [테스트](#16-테스트)
17. [관리자 앱 (간략)](#17-관리자-앱-간략)
18. [유지보수 가이드](#18-유지보수-가이드)
19. [알려진 한계](#19-알려진-한계)

---

## 1. 추출 대상과 범위

### 1.1 입력

| 항목 | 내용 |
|------|------|
| **파일 형식** | PDF만 지원 |
| **신평사** | NICE신용평가㈜, 한국신용평가㈜, 한국기업평가㈜ (3사) |
| **스캔 페이지** | `.env`의 `MAX_PDF_PAGES` (기본 **1페이지**). 다중 페이지 보고서는 상한을 올려야 함 |
| **입력 경로** | `.env` `INPUT_DIR` 또는 CLI 인자 (파일/폴더) |

### 1.2 추출하는 항목 (In Scope)

#### 문서 메타

| 필드 | 출처 | 모듈 |
|------|------|------|
| `company_name` | 1페이지 텍스트·레이아웃, 파일명 fallback | `agency/agency.py` |
| `agency` | 1페이지·파일명에서 3사 키(`nice`/`kis`/`kr`) 식별 | `agency/agency.py` |
| `evaluation_date` | 1페이지 텍스트·파일명 | `extract/evaluation_date.py` |
| `file_hash` | SHA-256 | `export/undefined_store.py` (`file_sha256`) |

#### 신용등급 (섹션 그리드 기반)

PDF 1페이지(또는 `MAX_PDF_PAGES` 범위)에서 **섹션 제목 3종**을 찾아 표/시각 그리드를 재구성한 뒤 행 단위로 추출한다.

| 섹션 키 | 제목 예시 | 추출 내용 |
|---------|-----------|-----------|
| `primary_rating` | 평가개요, 평가등급 | 평가대상 라벨, 신용등급, 등급전망, 평가종류(본/수시/신규 등) |
| `valid_rating` | 유효등급 | 동일 (Primary와 독립적으로 항상 추출) |
| `financial_indicators` | 주요 재무지표 | 재무지표 라벨·기간별 수치 그리드 |

등급 행에서 추출하는 값:

- `raw_label` — 평가대상 원문 라벨
- `rating` / `outlook` — 신용등급·등급전망
- `evaluation_type` — 본/수시/신규/예비/정기 등
- `issue_name` — 라벨 분리 후 잔여(종목명 등)
- `rating_status` — `none` / `single` / `ambiguous`

등급은 **YAML `label_dictionary` exact match**로 9개 상품(`instrument_key`)에 분류한다.

#### 재무지표

`financial_indicators` 섹션 표에서 **코드 상수 8키**로 exact match한다 (`common/metric_catalog.py`).

| metric_key | 표시명 |
|------------|--------|
| `total_assets` | 총자산 |
| `net_income` | 당기순이익 |
| `total_borrowings` | 총차입금 |
| `equity` | 자기자본 |
| `debt_ratio` | 부채비율(%) |
| `bis_ratio` | BIS자본비율(%) |
| `liquidity_ratio` | 유동성비율(%) |
| `leverage` | 총자산/자기자본(배) |

### 1.3 추출하지 않는 항목 (Out of Scope)

| 항목 | 이유 |
|------|------|
| 정성 평가 본문, 업체 개요, 평가 근거 전문 | 섹션 카탈로그에 없음 |
| 등급 추이·변동 이력 표 전체 | `valid_rating` 행만 사용, 시계열 분석 없음 |
| 스캔 범위 밖 페이지 | `MAX_PDF_PAGES` 초과 페이지 무시 |
| 이미지·스캔 PDF OCR | PyMuPDF 텍스트/좌표 추출만 사용 |
| YAML 미등록 라벨의 **자동 확정** | undefined로 기록, 추천만 제공 |
| 재무지표 YAML/관리자 편집 | 코드 카탈로그만 사용. 관리자 **상품 사전**은 신용등급 라벨(`instruments.yaml`)만 |
| `target_instrument` 지정 추출 | 없음 — PDF에서 검출된 모든 상품을 자동 탐색 |

### 1.4 상품(instrument) 목록

`config/instruments.yaml`의 `instruments`에 정의된 9키:

`issuer`, `insurance_payment`, `senior_unsecured`, `guaranteed_bond`, `subordinated`, `coco_t1`, `coco_t2`, `commercial_paper`, `short_term_bond`

라벨→상품 매핑은 `label_dictionary`에만 등록한다. 동일 정규화 라벨이 서로 다른 `instrument_key`로 매핑되면 **기동 시 거부**한다.

---

## 2. 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python **3.11 또는 3.12** (64-bit 권장) |
| PDF | PyMuPDF (`pymupdf`) — 텍스트·좌표·표 추출 |
| 설정 | `python-dotenv` (.env), `PyYAML` (instruments.yaml) |
| 출력 | `pandas`, `openpyxl` (Excel), JSON (stdlib) |
| DB | SQLite (`documents.db`) |
| YAML 편집(관리자) | `ruamel.yaml` (순서·주석 보존) |
| 테스트 | `pytest` |
| 관리자 UI | Streamlit (`admin/`, `admin/requirements.txt`) |

---

## 3. 아키텍처·개발 규칙

AI 에이전트·후임 개발자는 이 절을 **변경의 가드레일**로 삼는다. 상세 흐름은 이후 절을 본다.

### 3.1 아키텍처

1. **오케스트레이션 단일 진입점** — PDF 배치 처리 루프·파이프라인 조립은 `main.py`만. `admin/run_extract.bat`은 `main.py` 호출 래퍼일 뿐 두 번째 오케스트레이터가 아니다.
2. **관리자 별도 진입점** — `admin/admin_main.py`(Streamlit). 조회·예외 목록·상품 라벨 YAML만. PDF 추출 UI 없음.
3. **최상위 패키지(1단)** — `common/`, `agency/`, `classify/`, `extract/`, `export/`, `admin/`, `config/`, `results/`, `tests/`. `admin/` 안에만 `views/`, `ui/`, `services/`, `data/`, `backup/` 등 기능 하위를 둔다.
4. **경로·상수** — `.env` → `common/settings.py`만. 코드에 하드코딩하지 않는다.
5. **정책 단일 원천** — 정규화·추천·카탈로그 검증은 `common/matching_policy.py`. `instruments.yaml`에는 상품·라벨 딕셔너리만.
6. **자동 상품 탐색** — `target_instrument` / `--target` / `DEFAULT_TARGET_INSTRUMENT` 없음. PDF 검출 라벨 → YAML 분류 → `products`.
7. **추출·분류 모델 분리** — `ExtractedRatingRow` → `RatingRecord`. 분류기는 `rating`·`evaluation_type`을 **재계산하지 않는다**.
8. **원자적 저장** — JSON/Excel: 임시 파일 → 성공 확인 → `os.replace()` (`commit_batch_outputs`).
9. **미분류** — 결과 JSON `undefined_records`. YAML 쓰기는 `admin/services/yaml_service.py`만 (`managed_by: admin` 추가분만 삭제 가능).
10. **재무지표** — `common/metric_catalog.py` 8키 exact. raw/norm은 `export/document_store.py`(`documents.db`). 요약 4행은 `export/fin_excel_utils.py`. 관리자에서 지표 정의 편집 없음.
11. **실패 비표시** — Excel 원본·요약 신평사 블록은 `success_products` / `is_usable_financial_table` 통과분만. 게이트를 완화해 깨진 표를 억지 노출하지 않는다.

### 3.2 추출 (extract)

- `extract/row_parser.py`는 `ExtractedRatingRow`만 만든다. 분류기를 호출하지 않는다.
- 행 전체 등급 후보: 1개면 셀 위치 무관 `single`, 2개+면 **현재등급** 열만 사용. 동일 등급이 현재·직전에 있어도 행 전체 dedupe로 `single`을 만들지 않는다.
- Primary·유효등급·재무지표는 `extract/sections.py` 섹션 그리드 파이프라인. **유효등급은 Primary와 무관하게 항상 추출**.
- 그리드 셀 `source`는 `pdf_table` 또는 `visual_layout`. 진입점은 섹션 파이프라인이다.
- 평가대상 셀: `extract/label_fields.py` YAML 최장 prefix로 `raw_label`/`issue_name` 분리 후 분류.
- 병합 라벨: `extract/row_rebuild.py`로 분할. 복원 실패 시 `parse_error`.
- `extract/merge.py` `merge_canonical_records`: Primary canonical + `confirmed_by` + `validation_warnings`.
- `build_products`: 상품당 1건. 평가종류 우선순위 `본 > 수시 > 신규 > 예비 > 정기 > (primary 무타입) > 유효등급`.

### 3.3 분류·택소노미 (classify / YAML)

- 상품·라벨 매핑은 `config/instruments.yaml`만 (`instruments` + `label_dictionary`).
- 분류는 `label_dictionary` **exact match만**. 점수형 feature taxonomy 없음.
- 라벨 status: `matched` | `undefined` 만.
- `classify/undefined_filter.py`로 이메일·재무지표·rating none 등 후보 제외.
- 기동 시: 동일 정규화 라벨 상충 매핑 거부, 미등록 `instrument_key` 참조 거부.

### 3.4 테스트

- `tests/label_variants.json`: exact → matched/key, 미등록 → undefined만, 자동 key 확정 없음.
- 유지할 단위 테스트 영역: 현재등급 열 선택, 상품별 `products` 집계, source 병합, `fail_reason`, Excel 상품당 1행, occurrence_id, 원자적 저장, YAML `managed_by`, 예외 대기열.
- 테스트·문서·API에 쓰지 않는 개념: `--target`, scoring taxonomy, `ocr_required`, `metrics.yaml`, 구결과 경로 `result/`(기본은 `results/`), 라벨 status `unknown`/`ambiguous`.

### 3.5 문서화

- README·`admin/README.md`·`ops_guide.md`는 **현재 코드 계약**과 일치해야 한다.
- 문서에 적을 핵심 계약: `products` 상품당 1건, ExtractedRatingRow/RatingRecord 분리, PDF `success`/`partial`/`fail`, 현재등급 열·평가종류 우선순위, 재무지표 8키·요약 4행·`documents.db`·`--renormalize`, `RESULT_DIR`=`results/`, Excel `EXCEL_PUBLIC_COLUMNS` / `ADMIN_COLUMNS` 분리.
- admin 탭(현재): **결과 조회 · 확인 필요 · 상품 사전 · 운영 가이드**.
- 존재하지 않는 기능·과거 UI·삭제된 플래그를 문서에 남기지 않는다.

---

## 4. 디렉터리 구조

```
CreditDocStruct/
├── README.md                 # 이 문서 (구조·규칙·유지보수 — AI·개발자용)
└── CreditDocStruct/          # 앱 루트 (실행 cwd)
    ├── main.py               # CLI + extract_credit_report + commit_batch_outputs
    ├── requirements.txt
    ├── .env / .env.example
    ├── config/
    │   └── instruments.yaml  # 상품 9종 + label_dictionary
    ├── common/               # 설정, 모델, 정책, 등급 토큰, fail_reason
    ├── agency/               # 신평사 식별, 회사명, 기관별 레이아웃
    ├── extract/              # PDF → 섹션 그리드 → ExtractedRatingRow / ExtractedFinTable
    ├── classify/             # YAML exact match, 재무지표 분류
    ├── export/               # JSON, Excel, documents.db
    ├── admin/                # Streamlit 관리자 + 운영용 bat (추출 로직은 main.py)
    │   ├── admin_main.py
    │   ├── setup_admin.bat   # .venv + requirements.txt + admin/requirements.txt
    │   ├── run_extract.bat   # main.py 호출 (.env INPUT_DIR)
    │   ├── run_admin.bat     # Streamlit 0.0.0.0:8501
    │   ├── views/            # results, exceptions, dictionary, guide
    │   ├── services/         # result / exception / yaml
    │   ├── ui/theme.py       # CSS (섹션 라벨·알림·버튼 색)
    │   ├── content/ops_guide.md  # UI「운영 가이드」탭 (운영자 문구)
    │   └── README.md         # admin 개발자 매뉴얼
    ├── .streamlit/config.toml
    ├── results/              # 배치 JSON/Excel 출력
    └── tests/
```

### 모듈별 책임

| 패키지 | 핵심 파일 | 역할 |
|--------|-----------|------|
| `main.py` | — | PDF 순회, 파이프라인 조립, `build_products`, 배치 저장 |
| `common/models.py` | — | `ExtractedRatingRow`, `RatingRecord`, `ExtractedTableGrid`, `FinancialFact` |
| `common/settings.py` | — | `.env`, `instruments.yaml` 로드·기동 검증 |
| `common/matching_policy.py` | — | `normalize_label`, `normalize_metric_label`, lookup 충돌 검증 |
| `common/metric_catalog.py` | — | 재무지표 8키·alias |
| `common/rating_tokens.py` | — | AAA~B±, 전망(Stable/안정적 등) 정규식 |
| `common/fail_reasons.py` | — | PDF급·상품급 실패 코드·메시지 |
| `agency/agency.py` | — | 3사 식별, `company_name`, `AgencyLayoutConfig` |
| `extract/section_catalog.py` | — | 섹션 3종 제목·종료 패턴 정의 |
| `extract/sections.py` | — | 페이지→섹션 clip→`ExtractedTableGrid` |
| `extract/grid.py` | — | clip 영역 내 표/시각 그리드 재구성 |
| `extract/regions.py` | — | 좌우 2단 레이아웃, gutter, region clip |
| `extract/rating_from_grid.py` | — | 그리드→`ExtractedRatingRow`, 재무 노이즈·등급토큰만 라벨 행 제거 |
| `extract/row_parser.py` | — | 행 전체 등급 탐색, **현재등급 열** 선택, 유효등급 셀 노이즈 truncate |
| `extract/row_rebuild.py` | — | 병합 라벨 YAML longest-match 분할, 종류/등급 셀 붕괴 복원 |
| `extract/merge.py` | — | Primary·유효등급 canonical 병합, `confirmed_by` |
| `extract/fallback.py` | — | 섹션 행 없을 때 평문 줄 스캔 |
| `extract/fin_tables.py` | — | 주요 재무지표 표 추출, 라벨/값 concat·빈 기간열 정렬(`repair_financial_matrix`) |
| `classify/classifier.py` | — | `LabelClassifier` — YAML exact match |
| `classify/metric_classifier.py` | — | `MetricClassifier` — 코드 카탈로그 exact match |
| `classify/fin_normalize.py` | — | `ExtractedFinTable` → `FinancialFact[]` |
| `classify/undefined_filter.py` | — | undefined_records JSON 누적 대상 필터 |
| `export/json_io.py` | — | JSON 직렬화 |
| `export/excel.py` | — | 공개/관리자 Excel, 기업별 시트(요약+원본); 공개 목록은 success만 |
| `export/agency_select.py` | — | 회사 그룹핑, 신평사 순서(NICE→KIS→KR), fin usable 게이트 |
| `export/rating_excel_utils.py` | — | 신용등급(요약) cascade |
| `export/fin_excel_utils.py` | — | 재무지표(요약) 4행·기간 cascade |
| `export/undefined_store.py` | — | `file_sha256`, `make_occurrence_id` 헬퍼 |
| `export/document_store.py` | — | documents.db (요약·등급/재무 raw·norm), `--renormalize` |
| `admin/services/exception_service.py` | — | 결과 JSON → 확인 필요 대기열 |
| `admin/services/yaml_service.py` | — | 상품 사전 라벨 추가/삭제(`managed_by: admin`), YAML 백업 |

---

## 5. 전체 처리 흐름

```
입력 PDF/폴더
 │
 ├─ [기동] LabelClassifier.from_yaml() — instruments.yaml 검증
 ├─ [기동] MetricClassifier.from_yaml() — metric_catalog 로드
 │
 └─ PDF마다 extract_credit_report()
      │
      ├─ 1. PDF 열기, file_hash, 텍스트 통계 (chars/words/rating_token_count)
      ├─ 2. 1페이지: agency_key, company_name, evaluation_date
      ├─ 3. extract_section_tables_from_document()
      │      └─ 페이지별: 제목 3종 탐색 → region clip → extract_table_grid()
      ├─ 4. primary_rating + valid_rating 그리드 → rating_rows_from_section_tables()
      │      └─ 행 없으면 extract_fallback_rows_from_text() (페이지별)
      ├─ 5. financial_indicators 그리드 → ExtractedFinTable → facts_from_fin_tables()
      ├─ 6. rebuild_merged_rows() — YAML longest-match 라벨 분리
      ├─ 7. LabelClassifier.classify_rows() → RatingRecord[]
      ├─ 8. merge_canonical_records() — instrument_key별 병합, validation_warnings
      ├─ 9. build_products() — 상품당 1건, 평가종류 우선순위
      └─ 10. undefined_records 필터링 → 결과 dict 반환
 │
 └─ 배치 종료: commit_batch_outputs()
       ├─ results/{stem}.json, .xlsx  (원자적 replace)
       └─ documents.db — documents / rating·financial grids_raw / rating·financial_norm
```

### 단계별 의사결정 요약

| 단계 | 실패/분기 조건 |
|------|----------------|
| PDF 열기 | `file_error` |
| rebuild 실패 | `parse_error` (그리드는 결과에 포함) |
| 추출 행 0건 + 텍스트 부족 | `text_extraction_failed` |
| 추출 행 0건 + 텍스트 있음 | `parse_error` |
| 분류·집계 성공 | `status`: success / partial / fail |

---

## 6. 데이터 모델

추출과 분류는 **별도 dataclass**로 분리한다 (`common/models.py`).

```
ExtractedTableGrid          # 섹션 표 원본 (headers + rows)
    ↓ rating_from_grid
ExtractedRatingRow          # 추출 단계: rating_status, rating_cells 포함
    ↓ rebuild_merged_rows (라벨 분리)
ExtractedRatingRow[]        # 분할·복원된 행
    ↓ LabelClassifier.classify_rows
RatingRecord                # 분류 단계: instrument_key, classification_status
    ↓ merge_canonical_records
RatingRecord[] (canonical)  # instrument_key별 1건 + confirmed_by
    ↓ build_products
products[]                  # 상품당 최종 1건 (success/fail)

ExtractedFinTable           # 재무 표 그리드
    ↓ facts_from_fin_tables
FinancialFact[]             # metric_key, period, value
```

### RatingStatus

| 값 | 의미 |
|----|------|
| `none` | 등급 토큰 없음 |
| `single` | 등급 1개 확정 |
| `ambiguous` | 등급 복수 — 현재등급 열 적용 후에도 확정 불가 |

### ClassificationStatus

| 값 | 의미 |
|----|------|
| `matched` | YAML `label_dictionary` exact match |
| `undefined` | 미등록 라벨 (자동 확정 없음) |

---

## 7. 추출 파이프라인 (extract)

### 7.1 섹션 탐색 (`extract/sections.py`, `section_catalog.py`)

1. `extract_visual_lines(page)` — 글자 단위 bbox 수집
2. `detect_page_regions(page)` — 좌우 2단(gutter) 감지
3. 섹션별 제목 후보 탐색 (`match_section_key`)
   - **오염 제목 거부**: 재무 수치·ROA/BIS 등이 제목에 붙은 경우 skip
   - `valid_rating` → 좌측, `financial_indicators` → 우측 region 선호
4. `find_section_end_y` — 다음 섹션·종료 패턴까지 clip
5. `extract_table_grid` — PyMuPDF 표 또는 시각 정렬로 `headers`/`rows` 구성

### 7.2 등급 행 파싱 (`extract/row_parser.py`)

핵심 규칙:

1. **행 전체**에서 등급 토큰 후보 수집 (`common/rating_tokens.py`)
2. 후보 1개 → `rating_status=single`
3. 후보 2개 이상 → 헤더에 **「현재등급」** 열이 있으면 그 열만 사용
4. 그래도 복수 → `rating_status=ambiguous`
5. 종목코드(`영구A-05` 등) 오탐 제외 — 경계 정규식으로 방지
6. `evaluation_type` — 열 헤더·라벨 잔여에서 본/수시/신규 등 추론
7. 유효등급 셀: `truncate_valid_row_text` — 재무지표·각주 노이즈 패턴 및 **등급 토큰 직후 한글**에서 cut

### 7.3 병합 라벨·붕괴 셀 복원 (`extract/row_rebuild.py`)

한 셀에 여러 상품 라벨이 붙은 경우(merged row):

1. YAML `label_dictionary`를 **정규화 길이 내림차순**으로 스캔
2. non-overlapping span으로 분할
3. span마다 별도 `ExtractedRatingRow` 생성, 등급 토큰을 순서대로 배분

`종류`·`현재등급`에 복수 평가/등급이 공백으로 붙은 붕괴 행은 복수 상품 라벨이 있을 때 동일 경로로 분할한다.  
**평가대상이 비어 있고** 종류/등급만 붕괴된 primary는 복원 불가 → 스킵(유효등급 섹션에 위임).

### 7.4 재무지표 표 복구 (`extract/fin_tables.py`)

추출 직후 `repair_financial_matrix`:

- 라벨 셀 trailing 수치 분리 (`총자산 3,331,525`)
- 값 셀 복수 수치 concat → 첫 수치만 (`2,111,237 2,348,050`)
- 빈 헤더·값 교차 열을 기간 열로 정렬 후 라벨+기간만 유지

### 7.5 Primary·유효등급 병합 (`extract/merge.py`)

- `instrument_key`별 canonical 1건
- Primary(`pdf_table`/`visual_layout`) 우선
- 유효등급과 등급 일치 시 `confirmed_by: ["valid_rating_section"]`
- 불일치 시 `validation_warnings` (`conflicting_rating_sources`), Primary 유지

### 7.6 Fallback (`extract/fallback.py`)

`primary_rating`·`valid_rating`에서 행이 **하나도 없을 때만** 페이지 평문을 줄 단위 스캔.  
`looks_like_rating_row` + `looks_like_instrument_label` 통과 시 `parse_rating_row_values` 호출.

---

## 8. 분류 파이프라인 (classify)

### 8.1 라벨 분류 (`classify/classifier.py`)

```python
normalized = normalize_label(row.raw_label)  # 공백 제거, NFKC, 대문자
instrument_key = config.normalized_lookup.get(normalized)  # exact only
```

- **matched**: `instrument_key` 확정, `rating`/`outlook`은 추출값 그대로 이전
- **undefined**: YAML `label_dictionary`에 없는 라벨. **자동 확정에 사용하지 않음**

### 8.2 undefined 필터 (`classify/undefined_filter.py`)

`undefined_records`에 넣지 않는 경우:

- `rating_status=none` 이고 rating 없음
- 이메일·전화·재무지표 힌트 라벨
- Primary에서 이미 matched된 라벨의 유효등급 중복

미분류는 결과 JSON에만 남기고, 관리자 **확인 필요** 탭·**상품 사전**으로 처리한다.

### 8.3 정규화 정책 (`common/matching_policy.py`)

| 함수 | 용도 |
|------|------|
| `normalize_text` | 사람이 읽는 형태 (공백 단일화) |
| `normalize_label` | 라벨 lookup 키 (공백 완전 제거) |
| `normalize_metric_label` | 지표 라벨 (단위 괄호·각주 제거 후 공백 제거) |

기동 시 `build_normalized_lookup`이 동일 정규화 키의 상충 매핑을 `InstrumentsConfigError`로 거부한다.

---

## 9. 상품 집계 (products)

`main.py`의 `build_products()`가 `instrument_key`별 최종 1건을 만든다.

### 평가종류 우선순위 (낮을수록 우선)

```
본(본평가) > 수시 > 신규 > 예비 > 정기 > (primary, 타입 없음) > 유효등급
```

### 상품급 해석 (`_resolve_product_group`)

1. 동일 `instrument_key` 그룹에서 최고 우선순위 평가종류만 후보
2. `rating_status=ambiguous` → `multiple_rating_columns`
3. 등급 없음 → `rating_not_found`
4. 동일 우선순위에서 서로 다른 (rating, outlook) → `multiple_ratings`
5. 성공 시 `status=success`, rating/outlook 채움

### PDF급 status

| status | 조건 |
|--------|------|
| `success` | 모든 products가 success |
| `partial` | 일부만 success |
| `fail` | success 0건 또는 파일/파싱 오류 |

---

## 10. 재무지표 처리

### 분류

- `MetricClassifier` → `common/metric_catalog.py`의 `_METRIC_ALIASES`를 `normalize_metric_label` 후 **exact match**
- **`net_income`은 alias `당기순이익`만** — `순이익` 단독·부분 일치 없음
- 그 외 키는 등록 alias 허용 예: `총자산`/`자산총계`, `자기자본`/`자본총계`, BIS·부채비율 변형 등 (`_METRIC_ALIASES`가 원천)

### 정규화 (`classify/fin_normalize.py`)

- 표 헤더에서 기간 파싱 (`parse_period_header`)
- 셀 숫자 파싱 (`parse_numeric_cell`)
- 단위: 라벨 괄호, 표 caption(십억원/억원 등)에서 추론 → `FinancialFact.value` / `value_raw` / `unit`

### Excel 요약 4행 (`export/fin_excel_utils.py`)

기업별 시트 **재무지표(요약)** 는 **항상 4행**. 행 슬롯·채움:

| 행 | 표시명(기본) | 채움 |
|----|--------------|------|
| 1 | 총자산 | `total_assets` 매칭 값, 없으면 빈칸 (표시명은 고정) |
| 2 | 당기순이익 | `net_income`만, 없으면 빈칸 (표시명 고정) |
| 3 | 총차입금 또는 자기자본 | `total_borrowings` → `equity`. 매칭된 쪽의 표시명 사용. 둘 다 없으면 라벨 `총차입금`+빈칸 |
| 4 | 부채비율(%) 등 | `debt_ratio` → `bis_ratio` → `liquidity_ratio` → `leverage`. 매칭된 표시명 사용. 없으면 라벨 `부채비율(%)`+빈칸 |

빈 **값**은 usable 재무 표를 가진 신평사 순서 **NICE → KIS → KR**로만 채운다 (`cascade_summary_rows`).  
신용등급(요약)도 동일 순서로 상품별 첫 성공 등급을 고른다 (`build_cascaded_rating_rows`).

### 기업별 Excel 시트 레이아웃 (`export/excel.py`)

```
개요 (회사명, 최신 평가일)
신용등급(요약)     ← cascade
재무지표(요약)     ← cascade 4행
신용등급(원본)     ← 신평사별 소제목(㈜) + 표, NICE→KIS→KR
재무지표(원본)     ← 동일
```

### 원본(raw) 표시 게이트 (`export/agency_select.py`) — 실패 비표시

추출·인식에 실패한 신평사 블록은 **엑셀 원본에 넣지 않는다.**

| 채널 | 조건 |
|------|------|
| 신용등급(원본) | 해당 신평사 PDF에 `status=success`이고 `rating`이 있는 product ≥1 |
| 재무지표(원본) | `is_usable_financial_table`: 기간열≥2, 기간 헤더 비율≥50%, **라벨 있는 데이터 행≥3** |

게이트를 통과하지 못한 표(빈 `financial_tables`, 라벨 공란 1행, `parse_error` 등)는 요약 cascade에도 원본에도 노출하지 않는다.  
교차검증용 ≥2개 신평사는 **성공 추출만**으로 맞춘다.

### `--renormalize`

`documents.db`의 `financial_grids_raw`만으로 `financial_norm`(API 키 `financial_facts`)을 재생성. PDF 재처리 없이 카탈로그 변경 반영 시 사용.

---

## 11. 결과 스키마·상태·실패 사유

### PDF당 결과 객체 (주요 필드)

| 필드 | 설명 |
|------|------|
| `result_no` | 배치 순번 |
| `company_name`, `agency`, `evaluation_date` | 메타 |
| `status`, `fail_reason` | PDF급 (`fail_reason`: `{code, message}`) |
| `products` | 상품별 최종 1건 |
| `records` | 전체 `RatingRecord` (canonical 병합 후) |
| `validation_warnings` | Primary·유효등급 불일치 등 |
| `undefined_records` | YAML 미등록 |
| `tables` | 등급·재무 원본 그리드 |
| `financial_tables`, `financial_facts`, `undefined_metrics` | 재무 |
| `file_hash` | SHA-256 |
| `extracted_text_chars`, `rating_token_count` | 디버그·실패 판정용 |

### fail_reason 코드

**PDF급** (`common/fail_reasons.py` 우선순위 순):

| code | 의미 |
|------|------|
| `file_error` | PDF 열기 실패 |
| `text_extraction_failed` | 행 없음 + 텍스트·등급 토큰 부족 |
| `parse_error` | 텍스트는 있으나 행/표 구성 실패 |
| `label_not_found` | 등급은 있으나 라벨 없음 |
| `undefined_label` | 등급 있는 미등록 라벨 |

**상품급** (`products[].fail_reason`):

| code | 의미 |
|------|------|
| `multiple_rating_columns` | 현재등급 열 적용 후에도 등급 미확정 |
| `multiple_ratings` | 동일 상품·우선순위에서 등급/전망 충돌 |
| `rating_not_found` | YAML 매칭됐으나 등급 없음 |

---

## 12. 출력·저장

`commit_batch_outputs(results, stem=...)`:

| 출력 | 경로 | 내용 |
|------|------|------|
| JSON | `results/{stem}.json` | 전체 결과 배열 (`undefined_records` 포함) |
| Excel (공개) | `results/{stem}.xlsx` | 시트 `신용등급` + 회사별 시트 |
| documents.db | `admin/data/documents.db` | PDF 요약·등급/재무 raw·추출 결과 (아래) |

- stem 기본값: `result_YYYYMMDD` (`RESULT_FILENAME_PREFIX` + 실행일)
- JSON/Excel은 tmp → `os.replace()` 원자 교체

### documents.db 스키마

키: `doc_id` = PDF 내용 SHA-256 hex의 **앞 16자** (동일 내용 → 동일 id).  
`file_hash`는 전체 64자 hex를 `documents`에 UNIQUE로 보관. 자식 테이블 첫 열은 `doc_id`, 행 PK는 `row_id AUTOINCREMENT` (`sqlite_sequence`는 SQLite 자동 관리).

| 테이블 | 역할 |
|--------|------|
| `documents` | PDF 요약 — 메타, status, evaluation_date, fail_reason |
| `rating_grids_raw` | 신용등급 로우 — `primary_rating` / `valid_rating` 그리드 |
| `financial_grids_raw` | 재무지표 로우 — `financial_indicators` 그리드 (`--renormalize` 입력) |
| `rating_norm` | 신용등급 추출 결과 — 상품당 1행 (`products` 정규화) |
| `financial_norm` | 재무지표 추출 결과 — 지표·기간·값 (API `financial_facts`) |

동일 `doc_id`로 재실행하면 해당 문서의 자식 행을 지우고 최신으로 교체한다.

### Excel 공개 시트 열

`No`, `회사명`, `신평사`, `상품분류`, `신용등급`, `등급전망`, `평가일`, `원본파일명`  
(`build_excel_public_rows`: **처리상태 success**이고 신용등급이 있는 행만)

관리자용 추가 열(상품분류_Key, 원본라벨, 처리상태 등)은 `export/excel.py` `ADMIN_COLUMNS` 참고.  
기업별 시트 구조·raw 게이트는 [§10](#10-재무지표-처리) 참고.

---

## 13. 설정 (.env)

앱 루트 `CreditDocStruct/CreditDocStruct/.env` (템플릿: `.env.example`)

| 키 | 용도 | 기본 |
|----|------|------|
| `INPUT_DIR` | PDF 입력 폴더 | **필수, 코드 기본값 없음** |
| `INSTRUMENTS_YAML_PATH` | 상품·라벨 YAML | `config/instruments.yaml` |
| `RESULT_DIR` | 결과 폴더 | `results` |
| `DOCUMENT_DB_PATH` | 문서·재무 DB | `admin/data/documents.db` |
| `ADMIN_BACKUP_DIR` | 상품 사전 YAML 쓰기 전 백업 폴더 | `admin/backup` |
| `MAX_PDF_PAGES` | PDF 스캔 상한 | `1` |
| `MIN_EXTRACTED_TEXT_CHARS` | 텍스트 추출 실패 판정 | `50` |

상대 경로는 앱 루트(`CreditDocStruct/CreditDocStruct/`) 기준.  
미분류 라벨 저장소는 결과 JSON의 `undefined_records`이다.

---

## 14. 실행 방법

권장: Python 3.11/3.12 64-bit, 앱 루트 `CreditDocStruct/CreditDocStruct/`.

### 최초 설정

```bat
copy .env.example .env
REM .env 의 INPUT_DIR 에 PDF 폴더 경로 설정

admin\setup_admin.bat
REM .venv 생성 + requirements.txt + admin\requirements.txt 설치
```

### PDF 추출

```bash
# CLI
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe main.py report.pdf
.venv\Scripts\python.exe main.py ./other_pdfs
.venv\Scripts\python.exe main.py -o batch
.venv\Scripts\python.exe main.py --renormalize

# 동일: admin\run_extract.bat  (인자 없이 INPUT_DIR 전체 배치)
```

| CLI 옵션 | 설명 |
|----------|------|
| `input` | PDF/폴더 (생략 시 `INPUT_DIR`) |
| `-o`, `--output` | 결과 stem |
| `--non-recursive` | 하위 폴더 제외 |
| `--renormalize` | documents.db `financial_grids_raw` → `financial_norm` 재생성 |

### 관리자 웹

```bat
admin\run_admin.bat
REM http://localhost:8501  /  사내망 http://<서버IP>:8501
```

상세는 [§17](#17-관리자-앱-간략)·[`admin/README.md`](CreditDocStruct/admin/README.md).

---

## 15. 공개 API

`main.py`에서 외부 Python 코드가 import할 수 있는 함수. CLI 없이 프로그램 내에서 호출할 때 사용.

### `extract_credit_report(pdf_path, ...) -> dict`

단일 PDF 처리. **파일 저장 없이** 결과 dict 반환.

### `commit_batch_outputs(results, stem=...) -> (json, excel, doc_db)`

결과 리스트를 JSON·Excel·documents.db에 원자 저장.

```python
from main import extract_credit_report, commit_batch_outputs

result = extract_credit_report("report.pdf")
commit_batch_outputs([result], stem="batch")
```

일반 운영은 CLI(`python main.py`)만으로 충분하다. 다른 서비스·스크립트·노트북에서 dict를 바로 받아 후처리할 때 공개 API를 쓴다.

---

## 16. 테스트

```bash
cd C:\mycode\CreditDocStruct\CreditDocStruct
.venv\Scripts\python.exe -m pytest tests -q
```

| 테스트 파일 | 검증 범위 |
|-------------|-----------|
| `test_instrument_extraction.py` | 라벨 match, products, fail_reason, canonical 병합 |
| `test_section_pipeline.py` | 섹션 그리드, 현재등급 열, 행 선택 |
| `test_financial_metrics.py` | 재무지표 분류·요약·renormalize |
| `test_excel_admin_split.py` | Excel 공개/admin·기업별 시트 |
| `test_matching_policy.py` | 정규화·lookup 충돌 |
| `test_yaml_service.py`, `test_exception_service.py` | YAML managed_by·예외 대기열 |
| `test_result_service.py`, `test_app_helpers.py` | 결과 조회 헬퍼 |

새 라벨·섹션·등급 규칙 추가 시 해당 영역 테스트와 `tests/label_variants.json`을 함께 갱신한다.  
테스트 작성·유지 시 [§3.4](#34-테스트)를 지킨다.

---

## 17. 관리자 앱 (간략)

Streamlit 관리자 웹 앱. 진입점 `admin/admin_main.py`, 개발자 매뉴얼은 [`admin/README.md`](CreditDocStruct/admin/README.md).

| 항목 | 내용 |
|------|------|
| 최초 설치 | `admin/setup_admin.bat` — `.venv` + `requirements.txt` + `admin/requirements.txt` |
| 추출 래퍼 | `admin/run_extract.bat` — `.venv`로 `main.py` (`.env` `INPUT_DIR`). UI와 별개 |
| 웹 실행 | `admin/run_admin.bat` — `--server.address 0.0.0.0 --server.port 8501`. 로컬 `http://localhost:8501`, 사내망 `http://<서버IP>:8501` (방화벽 8501·동일 망) |
| 인증 | 앱 로그인 없음. 사내망 신뢰 전제 |
| 탭 | 결과 조회 · 확인 필요 · 상품 사전 · 운영 가이드 |
| 결과 조회 | `results/*.json`, 신평사·회사 필터, 공개 표, 행 선택 시 raw 재무. 재무 없으면 `st.error`만. Excel은 success+등급만 |
| 확인 필요 | `exception_service.collect_exceptions` (읽기 전용). `action`은 `ops_guide` §4와 동기화 |
| 상품 사전 | `instruments.yaml` 라벨. `managed_by: admin`만 삭제. 쓰기 전 `admin/backup/` |
| 운영 가이드 | `content/ops_guide.md` (운영자용). 모듈·스키마는 이 README / admin README |
| 사이드바 | 새로고침, 최신 mtime JSON 기준 확인 필요 건수 |
| UI 스타일 | `admin/ui/theme.py`, `.streamlit/config.toml` |

```
run_extract.bat | main.py → results/*.json · documents.db
  → 확인 필요 → 상품 사전(YAML) → 재추출
```

관리자 화면에 PDF 추출·업로드는 없다. 원격 브라우저가 클라이언트 PC 로컬 폴더를 읽어 추출하지도 않는다. 상세는 [`admin/README.md`](CreditDocStruct/admin/README.md).

---

## 18. 유지보수 가이드

### 라벨이 인식되지 않을 때

1. 관리자 **확인 필요**에서 미분류 항목·원문 라벨 확인 (또는 JSON `undefined_records`)
2. **상품 사전**에서 해당 상품에 원문 라벨 추가(`managed_by: admin`) — 또는 개발자가 `config/instruments.yaml` `label_dictionary`에 직접 등록(`active: true`)
3. 기동 시 정규화 충돌이 없는지 확인 (`load_instruments_config`)
4. 재추출

정규화 규칙 변경은 `common/matching_policy.py`만 수정. YAML에 normalization 블록을 두지 않는다.

### 등급이 잘못 추출될 때

1. `tables` / `records`에서 원본 그리드·`rating_status` 확인
2. `extract/row_parser.py` — 현재등급 열·토큰 경계·`truncate_valid_row_text`
3. `extract/rating_from_grid.py` — 재무 노이즈·등급토큰만 라벨 행 제거
4. `extract/row_rebuild.py` — 병합/붕괴 셀 복원
5. `common/rating_tokens.py` — 등급 패턴

### 섹션/표가 안 잡힐 때

1. `extract/section_catalog.py` — 제목 alias·종료 패턴
2. `extract/regions.py` — 2단 레이아웃·clip
3. `MAX_PDF_PAGES` 증가 여부

### 재무지표가 Excel 원본에 안 보일 때

1. JSON `financial_tables`가 비었는지(추출 실패) vs 표는 있으나 usable 미달인지 확인
2. `extract/fin_tables.py` — `repair_financial_matrix`, 제목·visual 폴백
3. `export/agency_select.py` — `is_usable_financial_table` (기간·라벨 행 게이트; **완화하지 않음**)

### 재무지표 추가·변경

1. `common/metric_catalog.py` — `METRIC_DEFINITIONS`, `_METRIC_ALIASES`
2. 요약 Excel 행 규칙 변경 시 `export/fin_excel_utils.py`
3. `--renormalize`로 기존 documents.db 반영

### 코드 수정 시 지켜야 할 것

- 오케스트레이션을 `main.py` 밖으로 옮기지 않는다 (`run_extract.bat`은 래퍼만 허용)
- `ExtractedRatingRow`와 `RatingRecord` 역할을 섞지 않는다
- 분류기가 `rating`을 재계산하지 않게 한다
- undefined 추천을 자동 확정에 쓰지 않는다
- 경로를 코드에 하드코딩하지 않는다
- 추출 실패·usable 미달 데이터를 Excel/원본에 억지로 넣지 않는다 (게이트 유지)
- 운영자 문구는 `ops_guide.md`, 개발 계약은 이 README / `admin/README.md`에 둔다
- 예외 `action`/`type_label` 변경 시 `ops_guide.md`와 동기화한다

### AI 유지보수 시 권장 순서

1. [§1](#1-추출-대상과-범위) — 요청이 In/Out of Scope인지 판단
2. [§3](#3-아키텍처개발-규칙) — 가드레일 위반 없는지 확인
3. [§5](#5-전체-처리-흐름) — 어느 단계 문제인지 특정
4. 해당 패키지 파일 + `tests/test_*.py`
5. 문서·`ops_guide`가 코드와 어긋나면 함께 수정 ([§3.5](#35-문서화))

---

## 19. 알려진 한계

| 항목 | 동작 |
|------|------|
| 동일 상품·동일 우선순위 등급 충돌 | 해당 상품만 `multiple_ratings`, PDF는 `partial`/`fail` |
| 1페이지 기본 스캔 | 2페이지 이후 등급·재무 표는 기본 설정에서 누락 |
| 스캔 PDF·이미지 기반 | 텍스트 레이어 없으면 `text_extraction_failed` |
| 미등록 라벨 | 자동 확정 없음 — YAML 수동 등록 필요 |
| Excel 원본·요약 | 성공/usable 게이트 통과분만 표시. NICE 요지 등에서 재무 미추출 시 해당 신평사 블록 생략 |
| 발행자(`issuer`) 등 | PDF에 해당 상품 행이 없으면 합성하지 않음 (다른 신평사·요약 cascade로만 보완) |
| 재무지표 8키 | `매출액`·`EBITDA` 등은 카탈로그 밖 → `undefined_metrics`로 남을 수 있음 (정상) |

운영 루프: `run_extract.bat`/`main.py` → JSON `undefined_records`/확인 필요 → 상품 사전 → 재추출.
