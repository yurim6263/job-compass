---
tags: [내경험, 프로젝트, 제조AI]
sources:
  - "[[Projects/SecondBrain/raw/내경험/text/가상경험_요약|가상경험_요약]]"
updated: 2026-10-31
origin: 혼합
---

# 가상프로젝트A — 설비 이상 탐지·잔여수명 예측 대시보드 (시험용 가상 카드)

> 시험용 가상 문서다. `/job-posting` 점수 시험에 쓰는 가짜 카드이며 실제 경험이 아니다.

## 경험 카드

### exp-20261031-01 센서 로그 전처리 규칙과 LSTM 이상 탐지 모델·평가를 맡음 (4명 팀)
- origin: 팀
- title: 센서 로그의 결측·이상치 처리 규칙을 만들고 LSTM 이상 탐지 모델과 평가 스크립트를 맡음
- problem: 센서 로그에서 고장 징후를 사람이 그래프로 보고 판단해 발견이 늦었음
- role: 4명 팀에서 데이터 전처리, LSTM 이상 탐지 모델, 평가를 맡음
- action: 결측은 앞뒤 값으로 보간하고 평균에서 3표준편차 밖은 이상치로 표시하는 규칙을 만들고, 윈도우 길이 30·60·120을 비교함
- change: 윈도우 60이 가장 안정적이었고 검증셋 F1은 0.89(가상 데이터 기준)
- numbers: △ F1 0.89 (가상 데이터 기준) [수치 확인 필요]
- job_link_tags: [제조AI, 설비데이터, 시계열예측]
- keywords: [LSTM, 전처리, 윈도우, F1, Python]
- question_types: [직무역량, 문제해결]
- evidence:
  - [[Projects/SecondBrain/raw/내경험/text/가상경험_요약|가상경험_요약]] — 가상프로젝트A 절
- fact_status: 자료확인

### exp-20261031-02 팀 프로젝트 이후 Transformer 비교 모델과 평가 자동화를 혼자 추가함
- origin: 본인작성
- title: 팀 프로젝트 뒤 Transformer 비교 모델과 평가 자동화를 혼자 추가함
- problem: 팀 단계 모델은 LSTM 하나였음
- role: 개인 고도화를 혼자 진행함
- action: Transformer 비교 모델을 추가하고 평가 자동화를 넣음
- change: 같은 가상 검증셋에서 F1 0.91
- numbers: △ F1 0.91 (가상 데이터 기준) [수치 확인 필요]
- job_link_tags: [ML/DL, 시계열예측]
- keywords: [Transformer, 평가 자동화, F1]
- question_types: [성장]
- evidence:
  - [[Projects/SecondBrain/raw/내경험/text/가상경험_요약|가상경험_요약]] — 개인 고도화 절
- fact_status: 자료확인

### exp-20261031-03 UI/UX 설계와 프론트엔드 구현(근거 미확인)
- origin: 팀
- title: 노션에만 적힌 UI/UX·프론트엔드 구현 주장
- problem: [확인 필요]
- role: [확인 필요]
- action: [확인 필요]
- change: [확인 필요]
- job_link_tags: [프론트/웹]
- keywords: [프론트엔드]
- evidence:
  - [[Projects/SecondBrain/raw/내경험/text/가상경험_요약|가상경험_요약]] — 노션에만 적힌 주장 절
- fact_status: 미확인
