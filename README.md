# CreditRateFinder

NICE신용평가 · 한국신용평가 · 한국기업평가 신용평가서 PDF에서  
평가대상별 신용등급(발행자, 조건부자본증권, 무보증사채 등)을 추출합니다.

표·시각 레이아웃으로 **구조 추출**한 뒤, `instrument_taxonomy.yaml` 기반 **점수 분류**로 상품 유형을 붙입니다.  
분류에 실패한 행도 등급이 있으면 `unknown`/`ambiguous`로 보존하고 Excel `needs_review`에 모읍니다.

## 설치

```bash
cd CreditRateFinder
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 사용법

모든 작업 오케스트레이션은 **`main.py`** 에서 수행합니다.

```bash
cd CreditRateFinder

# 단일 PDF → JSON
venv\Scripts\python.exe main.py report.pdf -o out.json --target issuer

# 폴더 일괄 → Excel (summary / all_candidates / needs_review)
venv\Scripts\python.exe main.py ./pdfs -o result.xlsx --target coco_t1
```

하위 호환 (동일하게 `main.py` 호출):

```bash
venv\Scripts\python.exe -m credit_scanner report.pdf --target coco_t1
venv\Scripts\python.exe pdf_scanner\pdf_scanner.py report.pdf
```

| 옵션 | 설명 |
|------|------|
| `--target` | 목표 상품 (`issuer`, `coco_t1`, `coco_t2`, `senior_unsecured` 등) |
| `--taxonomy` | 커스텀 `instrument_taxonomy.yaml` 경로 |
| `--non-recursive` | 폴더 처리 시 하위 디렉터리 제외 |
| `-o`, `--output` | 출력 JSON/Excel 경로 |

기본 출력:
- 단일 파일: `<입력명>.credit_rating.json`
- 폴더: `<폴더>/credit_rating_result.xlsx`

---

## 전체 처리 흐름

```
입력 PDF/폴더
    │
    ▼
main.py  (CLI 파싱 · 단일/폴더 분기 · 저장)
    │
    ├─ 단일 PDF ──► extract_credit_report() ──► JSON
    │
    └─ 폴더 ──────► PDF 순회 → extract_credit_report()
                        → summary / detail / review 행 조립
                        → Excel (summary | all_candidates | needs_review)
```

### `extract_credit_report` 내부 (단일 PDF)

```
1. PDF 열기 (앞 max_pages=3페이지, 텍스트 길이 검사)
   └─ 텍스트 < 50자 → status: ocr_required 로 종료

2. 1페이지 텍스트로 기관 식별 (agency.detect_agency)
   └─ NICE신용평가 / 한국신용평가 / 한국기업평가 / 미확인

3. 구조 추출 (우선순위 순, 결과를 모두 누적)
   ├─ tables   … PDF 표에서 등급표 헤더·행 추출
   ├─ visual   … "평가개요" 등 섹션 클립 후 시각 행 클러스터링
   ├─ valid    … "유효등급" 영역 행 추출
   └─ fallback … 위가 비었을 때만 평문 줄 단위 스캔

4. 행 파싱 (row_parser)
   └─ 레이블 · 평가종류 · 현재/직전등급 · outlook · Rating Action · 비고
   └─ classifier로 instrument_type 부여 (matched / unknown / ambiguous)

5. 후처리
   ├─ 중복 제거 (deduplicate_records)
   ├─ 목표 상품 선택 (select_target_rating)
   ├─ 상품유형별 best (select_best_by_instrument)
   └─ 리뷰 후보 수집 (unknown / ambiguous)

6. 결과 dict 반환
   status: success | needs_review | not_found | ocr_required
```

설계 원칙:
- **구조 추출**과 **의미 분류**를 분리합니다.
- 평가대상 동의어는 Python 정규식 하드코딩이 아니라 **taxonomy YAML**에 둡니다.
- 분류 실패 시에도 등급이 있는 행은 버리지 않습니다.

---

## 디렉터리 구조

```
CreditRateFinder/
├── README.md
├── requirements.txt
├── .gitignore
├── main.py                              # 진입점 / 전체 오케스트레이션
├── .cursor/rules/                       # Cursor 프로젝트 규칙
│   ├── architecture.mdc
│   ├── taxonomy.mdc
│   ├── extraction.mdc
│   ├── testing.mdc
│   └── documentation.mdc
├── credit_scanner/                      # 추출·분류·저장 라이브러리
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── pipeline.py
│   ├── constants.py
│   ├── models.py
│   ├── text_utils.py
│   ├── rating_tokens.py
│   ├── classifier.py
│   ├── agency.py
│   ├── config/
│   │   └── instrument_taxonomy.yaml
│   ├── extract/
│   │   ├── __init__.py
│   │   ├── visual.py
│   │   ├── tables.py
│   │   ├── layout.py
│   │   ├── fallback.py
│   │   └── row_parser.py
│   └── export/
│       ├── __init__.py
│       ├── excel.py
│       ├── json_io.py
│       └── review.py
├── pdf_scanner/
│   └── pdf_scanner.py                   # 하위 호환 래퍼 → main
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   └── label_variants.json
    └── test_instrument_extraction.py
```

---

## 파일별 기능

### 루트

| 파일 | 역할 |
|------|------|
| `main.py` | **유일한 오케스트레이션 진입점.** CLI 인자 파싱 → 단일 PDF는 JSON 저장·콘솔 출력, 폴더는 PDF 순회 후 Excel 저장. 폴더 순회·에러 행 처리는 여기에만 둡니다. |
| `requirements.txt` | 런타임·테스트 의존성 목록 |
| `.gitignore` | `venv/`, 캐시, `*.xlsx`, `*.credit_rating.json` 등 무시 |

### `.cursor/rules/` — 개발 가이드

| 파일 | 역할 |
|------|------|
| `architecture.mdc` | main 오케스트레이션 vs `credit_scanner` 라이브러리 분리, export에 폴더 루프 금지 |
| `taxonomy.mdc` | 동의어는 YAML만 확장, scoring 분류 유지, agency는 레이아웃만 |
| `extraction.mdc` | 구조 추출 → 분류 2단계, tables→visual→valid→fallback 경로 |
| `testing.mdc` | 회귀·fixture 관련 테스트 규칙 |
| `documentation.mdc` | 구조·진입점·API 변경 시 README 동기화 |

### `credit_scanner/` — 핵심 라이브러리

| 파일 | 역할 |
|------|------|
| `__init__.py` | 공개 API: `extract_credit_report` export, 패키지 버전 |
| `__main__.py` | `python -m credit_scanner` → `cli.main` → 루트 `main` |
| `cli.py` | 하위 호환. 오케스트레이션을 루트 `main.py`에 위임 |
| `pipeline.py` | **단일 PDF 추출 파이프라인.** 기관 식별, extract 경로 호출, 중복 제거, 목표 선택, 결과 dict 조립 |
| `constants.py` | 평가종류 우선순위, Rating Action, outlook 맵, 등급 regex, `--target` 선택지, 헤더 노이즈 토큰 |
| `models.py` | `RatingRecord`(추출 행), `VisualLine`(시각 좌표 행) 데이터클래스 |
| `text_utils.py` | NFKC 정규화, 공백 제거(`compact_text`), 평가종류·outlook 정규화 |
| `rating_tokens.py` | `AAA`, `AA+/Stable` 등 등급·전망 토큰 파싱·탐색 |
| `classifier.py` | taxonomy YAML 로드, feature/alias scoring, `matched`/`unknown`/`ambiguous` 판정. `get_classifier` 캐시 |
| `agency.py` | PDF 텍스트로 기관 식별 + 기관별 표 헤더·섹션 경계(`AgencyLayoutConfig`). 상품 분류에는 사용하지 않음 |

### `credit_scanner/config/`

| 파일 | 역할 |
|------|------|
| `instrument_taxonomy.yaml` | **평가대상 사전.** `features`(정규식 특징) + `instruments`(aliases, require/boost/exclude, base_score). 코드 수정 없이 워딩 추가 |

지원 canonical 타입 예: `coco_t1`, `coco_t2`, `issuer`, `senior_unsecured`, `subordinated`, `commercial_paper`, `short_term_bond`, `insurance_payment`, `structured_finance`

### `credit_scanner/extract/` — 구조 추출

| 파일 | 역할 |
|------|------|
| `__init__.py` | 추출 공개 함수 re-export |
| `tables.py` | PyMuPDF `find_tables()`로 등급표 헤더 탐지 → 행 그룹핑 → `RatingRecord` |
| `visual.py` | word 좌표를 y축 클러스터링해 `VisualLine` 생성, 섹션 제목 라인 탐색 |
| `layout.py` | 기관 레이아웃으로 **평가개요(primary)** · **유효등급** 영역을 clip하여 시각 행 추출 |
| `fallback.py` | 표/시각 결과가 비었을 때 페이지 평문 줄에서 후보 행 스캔 |
| `row_parser.py` | 셀/줄 값 → `RatingRecord`. 분류 결과·등급 토큰·평가종류·비고 조립. 미분류여도 등급 있으면 보존 |

### `credit_scanner/export/` — 저장·리뷰 (오케스트레이션 없음)

| 파일 | 역할 |
|------|------|
| `__init__.py` | 행 조립·저장 헬퍼 re-export |
| `excel.py` | `build_summary_row` / `build_detail_rows`, 워크북 쓰기(`summary`, `all_candidates`, `needs_review`) |
| `json_io.py` | 단일 결과를 UTF-8 JSON으로 저장 |
| `review.py` | `review_records` → Excel 리뷰 행, YAML alias 스니펫 제안(`suggest_taxonomy_aliases`) |

### `pdf_scanner/`

| 파일 | 역할 |
|------|------|
| `pdf_scanner.py` | 구 진입점 하위 호환. `main.main()` 호출 |

### `tests/`

| 파일 | 역할 |
|------|------|
| `conftest.py` | pytest 공통 fixture |
| `fixtures/label_variants.json` | 기관×워딩 회귀 케이스 (`label` → `expected` instrument) |
| `test_instrument_extraction.py` | taxonomy 분류, unknown 보존, 리뷰 행·alias 제안, 헤더 판정 등 단위/회귀 테스트 |

---

## Excel 출력 시트

| 시트 | 내용 |
|------|------|
| `summary` | PDF당 1행. 선택된 목표 등급 + 주요 상품유형별 등급 요약 |
| `all_candidates` | 추출된 모든 `RatingRecord` (분류상태·점수·원문 포함) |
| `needs_review` | `unknown`/`ambiguous` 레이블. taxonomy 보강용 (`제안_canonical_type`, `제안_alias`) |

---

## 새 워딩 추가 (유지보수)

코드 수정 없이 YAML만 편집합니다.

1. 일괄 실행 후 Excel `needs_review` 시트 확인
2. `제안_canonical_type`에 예: `issuer`, `senior_unsecured`, `coco_t1`
3. [`credit_scanner/config/instrument_taxonomy.yaml`](credit_scanner/config/instrument_taxonomy.yaml)의 해당 `aliases`에 문구 추가
4. 필요 시 [`tests/fixtures/label_variants.json`](tests/fixtures/label_variants.json)에 케이스 추가
5. 재실행 · 테스트 확인

```bash
venv\Scripts\python.exe -m pytest tests/ -v
```

수정 위치 가이드:
- 표 헤더·섹션 경계 → `agency.py`
- 상품 워딩·특징 → `instrument_taxonomy.yaml`
- 등급/전망 토큰 → `rating_tokens.py` / `constants.py`

---

## Python API

일괄 오케스트레이션은 `main.py`를 쓰고, 라이브러리로는 단일 PDF 추출만 직접 호출합니다.

```python
from credit_scanner import extract_credit_report

result = extract_credit_report("report.pdf", target_instrument="issuer")
print(result["selected"])         # 목표 상품으로 선택된 RatingRecord (dict) 또는 None
print(result["ratings"])          # instrument_type → best record
print(result["records"])          # 전체 추출 행
print(result["review_records"])   # unknown / ambiguous
print(result["status"])           # success | needs_review | not_found | ocr_required
```

---

## 의존성

| 패키지 | 용도 |
|--------|------|
| pymupdf | PDF 텍스트·표·word 좌표 추출 |
| pandas, openpyxl | Excel 출력 |
| PyYAML | taxonomy 로드 |
| pytest | 회귀 테스트 |
