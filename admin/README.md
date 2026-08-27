# admin — 관리자 앱 개발자 매뉴얼

Streamlit 기반 **관리자 웹 앱**. 배치 추출(`main.py`)과 **별도 진입점**이며,  
결과 조회·예외 점검·상품 라벨 YAML 편집을 담당한다.

이 문서는 **개발자·AI 에이전트**용이다.  
- 운영자(비개발자) 화면 문구 → `content/ops_guide.md`  
- 추출·분류·Excel·설정 전체 → [`docs/CreditDocStruct_doc.md`](../docs/CreditDocStruct_doc.md)

---

## 1. 역할과 경계

| 할 일 | 하지 않는 일 |
|--------|----------------|
| `results/*.json` 로드·필터·공개 표·공개 Excel 바이트 | PDF 배치 루프, `commit_batch_outputs` |
| 사이드바 PDF 1건 → `extract_credit_report` → 세션(`result_test`) | JSON/DB에 업로드 결과 저장 |
| JSON → 확인 필요 목록 집계(읽기 전용) | 예외 상태 머신·별도 미분류 DB |
| `instruments.yaml` **라벨** 추가·삭제(`managed_by: admin`) | 새 `instrument_key`, 잠긴 라벨 수정, 재무지표 카탈로그 |
| YAML 쓰기 전 `admin/backup/` 스냅샷 | 백업 복원 UI |
| `ops_guide.md` 렌더 | 추출 규칙·매칭 정책 변경 UI |

```
main.py → results/*.json · documents.db
  → 확인 필요(읽기) → 상품 사전(YAML) → main.py 재추출
```

사이드바 업로드는 브라우저가 보낸 PDF 바이트를 서버에서 `extract_credit_report`로만 처리한다. 배치 저장은 하지 않는다.

---

## 2. 디렉터리

```
admin/
├── admin_main.py          # Streamlit 진입: 4탭 + 사이드바
├── requirements.txt       # streamlit, ruamel.yaml
├── setup_admin.bat        # 앱 루트 .venv + requirements + admin/requirements
├── run_admin.bat          # --server.address 0.0.0.0 --server.port 8501
├── run_extract.bat        # .env INPUT_DIR로 main.py 배치 추출 (관리자 UI와 별개)
├── views/                 # 탭 UI (I/O는 services만)
│   ├── results.py
│   ├── exceptions.py
│   ├── dictionary.py
│   └── guide.py
├── services/
│   ├── result_service.py
│   ├── exception_service.py
│   └── yaml_service.py
├── ui/
│   ├── theme.py           # CSS: 섹션 라벨, stAlert 글씨, Excel/추가/삭제 버튼
│   └── copy.py            # YAML 등 사용자향 에러 문구
├── content/
│   └── ops_guide.md       # 「운영 가이드」탭 본문
├── backup/                # YAML 쓰기 시 자동 백업 (제거 금지)
└── data/                  # documents.db 기본 위치
```

경로·상수는 `common/settings.py` / `.env`만 사용. admin에 절대 경로 하드코딩 금지.

앱 루트에 `.streamlit/config.toml`(테마 색)이 있다.

---

## 3. 실행·의존성

앱 루트: 저장소 루트.

```bat
admin\setup_admin.bat
admin\run_admin.bat      # 관리자 웹
admin\run_extract.bat    # PDF 추출 (INPUT_DIR → main.py)
```

`run_admin.bat`은 `0.0.0.0:8501`으로 바인딩한다. `run_extract.bat`은 Streamlit을 켜지 않고 `main.py`만 실행한다.

| 접속 | URL |
|------|-----|
| 서버 PC | `http://localhost:8501` |
| 같은 사내망 다른 PC | `http://{서버 PC IP}:8501` |

접속 실패 시 Windows 방화벽 **TCP 8501** 인바운드 확인. 앱 로그인 레이어는 없다.

서버 PC 인바운드 허용 방법
1. 관리자 관한으로 제어판 실행
2. Windows Defender 방화벽
3. 고급 설정
4. 인바운드 규칙
5. 새 규칙
6. 포트
7. TCP
8. 특정 로컬 포트: 8501
9. 연결 허용
10. 프로필(도메인/개인/공용) 체크
11. 이름: CreditDocStruct

CMD 테스트 (서버 PC)
1. Test-NetConnection {서버 PC IP} -Port 8501
   - TCPTestSucceeded = TRUE면 정상
2. netstat -ano | findstr :8501
   - 0.0.0.0:8501 또는 [::]:8501 이 보이면 정상

PowerShell 테스트 (다른 PC)
1. Test-NetConnection {서버 PC IP} -Port 8501
   - TCPTestSucceeded = TRUE면 정상
   - 반드시 서버 PC IP로 입력할 것!

다른 PC 인터넷망에서 `http://{서버 PC IP}:8501`에 접속한다.

수동:

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt -r admin/requirements.txt
.venv\Scripts\python.exe -m streamlit run admin/admin_main.py --server.address 0.0.0.0 --server.port 8501
```

---

## 4. 진입점 (`admin_main.py`)

- `st.set_page_config` → `inject_styles()` → 제목/캡션
- 사이드바: 새로고침(`st.rerun`), **확인 필요 N건**, PDF 1건 업로드·추출  
  - `list_result_files()[0]`(mtime 최신) → `count_exceptions` (JSON만)
  - 탭에서 다른 결과 파일을 고르면 사이드바와 건수가 다를 수 있음
  - 추출은 `extract_credit_report`만. 결과는 세션 `adhoc_results` / 셀렉트 `result_test` (결과 조회·확인 필요)
- 탭: 결과 조회 · 확인 필요 · 상품 사전 · 운영 가이드 → `render_*_tab()`

뷰는 `services`만 호출한다. 사이드바 1건 추출은 `admin_main`에서 `extract_credit_report`를 호출한다.

---

## 5. 서비스 계약

### 5.1 `result_service`

| 함수 | 역할 |
|------|------|
| `list_result_files` | `RESULT_DIR`의 `*.json`, mtime 내림차순 |
| `load_results_json` | JSON 배열 검증; 실패 시 `ResultServiceError` |
| `filter_results` | 신평사 표시명 exact / 회사명 substring |
| `build_public_rows*` | `build_excel_public_rows` — **success + 등급 있음**만 |
| `build_public_excel_bytes` | `write_results_excel_tmp` → 바이트 |
| `first_financial_table` / `financial_table_to_wide_rows` | 결과 조회 raw 재무 미리보기 |
| `financial_fail_message` | 재무 없음 시 `st.error` 문구 |

공개 Excel/표 게이트를 완화하지 않는다.

### 5.2 `exception_service`

`collect_exceptions(results) -> list[dict]` — 영속화 없음.  
각 항목: `type`, `type_label`, `action`(조치 caption), `detail` 등.

| `type` | `type_label` | 출처 |
|--------|--------------|------|
| `undefined_label` | 미분류 상품 | `undefined_records`(등급 있는 것만) |
| `rating_ambiguous` | 신용등급 모호/충돌 | 상품 `multiple_rating_columns` / `multiple_ratings` |
| `no_financial_table` | 재무지표 없음 | `financial_tables` 비어 있고 파일급 오류 아님 |
| `file_or_parse_error` | 파일/텍스트/구조 오류 | PDF급 `file_error` / `text_extraction_failed` / `parse_error` |

`action` 문구는 운영 가이드 §4와 맞춘다. 변경 시 `ops_guide.md`와 함께 수정.

`count_exceptions` = `len(collect_exceptions(...))`.

### 5.3 `yaml_service`

- **ruamel.yaml** (순서·주석 보존). PyYAML로 덮어쓰지 않음.
- 쓰기 전 `_backup_yaml` → `ADMIN_BACKUP_DIR`.
- `add_alias`: 정규화 충돌 검사 → `managed_by: admin`, `active: true`.
- `delete_aliases`: `managed_by == "admin"`만 삭제.
- `list_instrument_aliases`: UI용(`is_admin_managed`).

---

## 6. 탭별 구현 메모

### 결과 조회 (`views/results.py`)

- 셀렉트: 세션 업로드는 `result_test`가 맨 위, 그다음 `results/*.json`
- 필터 → 상태 요약 → 공개 신용등급 표 → Excel 다운로드
- 행 선택 → `financial_tables[0]` wide 표
- 행 없음 / 재무 행 없음 → **`st.error(financial_fail_message)`만**, 빈 dataframe 숨김

### 확인 필요 (`views/exceptions.py`)

- 셀렉트: 세션 업로드는 `result_test`가 맨 위, 그다음 `results/*.json` (결과 조회와 동일)
- 유형별 `section-label` + `action` caption + dataframe
- 쓰기·버튼 없음. 수정은 상품 사전 또는 `main.py` 재추출/개발

### 상품 사전 (`views/dictionary.py`)

- 잠금 라벨 / admin 관리 라벨 분리
- 버튼 key: `dict_confirm_{instrument_key}`, `dict_delete_{instrument_key}`  
  → `theme.py`의 `st-key-dict_confirm_*` / `st-key-dict_delete_*`로 색 지정
- YAML 반영 후 결과 JSON은 재추출 전까지 불변

### 운영 가이드 (`views/guide.py`)

- `content/ops_guide.md`만 표시. 스키마·모듈 설명은 넣지 않음

---

## 7. UI (`ui/theme.py`)

| 대상 | 방식 |
|------|------|
| 섹션 제목 | `.section-label` |
| `st.error` / `st.warning` 본문 | `stAlert` 글씨 크기 |
| Excel 다운로드 | `stDownloadButton` — 연한 초록 |
| 추가 / 삭제 | Streamlit `st-key-{key}` 클래스 — 연초록 / 연빨강 |

---

## 8. 데이터·설정

| 항목 | 설정 키 / 기본 |
|------|----------------|
| 결과 JSON | `RESULT_DIR` → `results/` |
| 상품 YAML | `INSTRUMENTS_YAML_PATH` → `config/instruments.yaml` |
| YAML 백업 | `ADMIN_BACKUP_DIR` → `admin/backup/` |
| documents.db | `DOCUMENT_DB_PATH` → `admin/data/documents.db` (UI는 JSON 중심) |

미분류 저장소: 결과 JSON `undefined_records` (+ 확인 필요 탭).

---

## 9. 유지보수·확장 규칙

1. I/O·규칙 → `services/`; 위젯 → `views/`; CSS/문구 → `ui/`·`content/`.
2. admin에 PDF 순회·배치 저장을 넣지 않는다.
3. 공개 행/Excel = success+등급 게이트 유지.
4. admin이 쓰는 YAML은 `label_dictionary`뿐.
5. `_backup_yaml` / `backup/` 유지. 복원은 파일 복사.
6. 운영자 문장 ↔ `ops_guide.md`, 개발 계약 ↔ 이 README.
7. 의존 방향: **admin → common/export**. 사이드바 1건만 `main.extract_credit_report`. 코어가 admin을 import하지 않음.
8. 예외 `action`/`type_label` 변경 시 `ops_guide.md` §4·테스트와 동기화.

---

## 10. 테스트

```bash
.venv\Scripts\python.exe -m pytest tests/test_yaml_service.py tests/test_exception_service.py tests/test_result_service.py tests/test_app_helpers.py -q
```

| 파일 | 검증 |
|------|------|
| `test_yaml_service.py` | managed_by 추가/삭제, 충돌, 백업 |
| `test_exception_service.py` | 예외 유형 집계 |
| `test_result_service.py` | 필터·공개 행·재무 헬퍼 |
| `test_app_helpers.py` | UI 헬퍼 |

---

## 11. 관련 문서

| 문서 | 내용 |
|------|------|
| 루트 `README.md` | 공개용 소개·실행 안내 |
| `docs/CreditDocStruct_doc.md` | 파이프라인·아키텍처·개발 규칙 |
| `About_CreditDocStruct.md` | 업무 배경 (구현 계약 원천 아님) |
| `admin/content/ops_guide.md` | UI 운영자 가이드 |
