# CreditRateFinder 프로젝트 보고서

**작성일:** 2026-07-21  
**대상:** NICE신용평가 · 한국신용평가 · 한국기업평가 신용평가서 PDF  
**목적:** 신용등급·등급전망 자동 추출 및 구조화

---

## 1페이지 — 핵심 요약 (비개발자용)

### 이 시스템은 무엇을 하나요?

**CreditRateFinder**는 신평사 3사(NICE신용평가, 한국신용평가, 한국기업평가)가 발행한 **신용평가서 PDF**에서 **평가대상(상품)별 신용등급과 등급전망**을 자동으로 읽어 내는 프로그램입니다.  
처리 결과는 **엑셀·JSON**으로 저장되며, PDF 한 건당 **상품별 등급 목록(`products`)** 이 확정됩니다.

### 왜 만들었나요?

| 문제 | 해결 |
|------|------|
| PDF마다 표 형식·문구가 달라 사람이 일일이 확인해야 함 | 표·레이아웃·텍스트를 단계적으로 분석해 등급을 자동 추출 |
| 「무보증사채」「본」「CP」 등 표기가 신평사·시기마다 다름 | **라벨 사전(YAML)** 으로 표준 상품에 매핑. 새 표기는 사전에 추가하면 즉시 반영 |
| 등급을 못 찾거나 새 라벨이 나오면 원인 추적이 어려움 | 실패 사유 코드·미등록 라벨 목록을 별도 저장해 **검토·보완 루프** 지원 |

### 한 장으로 보는 전체 흐름

```
[PDF 폴더]  →  [자동 읽기·표 추출]  →  [라벨·등급 해석]
       →  [상품 분류]  →  [대표 등급 확정]  →  [엑셀 / JSON 저장]
                              ↓
                    [미등록 라벨 → 검토 목록 누적]
```

1. **입력:** 지정 폴더(또는 단일 PDF)의 신용평가서
2. **추출:** 「평가 개요」「평가 등급」 표와 「유효등급」 구역에서 행 단위로 라벨·등급·전망 수집
3. **분류:** 등록된 라벨 사전과 **정확히 일치**하는지 확인 → 발행자·무보증사채·CP 등 표준 상품으로 분류
4. **확정:** 「본」「본평가」 우선 규칙으로 PDF당 대표 등급 1건 선택
5. **출력:** `result/` 아래 JSON·엑셀, 미등록 라벨은 `admin/data/admin.db`(SQLite)에 누적

### 비개발자도 유지보수할 수 있나요?

- **라벨 사전:** `config/instruments.yaml`의 **라벨 사전**에 새 문구를 추가·수정하면, 코드 수정 없이 다음 실행부터 반영됩니다.
- **관리자 웹 앱(구현 완료):** 미등록 라벨을 브라우저에서 검토하고 클릭만으로 사전에 반영할 수 있는 **유지보수용 웹 애플리케이션(Streamlit)** 을 제공합니다. alias 추가·제외 시 YAML을 자동 백업 후 안전하게 갱신하며, 변경 이력을 남깁니다. (`admin/` 폴더, `setup_admin.bat` / `run_admin.bat` 더블클릭 실행)

### 결과를 어떻게 읽나요?

| 파일 | 내용 |
|------|------|
| `result/result_YYYYMMDD.xlsx` | 상품당 1행 — 회사명, 신평사, 상품·평가종류·등급·전망, 처리 성공/실패 |
| `result/result_YYYYMMDD.json` | 상세 기록 — 전체 상품 목록, 실패 사유, 검증 경고 |
| `admin/data/admin.db` | YAML에 없는 라벨 목록 (SQLite, 중복 없이 누적, 유사 라벨 추천·검수 상태 포함) |

**성공(`success`):** 대표 등급이 자동 확정됨  
**실패(`fail`):** 복수 상품·등급 불명·라벨 미등록 등 — `fail_reason` 코드로 원인 확인

### 설계 원칙 (한 줄)

> **범용:** 3사 PDF 공통 파이프라인  
> **확장:** 새 라벨은 YAML 추가만으로 대응  
> **투명:** 실패·미등록은 기록을 남겨 사람이 보완

<div style="page-break-after: always;"></div>

---

## 2페이지 이후 — 상세 기술 보고

### 목차

| 단계 | 절 | 주제 |
|:----:|----|------|
| 0 | [§0. 프로젝트 개요](#0-프로젝트-개요) | 범위·아키텍처·산출물 |
| 1 | [§1. 입력 및 환경](#1-입력-및-환경) | PDF 수집·설정 |
| 2 | [§2. PDF 구조 추출](#2-pdf-구조-추출) | 표·레이아웃·텍스트 |
| 3 | [§3. Primary·유효등급 구역](#3-primary유효등급-구역) | 이중 추출 전략 |
| 4 | [§4. 라벨·행 재구성](#4-라벨행-재구성) | 병합 셀·종목명 분리 |
| 5 | [§5. 등급·전망 추출](#5-등급전망-추출) | 토큰 검증·열 선택 |
| 6 | [§6. 상품 분류](#6-상품-분류) | YAML exact match |
| 7 | [§7. 병합·검증](#7-병합검증) | Primary vs 유효등급 |
| 8 | [§8. 대표 등급 확정](#8-대표-등급-확정) | selected·fail_reason |
| 9 | [§9. 결과 저장](#9-결과-저장) | JSON·Excel·undefined |
| 10 | [§10. 유지보수 체계](#10-유지보수-체계) | YAML·Admin 웹 앱 |
| 11 | [§11. 한계·향후](#11-한계향후) | 알려진 제약 |

---

### 0. 프로젝트 개요

#### 문제 상황

- 국내 3대 신평사 신용평가서는 **PDF 표 레이아웃·용어·열 구성**이 제각각이다.
- 「평가 개요」「유효등급」 등 **섹션별로 정보가 분산**되어 있어, 단순 텍스트 검색만으로는 등급과 상품을 안정적으로 연결하기 어렵다.
- 상품명 표기(예: `무보증사채(본)`, `CP`, `Coco(AT1)`)는 **지속적으로 변형**되며, 규칙 기반 하드코딩은 유지보수 비용이 크다.

#### 해결 방안

- **단계형 추출 파이프라인:** 표(table) → 시각 레이아웃(visual) → 평문(fallback) 순으로 구조화된 행(`ExtractedRatingRow`)을 만든다.
- **설정 주도 분류:** 상품·라벨 정의를 `config/instruments.yaml`에 분리하여 **코드 배포 없이** 신규 표기를 수용한다.
- **단일 오케스트레이션:** 모든 처리 흐름을 `main.py` 한 곳에서 관리해 동작을 예측 가능하게 한다.
- **운영 루프:** 미등록 라벨·실패 건을 `admin/data/admin.db`(SQLite)에 누적하고, 비개발자용 Admin 웹 앱과 연계해 검토·YAML 반영을 전제로 설계한다.

#### 시스템 구조 (모듈)

```
main.py                 ← 유일한 추출 오케스트레이션
├── agency/             신평사 식별·회사명·레이아웃 힌트
├── extract/            표·visual·유효등급·행 파싱·병합
├── classify/           YAML exact match·undefined 필터·추천
├── export/             JSON·Excel·undefined_store(SQLite 어댑터)
├── common/             설정·매칭 정책·모델·등급 토큰·실패 코드
├── admin/              관리자 웹 앱 (Streamlit, SQLite, YAML 백업·복원)
│   ├── admin_main.py   Streamlit 진입점
│   ├── views/          화면 (검수·라벨·이력·결과)
│   ├── ui/             테마·문구 헬퍼
│   ├── services/       SQLite·YAML·결과 서비스
│   ├── data/           admin.db
│   └── backup/         YAML 백업
└── config/instruments.yaml   # 상품·라벨 딕셔너리만
```
관리자 앱은 추출 파이프라인과 분리된 별도 진입점(`admin/admin_main.py`)이며,
추출 로직과는 SQLite(`admin.db`)와 `instruments.yaml`을 통해서만 연결된다.

---

### 1. 입력 및 환경

#### 문제 상황

- 처리 대상 PDF 경로가 실행마다 달라질 수 있고, 배치·단건 실행을 모두 지원해야 한다.
- 라벨 사전·결과 경로·페이지 스캔 상한 등 **운영 파라미터**를 코드에 박아 두면 환경별 재배포가 필요하다.

#### 해결 방안

| 항목 | 방식 |
|------|------|
| 입력 | CLI: `python main.py [pdf\|폴더]` — 생략 시 `.env`의 `INPUT_DIR` |
| 설정 | `.env`: `INPUT_DIR`, `INSTRUMENTS_YAML_PATH`(기본 `config/instruments.yaml`), `RESULT_DIR`, `MAX_PDF_PAGES`(기본 1), `MIN_EXTRACTED_TEXT_CHARS`(기본 50), `ADMIN_DB_PATH`(기본 `admin/data/admin.db`), `ADMIN_BACKUP_DIR`(기본 `admin/backup`). 결과 파일명 접두어(`result`)는 코드 고정 |
| 공개 API | `extract_credit_report(path)` → dict; `commit_batch_outputs()` → 파일 저장 |
| 신평사 표준명 | JSON `agency` / Excel `신평사` → `NICE신용평가㈜`, `한국신용평가㈜`, `한국기업평가㈜` 중 하나 |

---

### 2. PDF 구조 추출

#### 문제 상황

- PyMuPDF로 추출한 표는 **병합 셀·빈 열·헤더 변형** 때문에 행·열 경계가 깨진다.
- 표 추출이 실패한 페이지는 **좌표 기반 visual 레이아웃** 또는 **평문**으로만 salvage 가능하다.
- 스캔 PDF·손상 파일·암호 PDF는 텍스트가 거의 없어 **「추출 실패」와 「파싱 실패」** 를 구분해야 한다.

#### 해결 방안

| 우선순위 | 소스 | 조건 |
|:--------:|------|------|
| 1 | `pdf_table` (Primary) | 「평가 개요」「평가 등급」 표에서 행 추출 |
| 2 | `visual_layout` | Primary 표 행이 **없을 때만** 같은 페이지 시각 분석 |
| 3 | `plain_text` | Primary·유효등급 모두 없을 때 평문 fallback |

- **행 재구성(`row_rebuild`):** 병합·분할된 셀을 평가대상·등급·전망 열에 맞게 다시 조립한다.
- **텍스트 추출 실패 판정:** 평가 행이 없고, 전체 추출 문자 수가 `MIN_EXTRACTED_TEXT_CHARS` 미만이며 등급 토큰도 없으면 `text_extraction_failed` (OCR 미사용 정책).

**관련 모듈:** `extract/tables.py`, `extract/visual.py`, `extract/fallback.py`, `extract/row_rebuild.py`

---

### 3. Primary·유효등급 구역

#### 문제 상황

- 신용평가서에는 **「평가 등급」(Primary)** 과 **「유효등급」** 이 별도로 존재한다.
- Primary만 쓰면 유효등급 구역의 **보조 상품·검증 정보**를 놓칠 수 있고, 유효등급만 쓰면 **본평가 대표 등급**과 혼동될 수 있다.
- 유효등급 텍스트에는 재무 수치·이메일 등 **등급과 무관한 노이즈**가 섞인다.

#### 해결 방안

| 구역 | 역할 | selected 사용 |
|------|------|:-------------:|
| **Primary** (`평가 개요` / `평가 등급`) | 본평가·정기평가 등 **대표 확정의 근거** | ✅ |
| **유효등급** (`valid_rating_section`) | 교차 검증·valid-only 상품 보완 | ❌ |

- Primary 표에서 행이 나오면 **같은 페이지 visual_layout은 스킵** (중복 방지).
- **Primary 유무와 관계없이 유효등급은 항상 추출** → 이후 canonical 병합 단계에서 통합.
- 유효등급 행은 `truncate_valid_row_text()`로 길이·노이즈를 줄인 뒤 파싱한다.

**관련 모듈:** `extract/layout.py`, `main._extract_rows_from_page`

---

### 4. 라벨·행 재구성

#### 문제 상황

- PDF 표의 「평가대상」 셀에 **라벨과 종목명(issue)이 한 칸에 붙어** 있는 경우가 많다.  
  예: `무보증사채(본) 2026-1회`
- 신평사마다 「본」「본평가」「(본)」 등 **평가 구분 표기**가 다르다.
- 부분 문자열·정규식만으로 라벨을 자르면 **과잉 분리·미분리** 오류가 발생한다.

#### 해결 방안

- **YAML 최장 prefix 매칭:** 평가대상 셀 앞부분을 `label_dictionary` alias와 비교해 **가장 긴 일치 prefix** → `raw_label`, **나머지 전체** → `issue_name`.
- 숫자·종목코드용 별도 정규식 분리(ISSUE_CODE_RE)는 **제거** — 라벨 경계는 사전에만 위임.
- `evaluation_type`: 「본」「본평가」 등 Primary 평가 구분을 별도 필드로 보존 → 최종 선택 알고리즘 입력.

**관련 모듈:** `extract/label_fields.py`, `extract/row_rebuild.py`

---

### 5. 등급·전망 추출

#### 문제 상황

- 한 행에 **현재등급·직전등급** 열이 함께 있으면 잘못된 열을 고르면 등급이 틀린다.
- 종목코드·채권번호(`영구A-05`, `1A-23`, `A-10(사)`)가 **등급 패턴과 유사**해 오탐한다.
- 등급전망이 `(S)`, `Stable`, `(안정적)` 등 **영문·한글·괄호 혼용**이다.

#### 해결 방안

| 기능 | 로직 |
|------|------|
| **행 전체 스캔** | 모든 셀에서 등급 후보 수집 |
| **후보 1개** | 해당 등급 채택 |
| **후보 2개 이상** | 헤더의 「현재등급」 열만 사용 (`multiple_rating_columns`는 여기서도 확정 불가 시) |
| **토큰 경계** | 한글·숫자 경계 검사로 종목코드형 문자열 제외 |
| **전망 표준화** | `Stable`→`안정적`, `(S)`→`안정적` 등 한글 표기로 통일 |

**관련 모듈:** `extract/row_parser.py`, `common/rating_tokens.py`

---

### 6. 상품 분류

#### 문제 상황

- 동일한 정규화 라벨이 **서로 다른 상품**으로 매핑되면 분류 결과 전체가 신뢰할 수 없다.
- YAML에 없는 신규 표기는 **자동 추측 확정**하면 잘못된 등급-상품 연결이 시스템에 고착된다.
- undefined 목록에 **이메일·재무지표·등급 없는 행**까지 쌓이면 검토 부담이 커진다.

#### 해결 방안

- **Exact match only:** `normalize_label(raw_label)` 후 `label_dictionary`와 **완전 일치** → `instrument_key` 부여 (`matched`).
- **기동 시 충돌 검사:** 동일 normalized 라벨이 다른 `instrument_key`에 매핑되면 **프로그램 시작 거부**.
- **Undefined 처리:** 미등록 시 `classification_status=undefined`, char n-gram cosine **유사 라벨 추천(`suggestions`)** — **자동 확정에는 미사용**.
- **필터:** `undefined_filter` — Primary에서 이미 matched된 라벨 중복, 재무 노이즈, rating none 등은 admin 누적·출력에서 제외.

**등록 상품 키 (12종):** `issuer`(발행자신용등급), `insurance_payment`(보험지급능력등급), `senior_unsecured`(무보증사채), `guaranteed_bond`(보증사채), `subordinated`(후순위사채), `coco_t1`(조건부자본증권(신종)), `coco_t2`(조건부자본증권(후순위)), `commercial_paper`(기업어음), `short_term_bond`(전자단기사채), `structured_abs`(자산유동화증권 ABS), `structured_abcp`(자산유동화기업어음 ABCP), `structured_abstb`(자산유동화전자단기사채 ABSTB)

> 구조화금융은 `structured_abs` · `structured_abcp` · `structured_abstb`로 세분화했다. 각 상품 키는 `instruments.yaml`에서 사람이 읽는 `display_name` 하나로만 관리한다(과거 `major_category_name`/`display_name` 이원화 제거).

**관련 모듈:** `classify/classifier.py`, `classify/recommend.py`, `classify/undefined_filter.py`, `config/instruments.yaml`

---

### 7. 병합·검증

#### 문제 상황

- Primary와 유효등급에서 **같은 상품**에 대해 등급·전망이 **일치하거나 불일치**할 수 있다.
- valid-only 상품(Primary에 없고 유효등급에만 존재)도 **결과 JSON의 `ratings`/`records`에 포함**해야 한다.
- 어느 출처를 신뢰했는지 **감사 추적**이 필요하다.

#### 해결 방안

- **`merge_canonical_records()`:** `instrument_key`별로 Primary·valid 레코드를 하나의 canonical 레코드로 병합.
- **Primary 우선:** 등급·전망 결정 시 Primary 값을 기본 채택.
- **일치 시:** `confirmed_by: ["primary", "valid"]` — 양쪽 출처가 교차 확인.
- **불일치 시:** Primary 값 유지 + `validation_warnings`에 `conflicting_rating_sources` 기록.
- valid-only 키는 canonical `records`·`ratings` sparse에 **그대로 유지** (selected 후보에는 넣지 않음).

**관련 모듈:** `extract/merge.py`, `common/models.py` (`RatingRecord.confirmed_by`)

---

### 8. 대표 등급 확정

#### 문제 상황

- PDF 한 건에서 **여러 상품**이 등급을 가지면 Excel·수식 소비를 위해 **상품당 1행**이 필요하다.
- 같은 상품에 본·정기가 함께 있으면 대표 평가종류를 정해야 한다.
- 일부 상품만 등급 확정에 실패해도 다른 상품은 살려야 한다.

#### 해결 방안

**상품 집계 (`build_products`):**

1. matched `instrument_key`별로 그룹화
2. 평가종류 우선순위 `본/본평가 > 수시 > 신규 > 정기 > Primary(무종류) > 유효등급`
3. 동일 우선순위에서 등급·전망이 하나면 상품 `success`
4. ambiguous / 등급 충돌이면 해당 상품만 fail
5. PDF 상태: 전부 성공=`success`, 일부=`partial`, 없음=`fail`

| fail_reason code | 의미 (요약) |
|------------------|-------------|
| `file_error` | PDF 열기 실패 |
| `text_extraction_failed` | 텍스트·등급 토큰 부족 |
| `parse_error` | 구조 파싱 실패 |
| `multiple_rating_columns` | 현재등급 열로도 등급 단일화 실패 (상품급) |
| `multiple_ratings` | 동일 상품·동일 우선순위에서 상충 등급 (상품급) |
| `rating_not_found` | 라벨은 matched, 등급 없음 (상품급) |
| `label_not_found` | 등급은 있으나 라벨 미식별 |
| `undefined_label` | 등급 있는 미등록 라벨 |

**관련 모듈:** `main.py` (`build_products`), `common/fail_reasons.py`

---

### 9. 결과 저장

#### 문제 상황

- 배치 중간에 프로세스가 끊기면 **JSON·Excel·undefined가 불일치**할 수 있다.
- 같은 PDF·같은 라벨이 반복 실행될 때 undefined가 **중복 누적**되면 검토 목록이 비대해진다.
- 운영 사용자는 **엑셀 한 장**으로 결과를 보고, 개발·감사는 **JSON 상세**가 필요하다.

#### 해결 방안

| 산출물 | 내용 | 저장 특성 |
|--------|------|-----------|
| `result/result_YYYYMMDD.json` | PDF당 객체 — `result_no`, `products`, `records`, `validation_warnings`, `undefined_records` | **당일 stem 덮어쓰기** |
| `result/result_YYYYMMDD.xlsx` | 시트 `신용등급_결과`, 상품당 1행 (`products` 기준) | **당일 stem 덮어쓰기** |
| `admin/data/admin.db` | 미등록 라벨 occurrence + 검수 상태·이력 | **`occurrence_id` 기준 upsert 누적 (SQLite)** |

- **원자적 저장:** 임시 파일 작성 → `os.replace`로 한 번에 교체 (`commit_batch_outputs`).
- **`result_no`:** 배치 내 정수 순번(`1`, `2`, `3`...). 파일 추가·삭제 시 순번이 바뀌므로 식별자가 아닌 **표시용 순번**임을 명확히 하고자 과거 `result_id`(`A0001`) 포맷을 제거했다. 안정 식별은 `file_hash`·`file_name`으로 한다.
- **occurrence_id:** `file_hash|normalized_label|page|row_index` — 동일 위치 재실행 시 중복 방지.
- **Excel 열:** No, 회사명, 신평사, 처리상태, 상품분류_Key, 상품분류, 원본라벨, 평가종류, 신용등급, 등급전망, 원본파일명, 실패사유 (`No`는 `result_no` 정수)

**관련 모듈:** `export/json_io.py`, `export/excel.py`, `export/undefined_store.py`(SQLite 어댑터), `admin/services/candidate_store.py`

---

### 10. 유지보수 체계

#### 문제 상황

- 신평사·발행인이 **새로운 평가대상 문구**를 쓰기 시작하면 추출은 되지만 분류가 `undefined`로 남는다.
- YAML 파일 직접 편집은 **비개발자에게 진입 장벽**이 있다.
- 라벨 추가 후 **검증·배포·이력**을 한곳에서 관리할 UI가 없다.

#### 해결 방안

**운영 루프 (구현 완료)**

1. 배치 실행 → 미등록 라벨이 `admin/data/admin.db`에 `pending`으로 누적
2. 관리자 웹 앱 실행 → 라벨 검수 화면에서 `suggestions`(유사 등록 라벨) 참고
3. 클릭으로 기존 상품에 alias 추가(승인) 또는 노이즈 라벨 제외(ignore)
4. YAML 자동 백업 후 원자적 갱신 → 배치 재실행 시 즉시 반영 (**코드 변경·재배포 불필요**)

**비개발자용 Admin 웹 앱 (Streamlit, 구현 완료)**

| 기능 | 설명 |
|------|------|
| 라벨 검수 | `pending` 미등록 라벨을 목록·발생 횟수·추천과 함께 조회 |
| 라벨 승인·매핑 | 화면에서 상품(instrument) 선택 → `instruments.yaml`의 `label_dictionary`에 alias 추가 |
| 라벨 제외 | 노이즈 라벨을 `ignored` 처리 (검수 목록에서 제거) |
| YAML 자동 반영 | `ruamel.yaml`로 주석·형식 보존 편집, `admin/backup/`에 타임스탬프 백업 후 `os.replace` 원자적 교체 |
| 등록 라벨 관리 | 이미 등록된 alias 조회·삭제 |
| 변경 이력·복원 | `review_history` 이력 조회, 백업 파일로 YAML 복원 |

| 구성 요소 | 파일 |
|-----------|------|
| 웹 진입점 | `admin/admin_main.py` |
| SQLite 저장소 | `admin/services/candidate_store.py` (`admin.db`) |
| YAML 안전 편집 | `admin/services/yaml_service.py` (백업·충돌 검사·원자적 교체) |
| 설치·실행 | `admin/setup_admin.bat`, `admin/run_admin.bat` |
| 데이터 이관 | `admin/services/migrate_undefined_json.py` (구 `admin/undefined.json` → SQLite 1회) |

**YAML ↔ SQLite 관계**

- **YAML = 라벨 매핑 원천(source of truth):** exact match 분류의 상품·라벨은 `instruments.yaml`만 사용한다.
- **매칭 정책 = 코드 원천:** 정규화·추천·카탈로그 검증은 `common/matching_policy.py`에서만 관리한다.
- **SQLite = 검수 큐·이력:** 미등록 라벨 후보와 검수 상태(`pending`/`approved`/`ignored`)·변경 이력을 보관한다.
- **서버 시작 시 1회 멱등 양방향 동기화:** 개발자가 YAML을 직접 편집해도 관리자 서버 기동 시 `admin.db`와 재조정된다.
  - `pending` 라벨이 현재 YAML에 존재하면 → `approved`
  - `approved` 승인 alias가 YAML에서 제거되면 → `pending` 복구
  - `ignored`는 변경하지 않음

**동적 대응 원칙**

- 분류 규칙을 **점수·ML이 아닌 사전 exact match**로 고정 → 동작 예측 가능
- 신규 표기 = **데이터(YAML) 변경** → 범용 파이프라인은 그대로 유지
- ambiguous 등급·conflict는 **자동 확정하지 않고** warning·fail로 표면화

---

### 11. 한계·향후

#### 현재 한계

| 항목 | 설명 |
|------|------|
| OCR | 미사용 — 스캔 PDF는 `text_extraction_failed` 가능 |
| 본 없는 복수 Primary 상품 | 상품별 `products`로 모두 반환 (`success`) |
| 페이지 상한 | 기본 1페이지 — 장문 부록 표는 스캔 밖일 수 있음 |
| Admin 동기화 | 서버 기동 시 1회 동기화 — 실행 중 YAML 직접 편집은 재기동 후 반영 |

#### 향후 과제

- undefined → 사전 반영 후 **선택적 PDF 재처리** 자동화
- (필요 시) OCR·페이지 범위 설정 확장 — 운영 정책에 따른 opt-in

---

### 부록: 처리 파이프라인 상세 다이어그램

```
                    ┌─────────────────────────────────────┐
                    │         입력 PDF / 폴더              │
                    └─────────────────┬───────────────────┘
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  agency: 신평사·회사명 식별           │
                    └─────────────────┬───────────────────┘
                                      ▼
          ┌───────────────────────────────────────────────────────┐
          │              페이지별 ExtractedRatingRow[]             │
          │  Primary(pdf_table → visual?) + Valid(항상) + fallback  │
          └───────────────────────────┬───────────────────────────┘
                                      ▼
          ┌───────────────────────────────────────────────────────┐
          │  label_fields: YAML prefix → raw_label / issue_name   │
          │  row_parser + rating_tokens: 등급·전망                 │
          │  row_rebuild: 병합 행 정규화                           │
          └───────────────────────────┬───────────────────────────┘
                                      ▼
          ┌───────────────────────────────────────────────────────┐
          │  LabelClassifier: YAML exact match → RatingRecord[]    │
          └───────────────────────────┬───────────────────────────┘
                                      ▼
          ┌───────────────────────────────────────────────────────┐
          │  merge_canonical_records (confirmed_by, warnings)      │
          └───────────────────────────┬───────────────────────────┘
                                      ▼
          ┌───────────────────────────────────────────────────────┐
          │  build_products → products, status, fail_reason        │
          └───────────────────────────┬───────────────────────────┘
                                      ▼
          ┌───────────────────────────────────────────────────────┐
          │  commit_batch_outputs (원자적 저장)                     │
          │  · result/*.json / *.xlsx                              │
          │  · admin/data/admin.db (SQLite 누적)             │
          └───────────────────────────┬───────────────────────────┘
                                      ▼
          ┌───────────────────────────────────────────────────────┐
          │  Admin 웹 앱 (admin/admin_main.py, 별도 실행)            │
          │  · 검수 → alias 승인/제외 → instruments.yaml 자동 갱신 │
          │  · 서버 기동 시 admin.db ↔ YAML 1회 양방향 동기화       │
          └───────────────────────────────────────────────────────┘
```

---

### 부록: 실행·테스트

```bash
cd CreditRateFinder\CreditRateFinder
.venv\Scripts\python.exe main.py          # .env INPUT_DIR 배치
.venv\Scripts\python.exe main.py -o batch # 결과 stem 지정
.venv\Scripts\python.exe -m pytest tests -q
```

단위 테스트(114건)는 라벨 분리, 등급 오탐 방지, Primary+valid 동시 추출, canonical 병합, selected·fail_reason, undefined dedup(SQLite), 원자적 저장, 매칭 정책(정규화·추천·검증), 그리고 관리자 앱의 SQLite 검수 저장소·YAML 안전 편집·양방향 동기화 등을 검증한다.

관리자 앱 실행:

```bash
cd CreditRateFinder\CreditRateFinder
admin\setup_admin.bat   # 최초 1회 설치
admin\run_admin.bat     # 브라우저에서 localhost:8501 검수
```

---

*본 문서는 CreditRateFinder 코드베이스(2026-07-21 기준) 및 README를 바탕으로 작성되었습니다.*
