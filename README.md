# CreditDocStruct

국내 3사 신용평가서 PDF에서 신용등급과 주요 재무지표를 추출합니다.

신용평가사 3사 : NICE신용평가, 한국신용평가, 한국기업평가

## 사용

사이드바에 PDF 1개를 올린 뒤 **테스트 추출**을 누릅니다. 결과는 세션에만 보이며 서버에 저장되지 않습니다.

## 로컬 실행

Python 3.11 또는 3.12.

```bat
copy .env.example .env
admin\setup_admin.bat
admin\run_admin.bat
```

http://localhost:8501

```bash
streamlit run streamlit_app.py
```
