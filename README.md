# CreditDocStruct

**신평서 데이터 구조화 프로젝트 — 개발자 문서**

NICE신용평가 · 한국신용평가 · 한국기업평가가 발행한 **신용평가서 PDF**에서  
평가대상 라벨·신용등급·등급전망·재무지표를 추출해 구조화된 JSON/Excel로 저장한다.

이 문서만 읽어도 프로젝트의 **추출 범위, 처리 흐름, 모듈 책임, 분류 정책**을 파악할 수 있도록 작성했다.  
AI·후임 개발자가 유지보수할 때는 이 README와 `.cursor/rules/`를 함께 참고한다.

---

## 목차

1. [추출 대상과 범위](#1-추출-대상과-범위)
2. [기술 스택](#2-기술-스택)
3. [아키텍처 원칙](#3-아키텍처-원칙)
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
| `file_hash` | SHA-256 | `export/undefined_store.py` |

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
| 재무지표 YAML/관리자 검수 | 코드 카탈로그만 사용 |
| `target_instrument` 지정 추출 | 없음 — PDF에서 검출된 모든 상품을 자동 탐색 |

### 1.4 상품(instrument) 목록

`config/instruments.yaml`의 `instruments`에 정의된 9키:

`issuer`, `insurance_payment`, `senior_unsecured`, `guaranteed_bond`, `subordinated`, `coco_t1`, `coco_t2`, `commercial_paper`, `short_term_bond`

라벨→상품 매핑은 `label_dictionary`에만 등록한다. 동일 정규화 라벨이 서로 다른 `instrument_key`로 매핑되면 **기동 시 거부**한다.

---

## 2. 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3 |
| PDF | PyMuPDF (`pymupdf`) — 텍스트·좌표·표 추출 |
| 설정 | `python-dotenv` (.env), `PyYAML` (instruments.yaml) |
| 출력 | `pandas`, `openpyxl` (Excel), JSON (stdlib) |
| DB | SQLite (`admin.db`, `documents.db`) |
| 테스트 | `pytest` |
| 관리자 UI | Streamlit (`admin/`, 별도 requirements) |

---

## 3. 아키텍처 원칙

`.cursor/rules/architecture.mdc`와 동일한 규칙을 따른다.

1. **오케스트레이션 단일 진입점** — PDF 배치 처리 루프는 `main.py`만 담당. 다른 패키지에 CLI/배치 루프를 두지 않는다.
2. **추출·분류 모델 분리** — `ExtractedRatingRow`(추출) → `RatingRecord`(분류). 등급 값은 추출 단계에서 확정하고 분류기는 **재계산하지 않는다**.
3. **정책 단일 원천** — 라벨 정규화·추천·검증은 `common/matching_policy.py`. YAML에는 상품·라벨 딕셔너리만 둔다.
4. **재무지표는 코드 카탈로그** — `common/metric_catalog.py` (8키). `metrics.yaml` 없음.
5. **경로·상수** — `.env` → `common/settings.py`로만 읽는다. 코드에 하드코딩하지 않는다.
6. **원자적 저장** — JSON/Excel은 임시 파일 작성 → `os.replace()`로 교체 (`commit_batch_outputs`).
7. **자동 상품 탐색** — 사용자가 대상 상품을 지정하지 않는다. PDF에서 검출된 라벨을 YAML로 분류해 `products`를 만든다.

---

## 4. 디렉터리 구조

```
CreditDocStruct/
├── README.md                 # 이 문서 (개발자용)
├── .cursor/rules/            # AI·개발 규칙 (architecture, extraction, taxonomy, testing)
└── CreditDocStruct/          # 앱 루트 (실행 cwd)
    ├── main.py               # CLI + extract_credit_report + commit_batch_outputs
    ├── requirements.txt
    ├── .env / .env.example
    ├── config/
    │   └── instruments.yaml  # 상품 9종 + label_dictionary
    ├── common/               # 설정, 모델, 정책, 등급 토큰, fail_reason
    ├── agency/               # 신평사 식별, 회사명, 기관별 레이아웃
    ├── extract/              # PDF → 섹션 그리드 → ExtractedRatingRow / ExtractedFinTable
    ├── classify/             # YAML exact match, 재무지표 분류, undefined 추천
    ├── export/               # JSON, Excel, SQLite 저장
    ├── admin/                # Streamlit 관리자 (2탭: 결과·라벨검수)
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
| `extract/rating_from_grid.py` | — | 그리드→`ExtractedRatingRow`, 재무 노이즈 행 제거 |
| `extract/row_parser.py` | — | 행 전체 등급 탐색, **현재등급 열** 선택, `rating_status` |
| `extract/row_rebuild.py` | — | 병합 라벨 YAML longest-match 분할 |
| `extract/merge.py` | — | Primary·유효등급 canonical 병합, `confirmed_by` |
| `extract/fallback.py` | — | 섹션 행 없을 때 평문 줄 스캔 |
| `extract/fin_tables.py` | — | 재무 표 파싱 보조 (기간 헤더, 숫자 셀) |
| `classify/classifier.py` | — | `LabelClassifier` — YAML exact match |
| `classify/metric_classifier.py` | — | `MetricClassifier` — 코드 카탈로그 exact match |
| `classify/fin_normalize.py` | — | `ExtractedFinTable` → `FinancialFact[]` |
| `classify/recommend.py` | — | undefined 라벨 char n-gram cosine 추천 (자동 확정 안 함) |
| `classify/undefined_filter.py` | — | undefined_records·SQLite 누적 대상 필터 |
| `export/json_io.py` | — | JSON 직렬화 |
| `export/excel.py` | — | 공개/관리자 Excel, 기업별 시트 |
| `export/fin_excel_utils.py` | — | 재무 요약 4행 규칙 |
| `export/undefined_store.py` | — | 미분류 라벨 SQLite |
| `export/document_store.py` | — | 문서·재무 raw/facts SQLite, `--renormalize` |

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
       ├─ admin.db — 미분류 라벨 occurrence
       └─ documents.db — 문서·재무 raw/facts
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
| `undefined` | 미등록 라벨 (추천 suggestions 첨부, 자동 확정 없음) |

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

### 7.3 병합 라벨 분리 (`extract/row_rebuild.py`)

한 셀에 여러 상품 라벨이 붙은 경우(merged row):

1. YAML `label_dictionary`를 **정규화 길이 내림차순**으로 스캔
2. non-overlapping span으로 분할
3. span마다 별도 `ExtractedRatingRow` 생성, 등급 토큰을 순서대로 배분

### 7.4 Primary·유효등급 병합 (`extract/merge.py`)

- `instrument_key`별 canonical 1건
- Primary(`pdf_table`/`visual_layout`) 우선
- 유효등급과 등급 일치 시 `confirmed_by: ["valid_rating_section"]`
- 불일치 시 `validation_warnings` (`conflicting_rating_sources`), Primary 유지

### 7.5 Fallback (`extract/fallback.py`)

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
- **undefined**: `recommend_instruments()`로 top-k 추천 (`RECOMMENDATION.min_score` 미만 제외). **자동 확정에 사용하지 않음**

### 8.2 undefined 필터 (`classify/undefined_filter.py`)

`undefined_records`·SQLite 누적에서 제외:

- `rating_status=none` 이고 rating 없음
- 이메일·전화·재무지표 힌트 라벨
- Primary에서 이미 matched된 라벨의 유효등급 중복

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

- `MetricClassifier` → `common/metric_catalog.py`의 `_METRIC_ALIASES` exact match
- **`net_income`은 `당기순이익`만** — `순이익` 부분 일치 금지

### 정규화 (`classify/fin_normalize.py`)

- 표 헤더에서 기간 파싱 (`parse_period_header`)
- 셀 숫자 파싱 (`parse_numeric_cell`)
- 단위: 라벨 괄호, 표 caption(십억원/억원 등)에서 추론

### Excel 요약 4행 (`export/fin_excel_utils.py`)

기업별 시트 **재무지표(요약)** 는 항상 4행, 표시명 고정:

| 행 | 표시명 | 값 결정 |
|----|--------|---------|
| 1 | 총자산 | exact 매칭, 없으면 빈칸 |
| 2 | 당기순이익 | exact `당기순이익`만 |
| 3 | 총차입금 또는 자기자본 | 총차입금 → 자기자본 → 라벨 `총차입금`+빈칸 |
| 4 | 부채비율(%) / BIS / 유동성 / 레버리지 | 순서대로 cascade, 없으면 `부채비율(%)`+빈칸 |

### `--renormalize`

`documents.db`에 저장된 raw 재무 그리드만으로 `financial_facts`를 재생성. PDF 재처리 없이 카탈로그 변경 반영 시 사용.

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
| `undefined_records` | YAML 미등록 + `suggestions` |
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
| JSON | `results/{stem}.json` | 전체 결과 배열 |
| Excel (공개) | `results/{stem}.xlsx` | 시트 `신용등급` + 회사별 시트 |
| admin.db | `admin/data/admin.db` | 미분류 라벨 occurrence |
| documents.db | `admin/data/documents.db` | 문서 메타, 재무 raw/facts |

- stem 기본값: `result_YYYYMMDD` (`RESULT_FILENAME_PREFIX` + 실행일)
- JSON/Excel은 tmp → `os.replace()` 원자 교체

### Excel 공개 시트 열

`No`, `회사명`, `신평사`, `상품분류`, `신용등급`, `등급전망`, `평가일`, `원본파일명`

관리자용 추가 열(상품분류_Key, 원본라벨, 처리상태 등)은 `export/excel.py` `ADMIN_COLUMNS` 참고.

---

## 13. 설정 (.env)

앱 루트 `CreditDocStruct/CreditDocStruct/.env` (템플릿: `.env.example`)

| 키 | 용도 | 기본 |
|----|------|------|
| `INPUT_DIR` | PDF 입력 폴더 | **필수, 코드 기본값 없음** |
| `INSTRUMENTS_YAML_PATH` | 상품·라벨 YAML | `config/instruments.yaml` |
| `RESULT_DIR` | 결과 폴더 | `results` |
| `ADMIN_DB_PATH` | 미분류 라벨 DB | `admin/data/admin.db` |
| `DOCUMENT_DB_PATH` | 문서·재무 DB | `admin/data/documents.db` |
| `ADMIN_BACKUP_DIR` | YAML 백업 | `admin/backup` |
| `MAX_PDF_PAGES` | PDF 스캔 상한 | `1` |
| `MIN_EXTRACTED_TEXT_CHARS` | 텍스트 추출 실패 판정 | `50` |

상대 경로는 앱 루트(`CreditDocStruct/CreditDocStruct/`) 기준.

---

## 14. 실행 방법

```bash
cd C:\mycode\CreditDocStruct\CreditDocStruct
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
# .env에 INPUT_DIR 설정

# .env INPUT_DIR 배치 처리
.venv\Scripts\python.exe main.py

# 단일 PDF / 다른 폴더
.venv\Scripts\python.exe main.py report.pdf
.venv\Scripts\python.exe main.py ./other_pdfs

# 결과 파일명 stem
.venv\Scripts\python.exe main.py -o batch

# 재무 facts만 재생성
.venv\Scripts\python.exe main.py --renormalize
```

| CLI 옵션 | 설명 |
|----------|------|
| `input` | PDF/폴더 (생략 시 `INPUT_DIR`) |
| `-o`, `--output` | 결과 stem |
| `--non-recursive` | 하위 폴더 제외 |
| `--renormalize` | documents.db 기반 financial_facts 재생성 |

---

## 15. 공개 API

`main.py`에서 외부 Python 코드가 import할 수 있는 함수. CLI 없이 프로그램 내에서 호출할 때 사용.

### `extract_credit_report(pdf_path, ...) -> dict`

단일 PDF 처리. **파일 저장 없이** 결과 dict 반환.

### `commit_batch_outputs(results, stem=...) -> (json, excel, admin_db, doc_db)`

결과 리스트를 JSON·Excel·SQLite에 원자 저장.

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
| `test_candidate_store.py`, `test_yaml_service.py` | admin 서비스·YAML |
| `test_result_service.py`, `test_app_helpers.py` | 결과 조회 헬퍼 |

새 라벨·섹션·등급 규칙 추가 시 해당 영역 테스트와 `tests/label_variants.json`을 함께 갱신한다.

---

## 17. 관리자 앱 (간략)

Streamlit 기반 비개발자 운영 UI (`admin/admin_main.py`). 상세는 `admin/README.md` 참고.

- **2탭:** 결과 조회 · 라벨 검수 (작업 이력·라벨 조회·백업 복원 UI는 제거)
- 미분류 라벨 검수 → `instruments.yaml` 등록 (`admin.db`)
- 추출 결과 공개 컬럼 조회 · 비개발자 Excel(기업별 시트 포함) 다운로드
- 실행: `admin/run_admin.bat`

핵심 파이프라인(`main.py`)과 **별도 진입점**이며, 배치 추출 로직은 admin에 두지 않는다.

---

## 18. 유지보수 가이드

### 라벨이 인식되지 않을 때

1. 결과 JSON의 `undefined_records` 또는 `records`에서 `raw_label`·`normalized_label` 확인
2. `config/instruments.yaml` `label_dictionary`에 **원문 라벨** 추가 (`active: true`)
3. 기동 시 정규화 충돌이 없는지 확인 (`load_instruments_config`)
4. 재실행

정규화 규칙 변경은 `common/matching_policy.py`만 수정. YAML에 normalization 블록을 두지 않는다.

### 등급이 잘못 추출될 때

1. `tables` / `records`에서 원본 그리드·`rating_status` 확인
2. `extract/row_parser.py` — 현재등급 열·토큰 경계
3. `extract/rating_from_grid.py` — 재무 노이즈 행 제거
4. `common/rating_tokens.py` — 등급 패턴

### 섹션/표가 안 잡힐 때

1. `extract/section_catalog.py` — 제목 alias·종료 패턴
2. `extract/regions.py` — 2단 레이아웃·clip
3. `MAX_PDF_PAGES` 증가 여부

### 재무지표 추가·변경

1. `common/metric_catalog.py` — `METRIC_DEFINITIONS`, `_METRIC_ALIASES`
2. 요약 Excel 행 규칙 변경 시 `export/fin_excel_utils.py`
3. `--renormalize`로 기존 documents.db 반영

### 코드 수정 시 지켜야 할 것

- 오케스트레이션을 `main.py` 밖으로 옮기지 않는다
- `ExtractedRatingRow`와 `RatingRecord` 역할을 섞지 않는다
- 분류기가 `rating`을 재계산하지 않게 한다
- undefined 추천을 자동 확정에 쓰지 않는다
- 경로를 코드에 하드코딩하지 않는다

### AI 유지보수 시 권장 순서

1. 이 README §1(범위) — 요청이 In/Out of Scope인지 판단
2. §5 흐름도 — 어느 단계 문제인지 특정
3. 해당 패키지 파일 + `tests/test_*.py`
4. `.cursor/rules/` (architecture, extraction, taxonomy, testing)

---

## 19. 알려진 한계

| 항목 | 동작 |
|------|------|
| 동일 상품·동일 우선순위 등급 충돌 | 해당 상품만 `multiple_ratings`, PDF는 `partial`/`fail` |
| 1페이지 기본 스캔 | 2페이지 이후 등급 표는 기본 설정에서 누락 |
| 스캔 PDF·이미지 기반 | 텍스트 레이어 없으면 `text_extraction_failed` |
| 미등록 라벨 | 자동 확정 없음 — YAML 수동 등록 필요 |

미분류 라벨은 `admin.db`에 누적된다. 운영 루프: 추출 → undefined 확인 → YAML 등록 → 재추출.
