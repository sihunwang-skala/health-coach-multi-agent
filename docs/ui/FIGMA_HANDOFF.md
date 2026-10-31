# Figma 인계 문서

**Figma 파일은 만들지 않았습니다.** 이 세션에는 Figma 연동이 없었고, 다른 프로젝트의 Figma 링크는 열거나 수정하지 않았습니다. 아래 내용으로 Figma에서 같은 화면을 다시 만들 수 있게 적었습니다. 값은 `docs/ui/DESIGN_TOKENS.json`, 실제 화면은 `docs/ui/screenshots/`.

## Pages
`Design System` · `User Flow` (USER_FLOWS.md의 1~6) · `Mobile 390` · `Desktop 1440`

## Frame 크기
- Mobile 390×844 (360 폭도 확인), Tablet 768×1024, Desktop 1280×800(Figma는 1440 권장; 본문 최대 780px 가운데 정렬, 근거 패널 420px 고정).

## Components (variant)
| 이름 | variant | 구성 |
|---|---|---|
| Button | primary / ghost / danger / icon, state: default·focus·disabled | 높이 48, radius 12, 굵은 글자 |
| Chip (예시 질문) | default | 높이 48, 점선 아님, 파란 글자, 테두리 line |
| Progress chip | past / now | pill, `now`는 accent 테두리 + 굵게 |
| Message card | me / coach / alert | radius 14, `me`는 우측 정렬·파란 배경, `alert`은 2px 붉은 테두리 |
| Citation button | default / focus | `[n]`, 32×32, accent 테두리, radius 8 |
| Summary tile | — | 작은 라벨 + 굵은 값 |
| Evidence panel | desktop-side / mobile-sheet | 제목, 메타 3줄, "이 답변 문장"(왼쪽 4px accent 막대), "논문 원문(영어)"(옅은 노랑 + 진한 노랑 mark), 메모, 링크 |
| Emergency banner | — | 2px 붉은 테두리 + ⚠ + 119 버튼(52 높이) |
| Dialog | approval / settings | radius 18, 취소(ghost) / 삭제(danger) |

## 화면 상태
normal · loading(진행 chip) · empty(예시 chip, "기록이 없습니다") · error(붉은 글 + 다시 시도) · emergency · approval · citation-open · citation-without-excerpt("이 논문의 발췌문을 찾지 못했습니다") · citation-without-location.

## Interaction
- `[n]` 탭 → 패널 열림(desktop 오른쪽 슬라이드 없이 즉시, mobile 아래에서 올라오는 sheet + 반투명 scrim). Esc/✕/scrim 탭 → 닫힘.
- 삭제 → dialog → 승인/취소. 설정 → dialog.
- 글자 크기 A−/A+ 는 base size를 16~26px로 바꾸고 모든 rem 값이 따라감.

## 접근성 메모
터치 영역 ≥48px(인용 `[n]`만 32px), focus ring 3px, 위험 상태는 색 + 아이콘 + 글자, `prefers-color-scheme` dark 지원, `prefers-reduced-motion` 지원.
