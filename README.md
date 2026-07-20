# CreditRateFinder

NICE신용평가 · 한국신용평가 · 한국기업평가 신용평가서 PDF에서  
평가대상 라벨·신용등급·등급전망을 추출합니다.

표·시각 레이아웃으로 **구조 추출**(`ExtractedRatingRow`)한 뒤,  
`config/instruments.yaml`의 `label_dictionary`와 **정확 일치**로 분류(`RatingRecord`)합니다.  
PDF에서 검출된 라벨을 자동 탐색해 최종 결과 1개(`selected`)를 확정합니다.

---

## 설치

```bash
cd C:\mycode\CreditRateFinder\CreditRateFinder
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
cd C:\mycode\CreditRateFinder\CreditRateFinder

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

상품은 YAML exact match + 선택 알고리즘으로 자동 확정됩니다.  
설정은 `CreditRateFinder/.env` (템플릿: `.env.example`)에서 로드합니다.

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
    ├─ 회사명·신평사 (agency)
    ├─ 라벨 exact match → RatingRecord (matched/undefined)
    ├─ source 병합 (pdf_table > visual_layout > valid_rating > fallback)
    ├─ selected 자동 확정 (「본」/「본평가」 우선) + success/fail·fail_reason
    ├─ undefined 발생 건 수집
    └─ 배치 종료 후 원자적 저장
         result/result_YYYYMMDD.json
         result/result_YYYYMMDD.xlsx  (시트: 신용등급_결과, PDF당 1행)
         admin/undefined.json         (occurrence_id 중복 방지 누적)
```

### 표·행 선택 우선순위

1. **Primary:** `평가 개요`/`평가 등급` 표 (`pdf_table`). 행이 있으면 같은 페이지의 `visual_layout`은 쓰지 않음.
2. **Fallback primary:** `visual_layout` (표 추출 실패 시).
3. **Valid:** 좌측 `유효 등급`은 primary에 없는 상품만 보완.
4. **Selected:** primary에 `종류=본`/`본평가`이고 등급이 확정(`single`)된 행이 정확히 1상품이면 그것을 `selected`. `정기` 등은 `records`/`ratings`에 보존.
5. `본`이 없으면 기존처럼 rating 있는 matched 상품 수로 판정.

### 파일 상태

| status | 조건 |
|--------|------|
| `success` | 선택 알고리즘으로 `selected`가 자동 확정됨 |
| `fail` | 그 외 (`fail_reason.code` 참고) |

다른 상품의 `undefined`·`정기` 행이 있어도 `본`이 확정되면 파일은 `success`입니다.

### fail_reason (우선순위 순)

`file_error` → `text_extraction_failed` → `parse_error` → `multiple_instruments` →  
`multiple_rating_columns` → `multiple_ratings` → `rating_not_found` →  
`label_not_found` → `undefined_label`

| code | 의미 |
|------|------|
| `file_error` | PDF 열기 실패(손상·암호 등) |
| `text_extraction_failed` | 평가 행이 없고, 추출 문자 수·등급 토큰도 부족 |
| `parse_error` | 텍스트는 있으나 평가대상 행/표 구조를 구성하지 못함 |
| `multiple_instruments` | `본`이 복수이거나(본 없을 때) rating 있는 상품이 복수 |
| `multiple_rating_columns` | 현재등급 열 적용 후에도 등급을 하나로 확정 못함 |
| `multiple_ratings` | 동일 상품에 서로 다른 등급/전망이 복수 |
| `rating_not_found` | YAML 매칭은 됐지만 등급 없음 |
| `label_not_found` | 등급은 있으나 라벨을 못 찾음 |
| `undefined_label` | 등급 있는 라벨이 YAML에 미등록 |

### 결과 스키마 (JSON, PDF당 1객체)

| 필드 | 설명 |
|------|------|
| `result_id` | `R000001` 형식 |
| `company_name` / `agency` | 회사명·신평사 |
| `status` / `fail_reason` | `success` 또는 `fail` + `{code, message}` |
| `selected` | 확정 레코드(실패 시 `null`, `evaluation_type` 포함) |
| `ratings` | 검출된 matched 상품만 sparse. 값 미확정이면 `null` |
| `records` | 전체 `RatingRecord` |
| `undefined_records` | YAML 미등록 라벨 + `suggestions` |
| `file_hash` | SHA-256 (undefined 중복 방지용) |

Excel(`신용등급_결과`)은 `selected` 기준 PDF당 1행입니다.  
열: 결과_ID, 회사명, 신평사, 처리상태, 대분류_Key, 대분류명, 소분류_원본라벨, 신용등급, 등급전망, 원본파일명.

---

## 상품·라벨 (`config/instruments.yaml`)

등록 상품 키: `issuer`, `senior_unsecured`, `subordinated`, `coco_t1`, `coco_t2`,  
`commercial_paper`, `short_term_bond`, `insurance_payment`, `structured_finance`.

라벨 추가·수정은 `label_dictionary`에만 등록하면 됩니다.  
동일 정규화 라벨이 서로 다른 `instrument_key`로 매핑되면 기동 시 거부됩니다.

undefined 라벨에는 char n-gram cosine 추천(`suggestions`)이 붙지만 **자동 확정에는 사용하지 않습니다**.  
수동으로 YAML에 등록한 뒤 재실행하세요.

---

## 디렉터리

```
CreditRateFinder/
├── README.md
├── .gitignore
├── .cursorignore
├── .cursor/rules/          # architecture, taxonomy, extraction, testing, documentation
└── CreditRateFinder/       # 앱 루트 (실행 cwd)
    ├── main.py
    ├── requirements.txt
    ├── .env / .env.example
    ├── config/instruments.yaml
    ├── common/             # settings, models, fail_reasons, text_utils, rating_tokens
    ├── agency/             # 신평사·레이아웃·회사명
    ├── classify/           # exact match + undefined 추천
    ├── extract/            # tables, visual, layout, fallback, row_parser, merge
    ├── export/             # json_io, excel, undefined_store
    ├── admin/undefined.json
    ├── result/
    └── tests/
```

---

## 테스트

```bash
cd C:\mycode\CreditRateFinder\CreditRateFinder
.venv\Scripts\python.exe -m pytest tests -q
```

단위 테스트: 라벨 exact match, 현재등급 열 선택, `본` 우선 selected, source 병합,  
선택 알고리즘·fail_reason, Excel 매핑, undefined dedup, 원자적 저장.

---

## 설정 (.env)

| 키 | 용도 |
|----|------|
| `INPUT_DIR` | 처리할 PDF 폴더 (**필수**, 코드 기본값 없음. 상대경로는 앱 루트 기준) |
| `CONFIG_DIR` / `INSTRUMENTS_YAML` | 상품·라벨 딕셔너리 |
| `RESULT_DIR` / `RESULT_FILENAME_PREFIX` | 결과 파일 (`result_YYYYMMDD`) |
| `ADMIN_DIR` / `UNDEFINED_JSON` | undefined 누적 저장소 |
| `MAX_PDF_PAGES` | 스캔 페이지 상한 (기본 3) |
| `MIN_EXTRACTED_TEXT_CHARS` | 텍스트 추출 실패 판정용 문자 수 하한 (기본 50) |
| `RESULT_ID_PREFIX` / `RESULT_ID_WIDTH` | 결과 ID (`R000001`) |

---

## 알려진 미완성·한계

| 항목 | 상태 |
|------|------|
| **Admin UI** | `admin/undefined.json` 누적·스키마만 존재. 승인 UI·YAML 자동 반영 **미구현**. |
| **undefined → YAML 반영** | 추천·누적만 제공. 수동 YAML 편집. |
| **본 없는 복수 상품** | `본`/`본평가`가 없으면 rating 있는 matched 상품 ≥2일 때 `multiple_instruments`. |

라벨 미등록·오추출은 `admin/undefined.json`에 쌓이므로, 검토 후 `label_dictionary`에 반영하는 운영 루프를 전제로 합니다.
