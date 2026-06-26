# Issues & Technical Decisions

> 구현 과정에서 발견된 기술적 이슈와 해결 상태.
> 번호는 절대 재사용 안 함. 해결돼도 그대로 두고 상태만 변경.

상태 마커: ✅ 해결됨 / 🔄 진행 중 / ⏸️ 보류 / ❌ 무효화

---

## Issue #1: 2019 이미지에 REST API가 없음 — 제어 표면 미상

**상태: ✅ 해결됨 (2026-06-26)**

### 문제

CLI로 WebProtégé를 제어하려는데 공식 REST/HTTP API 문서가 없음. `web.xml`엔 서블릿 매핑이
없고 단일 catch-all 필터만 있음.

### 원인

`4.0.0-beta-3`는 GWT 앱. 모든 기능이 단일 GWT-RPC 서블릿(`/webprotege/dispatchservice`,
`@RemoteServiceRelativePath("dispatchservice")`)의 `executeAction(Action)` 한 메서드로 흐름.
유일한 비-GWT 엔드포인트 `/download`도 인증 세션 필수(미인증 403).

### 해결 방법

| 시도 | 결과 |
|---|---|
| 후보 경로 프로빙(`/dispatch`, `/fileupload` 등) | 대부분 404, `/webprotege/dispatchservice`만 500(존재) |
| JAR 디컴파일(CFR)로 인터페이스/핸들러 확인 | 액션 핸들러 전수 확인 — 전부 GWT-RPC |

→ 상세: `references/control-surface.md`.

---

## Issue #2: 인증이 CHAP 핸드셰이크 (단순 폼 로그인 아님)

**상태: ✅ 해결됨 (2026-06-26)**

### 문제

세션 쿠키를 얻으려면 로그인을 재현해야 하는데 username/password 폼 POST가 아님.

### 원인

`GetChapSession` → 챌린지/솔트 수신 → `PerformLogin`(MD5 기반 CHAP 응답) 2단계.
`saltedPwd = MD5(utf8(hex_lower(salt)) || utf8(pwd))`,
`resp = MD5(challenge || saltedPwd)`.

### 해결 방법

| 시도 | 결과 |
|---|---|
| CHAP를 Python/Node로 직접 재구현 | 가능하나 직렬화기 벽(Issue #3)으로 ROI 낮음 |
| **브라우저 자동화로 앱 JS가 처리** | 채택 — CHAP/직렬화 전부 위임 |

---

## Issue #3: GWT-RPC 커스텀 직렬화기 벽

**상태: ✅ 해결됨 (2026-06-26) — 브라우저 자동화로 우회**

### 문제

핸드롤 RPC로 실제 액션(프로젝트 생성/목록, 프레임 편집)을 호출하려면 각 타입의 직렬화를
재현해야 함.

### 원인

`AvailableProject`, `ProjectDetails`, `NewProjectSettings`, 엔티티/프레임 타입 등 다수가
`CustomFieldSerializer`(주로 AutoValue)를 가짐 → 액션마다 직렬화기 재구현 필요.

### 해결 방법

브라우저가 앱 JS를 통해 직렬화를 수행하므로 추가 비용 0. (Playwright)

---

## Issue #4: 다운로드가 단일 파일이 아니라 ZIP

**상태: ✅ 해결됨 (2026-06-26) — 동작으로 수용**

### 문제

`export`가 `.ttl`/`.owl` 단일 파일이 아니라 ZIP을 내려줌.

### 원인

`/download` 서블릿이 리비전 디렉토리 구조를 ZIP으로 패키징
(`<project>-ontologies-<fmt>-REVISION-HEAD/<file>`).

### 해결 방법

ZIP을 그대로 저장(`--out`). 향후 자동 압축 해제 옵션(`--unzip`)을 todo에 둠.

---

## Issue #5: 다이얼로그 컨테이너 클래스가 난독화됨

**상태: ✅ 해결됨 (2026-06-26)**

### 문제

GWT가 다이얼로그 클래스를 `GC5IROGBCX`처럼 난독화 → 컨테이너 스코핑 불가.

### 해결 방법

전역 셀렉터 + 모달 오픈 시의 불변식 이용(예: 생성 다이얼로그에선 `input[type=text]`가 정확히
2개=name·language, confirm 버튼은 `inPopup` 판정). 안정 클래스(`wp-project-list__*`,
`[title=Menu]`)는 그대로 사용. 이미지 핀 전제.

---

## Issue #6: Apply External Edits — 업로드 온톨로지 IRI가 다르면 조용히 무반영

**상태: ✅ 해결됨/문서화 (2026-06-26)**

### 문제

merge-upload(파일→프로젝트 반영)가 어떤 경우 아무 변경도 적용하지 않고 조용히 끝남.

### 원인

`ModifiedProjectOntologiesCalculator.isDifferentVersionOfOntology`가 프로젝트 온톨로지와
업로드 온톨로지의 **Ontology IRI가 동일(둘 다 non-anonymous)** 할 때만 diff를 계산. IRI가
다르거나 anonymous면 diff 스킵 → 변경 0 → 무반영(에러도 없음).

### 해결 방법

- export로 현재 프로젝트의 Ontology IRI를 확인하고, 편집본도 **같은 IRI**로 유지.
- 라이브 검증: 동일 IRI로 추가+삭제가 정상 반영, 새 리비전(R2) 생성 확인.

### 향후 고려사항

구조화 편집 엔진에서 "export→편집" 시 Ontology IRI를 절대 바꾸지 않도록 강제(가드) 필요.

---

## Issue #7: Apply External Edits는 2단계 다이얼로그

**상태: ✅ 해결됨 (2026-06-26)**

### 문제

파일 선택 후 OK 한 번으론 merge가 커밋되지 않음.

### 원인

1차 "Upload ontologies"(파일→OK)는 업로드+diff 계산만 하고, 2차 "Merge ontologies"
미리보기(변경목록 + commit message + OK)에서 비로소 커밋. 1차 OK만 누르면 미반영.

### 해결 방법

`applyExternalEdits`가 두 다이얼로그를 모두 처리: 파일→OK → "Changes to be applied" 대기 →
(commit message 입력) → 2차 OK.
