---
scope: craft
triggers:
- 화면(을|이|에|은|의)?\s*(만들|고치|붙|추가|바꾸|띄)
- 프런?트\s*엔드|frontend
- \.tsx|\.jsx|리액트|React
- 모달|다이얼로그|팝업
- 저장(이|은|을|하면)?\s*(안 ?되|버튼|실패|거절)
- 로그인|로그아웃|계정\s*(전환|바꾸|경계)
- 입력\s*(칸|창|폼)|드롭다운|셀렉트
slots: []
links:
- screen-follows-the-purpose
- pick-up-async-results
- diagnose-from-what-ran
- verify-narrow-then-wide
- client-lifecycle-in-one-scope
severity: contract
sources: []
---

# 화면을 짜기 전에 계정 경계와 비동기 소유권을 정한다

규칙. 화면을 서버에 연결하기 전에 데이터의 주인, 상태의 유효 기간, 계정 변경 시 초기화 범위를 정한다. 저장과 재조회 경로, 실패 표시, 늦게 도착한 응답 처리를 함께 확인한다.
