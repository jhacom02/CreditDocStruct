---
name: CreditRateFinder implementation roadmap
overview: creditratefinder_restructure_43c68190.plan.md에 정의된 계약(자동 target 탐지, ExtractedRatingRow/RatingRecord 분리, fail_reason 9코드, sparse ratings, occurrence_id 중복방지, 원자적 저장)을 실제 코드로 구현한다. 현재 모든 모듈 파일은 TODO docstring뿐인 placeholder 상태이며, 이번 계획은 6개의 남은 todo(settings-config부터 tests-docs까지)를 순서대로 구현하는 로드맵이다.
todos: []
isProject: false
---


# CreditRateFinder 구현 로드맵

기준 문서: [C:\Users\infomax\.cursor\plans\creditratefinder_restructure_43c68190.plan.md](C:\Users\infomax\.cursor\plans\creditratefinder_restructure_43c68190.plan.md)

## 현재 상태 확인

`scaffold-layout`(폴더 골격)만 완료된 상태다. 나머지 6개 todo는 모두 `pending`이고, 아래 파일들은 전부 `"""TODO: ..."""` docstring만 있는 빈 placeholder다:

- [common/settings.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\settings.py), [common/models.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\models.py), [common/fail_reasons.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\fail_reasons.py), [common/text_utils.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\text_utils.py), [common/rating_tokens.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\rating_tokens.py)
- [agency/agency.py](c:\mycode\CreditRateFinder\CreditRateFinder\agency\agency.py)
- [classify/classifier.py](c:\mycode\CreditRateFinder\CreditRateFinder\classify\classifier.py), [classify/recommend.py](c:\mycode\CreditRateFinder\CreditRateFinder\classify\recommend.py)
- [extract/tables.py](c:\mycode\CreditRateFinder\CreditRateFinder\extract\tables.py), `visual.py`, `layout.py`, `fallback.py`, [extract/row_parser.py](c:\mycode\CreditRateFinder\CreditRateFinder\extract\row_parser.py)
- [export/json_io.py](c:\mycode\CreditRateFinder\CreditRateFinder\export\json_io.py), `excel.py`, [export/undefined_store.py](c:\mycode\CreditRateFinder\CreditRateFinder\export\undefined_store.py)
- [main.py](c:\mycode\CreditRateFinder\CreditRateFinder\main.py)는 `NotImplementedError`만 던지는 상태
- [tests/test_instrument_extraction.py](c:\mycode\CreditRateFinder\CreditRateFinder\tests\test_instrument_extraction.py)·[tests/label_variants.json](c:\mycode\CreditRateFinder\CreditRateFinder\tests\label_variants.json)는 삭제된 구 `credit_scanner` API(`InstrumentClassifier`, `unknown` status 등)를 참조하는 구버전 그대로 남아 있어 전면 재작성 필요
- [.env.example](c:\mycode\CreditRateFinder\CreditRateFinder\.env.example)/`.env`에는 삭제 대상인 `DEFAULT_TARGET_INSTRUMENT`가 아직 남아 있음
- [requirements.txt](c:\mycode\CreditRateFinder\CreditRateFinder\requirements.txt)에 `python-dotenv` 누락
- 구 `instrument_taxonomy.yaml`(alias 목록)은 git 커밋 `f4b2fe3`에서 복구 가능 → `config/instruments.yaml` 마이그레이션 시 참고

## 구현 순서 (plan.md 섹션 I 기준)

### 1. `settings-config` — 설정·YAML·fail_reason 기반

- [common/settings.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\settings.py): `python-dotenv`로 `.env` 로드, `CONFIG_DIR`/`INSTRUMENTS_YAML`/`RESULT_DIR`/`RESULT_FILENAME_PREFIX`/`ADMIN_DIR`/`UNDEFINED_JSON`/`MAX_PDF_PAGES`/`OCR_TEXT_MIN_CHARS`/`RESULT_ID_PREFIX`/`RESULT_ID_WIDTH` 필드를 가진 `Settings` dataclass. `DEFAULT_TARGET_INSTRUMENT` 필드 없음.
- `.env`/`.env.example`에서 `DEFAULT_TARGET_INSTRUMENT` 행 제거, `requirements.txt`에 `python-dotenv` 추가.
- `config/instruments.yaml`: git 이력의 구 `instrument_taxonomy.yaml` alias를 `label_dictionary`로 마이그레이션하고 `instruments`/`normalization`/`recommendation`/`validation` 섹션을 plan.md 섹션 C 스키마대로 채움.
- `common/settings.py` 또는 별도 `config` 로더에 **기동 시 검증** 추가: 동일 정규화 라벨이 다른 key에 매핑되면 거부, 등록되지 않은 `instrument_key` 참조 거부.
- [common/fail_reasons.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\fail_reasons.py): plan.md 섹션 D의 9개 코드(`file_error`~`undefined_label`)를 우선순위 순서 그대로 상수/헬퍼로 정의(코드 + 메시지, "여러 열"이 아닌 "여러 등급 값" 문구로 `multiple_rating_columns` 작성).
- [common/text_utils.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\text_utils.py): YAML `normalization` 규칙(NFKC, trim, 줄바꿈 제거, 괄호 정규화, 영문 대문자, 공백 제거) 적용 함수.
- [common/rating_tokens.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\rating_tokens.py): 등급/전망 토큰 파싱 + 셀 안 토큰 개수 카운팅(추후 row_parser의 `rating_status` 판정에 사용).

### 2. `rewrite-models-extract` — 모델 분리 + 추출

- [common/models.py](c:\mycode\CreditRateFinder\CreditRateFinder\common\models.py): `ExtractedRatingRow`(raw_label, rating_cells, rating_status, rating, outlook, page, row_index, section, source)와 `RatingRecord`(+instrument_key, classification_status, suggestions) 두 dataclass를 분리 정의(plan.md 섹션 E).
- [agency/agency.py](c:\mycode\CreditRateFinder\CreditRateFinder\agency\agency.py): 신평사 식별, 기관별 표 헤더/섹션 패턴, 회사명 추출(1페이지 헤더 우선, 실패 시 파일명 stem 보조).
- [extract/tables.py](c:\mycode\CreditRateFinder\CreditRateFinder\extract\tables.py) / `visual.py` / `layout.py` / `fallback.py`: PDF 표·좌표·평가개요 영역·평문 폴백 추출(PyMuPDF `find_tables` 등 활용).
- [extract/row_parser.py](c:\mycode\CreditRateFinder\CreditRateFinder\extract\row_parser.py): 셀/줄 → `ExtractedRatingRow` 조립. rating 셀 개수로 `rating_status`(`none`/`single`/`ambiguous`) 판정(셀 내부 토큰 2개 이상도 `ambiguous`로 통합).

### 3. `rewrite-classify` — 분류·추천

- [classify/classifier.py](c:\mycode\CreditRateFinder\CreditRateFinder\classify\classifier.py): `ExtractedRatingRow` → 라벨 정규화(`text_utils`) → `label_dictionary` exact match → `RatingRecord` 생성(matched/undefined). YAML 로드·충돌 검증 연동.
- [classify/recommend.py](c:\mycode\CreditRateFinder\CreditRateFinder\classify\recommend.py): `undefined` 레코드에 대해서만 char n-gram cosine 기반 추천 Key·점수·사유 생성(자동 확정에는 미사용).

### 4. `main-orchestration` — 오케스트레이션

[main.py](c:\mycode\CreditRateFinder\CreditRateFinder\main.py)의 `NotImplementedError`를 실제 흐름으로 교체:

- CLI: `python main.py <dir|pdf>` (`--target` 옵션 없음), `-o` stem 오버라이드만 지원.
- PDF 순회 → 추출(`extract`) → 분류(`classify`) → **선택 알고리즘**(plan.md 섹션 B): matched+rating 있는 그룹을 `instrument_key`별로 모아 0/1/2+ 개수로 분기해 `selected` 자동 확정.
- fail_reason 우선순위 판정(plan.md 섹션 D 표 그대로, `file_error`→...→`undefined_label`).
- 결과 객체 조립: `result_id`(`R`+zero-pad), `selected`, `ratings`(검출된 key만, 미확정만 `null`), `records`, `undefined_records`.
- 배치 종료 후 `commit_batch_outputs`: JSON/Excel/`admin/undefined.json` 병합 결과를 `.tmp`로 만들고 전부 성공 확인 후 `os.replace()`로 원자적 교체(plan.md 섹션 G-1).

### 5. `export-json-excel` — 저장 계층

- [export/json_io.py](c:\mycode\CreditRateFinder\CreditRateFinder\export\json_io.py): `result_YYYYMMDD.json`(배열) tmp 파일 생성 헬퍼.
- [export/excel.py](c:\mycode\CreditRateFinder\CreditRateFinder\export\excel.py): `신용등급_결과` 시트, PDF당 1행, 대분류_Key/명을 `selected` 기준으로 채움, fail 시 공란.
- [export/undefined_store.py](c:\mycode\CreditRateFinder\CreditRateFinder\export\undefined_store.py): `admin/undefined.json` 로드 → `occurrence_id`(`sha256(PDF)+normalized_label+page+row_index`) 기반 dedup 병합 → tmp 파일 생성. 기존 `occurrence_id`면 `occurrence_count`/`first_seen_at`/`sample_files`/`sample_ratings` 갱신 금지.

### 6. `tests-docs` — 테스트·문서

- [tests/label_variants.json](c:\mycode\CreditRateFinder\CreditRateFinder\tests\label_variants.json): `expected: "unknown"` → `expected: "undefined"`(또는 매칭 instrument_key)로 스키마 갱신.
- [tests/test_instrument_extraction.py](c:\mycode\CreditRateFinder\CreditRateFinder\tests\test_instrument_extraction.py): 삭제된 `credit_scanner.*` import를 전부 새 모듈(`classify.classifier`, `extract.row_parser`, `agency.agency` 등)로 교체하고 전면 재작성. 선택 알고리즘(단일 후보 success / 후보 0개 / `multiple_instruments` / `multiple_rating_columns` / `multiple_ratings`), Excel 대분류 매핑, `admin/undefined.json` occurrence_id dedup, 저장 원자성(tmp→replace 실패 시 원본 보존) 케이스 추가.
- `README.md`, `.cursor/rules/*.mdc`(architecture/taxonomy/extraction/testing/documentation) 새 계약(자동 target 탐지, ExtractedRatingRow/RatingRecord 분리, fail_reason 9코드)에 맞게 전면 갱신.
- `pytest` 실행해 통과 확인.

## 진행 방식

각 단계는 순서대로 진행하되 서로 의존성이 있다(settings/models가 먼저 필요 → extract/classify → main → export → tests). Agent 모드로 전환해 `settings-config`부터 순서대로 todo를 `in_progress`/`completed`로 갱신하며 구현할 것을 권장한다.
</plan>
<todos>[{"id": "settings-config", "content": "common/settings.py .env 로드, instruments.yaml 마이그레이션·검증, fail_reasons.py 9코드"}, {"id": "rewrite-models-extract", "content": "common/models.py ExtractedRatingRow/RatingRecord, agency.py, extract/* (row_parser 포함)"}, {"id": "rewrite-classify", "content": "classify/classifier.py exact-match + classify/recommend.py"}, {"id": "main-orchestration", "content": "main.py 선택 알고리즘·fail_reason·commit_batch_outputs 오케스트레이션"}, {"id": "export-json-excel", "content": "export/json_io.py·excel.py·undefined_store.py (occurrence_id dedup, tmp 저장)"}, {"id": "tests-docs", "content": "tests 재작성, README/.cursor/rules 갱신, pytest 확인"}]