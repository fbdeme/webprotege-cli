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

---

> 아래 #8~#12는 실데이터(~2000 트리플) 실험에서 발견 — 상세·근거·계획은 `strengthening.md` 참조.

## Issue #8: WebProtégé 라운드트립이 `@` 리터럴(이메일)을 깨뜨림

**상태: ✅ 해결됨 (2026-06-26)** — high

### 문제/원인

plain literal `"user@dept.edu"` → WebProtégé export에서 `"user"@dept.edu`(도메인=언어태그). 점 든 lang tag는 Turtle/RDF 위반 → rdflib 거부. Turtle뿐 아니라 RDF/XML(`xml:lang`)도 동일 → **저장값 자체 손상**. 실데이터(`cli test` export)에서 40건(39 단순 + 1 임베디드).

**임베디드 케이스(라이브 필드테스트 `cli test`에서 발견, 2026-06-26)**: 이메일이 자유 텍스트 *중간에* 박히면 가짜 lang-tag 뒤에 원문이 더 이어짐:
```
:note "MMLab 2026/27 모집(중앙접수 mmlab-contact"@e.ntu.edu.sg, NPGS 무본드). ;
```
초기 새니타이저는 도메인(`e.ntu.edu.sg`)까지만 재결합해 `, NPGS 무본드).` 가 따옴표 밖에 남음 → `,` 가 Turtle objectList 구분자로 오인 → `Bad syntax (objectList expected)`. 단순 이메일 40건은 복구됐으나 이 1건이 파싱 차단.

### 해결 방법

- (shipped) `onto` load 새니타이저: `"…"@<점든태그>` → 따옴표 안으로 재결합. **정규식을 EOL 종결자(`;`/`.`/`,`)까지 trailing 원문을 끌어들이도록 확장** → 단순/임베디드 양쪽 복구. 실 export(`cli test`)에서 40/40 복구(잔여 0), `onto info` 클린 파싱 + 임베디드 값 원문 그대로 재구성 확인(`"…mmlab-contact@e.ntu.edu.sg, NPGS 무본드)."`). 회귀 테스트 추가.
- (guidance) **캐노니컬 파일을 진실원으로** — WebProtégé export를 편집 베이스로 쓰지 말 것. 편집은 파일에서 `onto`, 반영은 `apply-edits`로 push만. (새니타이저는 안전망이지 정식 경로가 아님.)

## Issue #9: `validate --reason`가 OWL2 외 datatype에서 중단

**상태: ✅ 해결됨 (2026-06-26)** — med

HermiT가 `xsd:gYear` 등 OWL2 datatype map 밖 타입 거부(`UnsupportedDatatypeException`).

- **Pellet fallback 조사 후 기각**: owlready2 0.51 번들 Pellet(Jena)이 Java 25(class file 69)를 요구 — 이 머신은 Java 21(65). datatype과 무관하게 `UnsupportedClassVersionError`로 못 돎.
- **대신 datatype 완화 재시도 도입**: HermiT 중단 메시지에서 문제 datatype IRI를 추출 → reasoning용 임시 그래프에서만 해당 literal/`rdfs:range`를 불투명 string으로 치환 → 재시도(미지원 타입마다 1패스). 사용자 파일 불변. 클래스 일관성/불충족 추론은 완주. 완화 내역은 `reasoner: relaxed …` 라인으로 명시. 실 ~2000트리플로 검증("consistent"). 회귀 테스트 추가(java-guarded). parse/structural `validate`는 원래 영향 없음.

## Issue #10: `apply-edits` IRI 불일치 시 조용한 무반영

**상태: ✅ 해결됨 (2026-06-26)** — med

업로드 온톨로지 IRI≠프로젝트 IRI → merge 0건인데 "applied (~0)" exit 0. → 0 changes일 때 경고 출력(원인=IRI 불일치 안내). 향후: 업로드 전 IRI 사전 비교.

## Issue #11: `onto info` 개체 카운트 누락

**상태: ✅ 해결됨 (2026-06-26)** — low

`owl:NamedIndividual`만 세어 `a :Class`로만 선언된 개체(실데이터 241명)를 0으로 표시. → "owl:NamedIndividual N개, class instance M개" 둘 다 출력.

## Issue #12: `onto remove`가 reification blank node 고아화

**상태: ⏸️ 보류 (2026-06-26)** — low

엔티티가 reified `rdf:Statement`의 subject/object면 remove 후 blank node가 남음. 향후 `--prune-reification` 옵션.

## Issue #13: apply-edits가 공리(AllDisjointClasses/characteristics)를 올바르게 다루는가? — YES

**상태: ✅ 확인됨 (2026-06-26)** — positive finding

### 질문

`add-disjoint`/`add-characteristic`로 만든 공리(특히 bnode 기반 `owl:AllDisjointClasses`, property characteristic)가 `apply-edits`(MergeUpload) diff·저장·재export를 통과하는지 불확실했음(S1처럼 조용히 누락될 위험).

### 검증

합성 ontology(Cat/Dog/Fish + livesWith/age)로 create→apply-edits(하드닝본)→export 라이브 실행:
- apply-edits 변경수 = **3** = 추가한 OWL **축** 수(AllDisjointClasses 1 + FunctionalProperty 1 + SymmetricProperty 1). WebProtégé는 트리플이 아니라 **OWL 축 단위**로 diff함.
- export 결과에 `owl:AllDisjointClasses` + `owl:members ( :Cat :Dog … )`, `owl:FunctionalProperty`, `owl:SymmetricProperty` 모두 보존.

→ 공리 하드닝 명령은 push 경로(file→WebProtégé)에서 안전. (오프라인에선 HermiT가 disjoint/functional 위반을 INCONSISTENT로 잡는 것도 실데이터로 확인.)
