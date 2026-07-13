# PDFScanner

NICE신용평가 · 한국신용평가 · 한국기업평가 신용평가서 PDF에서
평가대상별 신용등급(발행자, 조건부자본증권, 무보증사채 등)을 추출합니다.

## 설치

```bash
cd PDFScanner
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 사용법

모든 작업 오케스트레이션은 **`main.py`** 에서 수행합니다.

```bash
cd PDFScanner

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

## 디렉터리 구조

```
PDFScanner/
├── README.md
├── requirements.txt
├── .gitignore
├── main.py                              # ★ 진입점 / 전체 오케스트레이션
├── .cursor/rules/                       # Cursor 프로젝트 규칙
│   ├── architecture.mdc
│   ├── taxonomy.mdc
│   ├── extraction.mdc
│   ├── testing.mdc
│   └── documentation.mdc
├── credit_scanner/                      # 추출·분류·저장 라이브러리
│   ├── __init__.py                      # extract_credit_report 공개
│   ├── __main__.py                      # python -m credit_scanner → main
│   ├── cli.py                           # main 위임
│   ├── pipeline.py                      # 단일 PDF 추출 API
│   ├── constants.py                     # 등급·평가종류·타겟 상수
│   ├── models.py                        # RatingRecord, VisualLine
│   ├── text_utils.py                    # 텍스트 정규화
│   ├── rating_tokens.py                 # 등급·전망 토큰 파싱
│   ├── classifier.py                    # taxonomy scoring 분류기
│   ├── agency.py                        # 기관 식별 + 레이아웃 어댑터
│   ├── config/
│   │   └── instrument_taxonomy.yaml     # 평가대상 별칭·특징 사전
│   ├── extract/
│   │   ├── visual.py                    # 시각적 행 클러스터링
│   │   ├── tables.py                    # PDF 표 추출
│   │   ├── layout.py                    # 평가개요·유효등급 영역
│   │   ├── fallback.py                  # 평문 fallback
│   │   └── row_parser.py                # 행 → RatingRecord
│   └── export/
│       ├── excel.py                     # summary/detail 행·워크북 쓰기
│       ├── json_io.py                   # JSON 저장
│       └── review.py                    # needs_review / 별칭 제안
├── pdf_scanner/
│   └── pdf_scanner.py                   # 하위 호환 래퍼 → main
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   └── label_variants.json          # 기관×워딩 회귀 fixture
    └── test_instrument_extraction.py
```

## 처리 흐름 (`main.py`)

1. CLI 인자 파싱
2. **단일 PDF**: `extract_credit_report` → JSON 저장 → 콘솔 출력  
   **폴더**: PDF 순회 → 동일 추출 → Excel(`summary` / `all_candidates` / `needs_review`) 저장
3. 라이브러리 내부: 표/시각 추출 → taxonomy 분류 → 미분류는 `unknown`으로 보존 후 리뷰 시트 출력

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

## Python API

일괄 오케스트레이션은 `main.py`를 쓰고, 라이브러리로는 단일 PDF 추출만 직접 호출합니다.

```python
from credit_scanner import extract_credit_report

result = extract_credit_report("report.pdf", target_instrument="issuer")
print(result["selected"])
print(result["review_records"])  # unknown / ambiguous
```

## 의존성

| 패키지 | 용도 |
|--------|------|
| pymupdf | PDF 텍스트/표 추출 |
| pandas, openpyxl | Excel 출력 |
| PyYAML | taxonomy 로드 |
| pytest | 회귀 테스트 |
