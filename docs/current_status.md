# Current Status

> 최종 업데이트: 2026-06-26 (세션 3c — end-to-end 필드테스트 + S1 임베디드 이메일 해결)

---

## Session 2026-06-26 (3c) — 실 PI 온톨로지 end-to-end 필드테스트 + 새니타이저 임베디드 케이스 해결

**필드테스트 (throwaway 계정 `wpcli_h135555`, 미커밋 — study_abroad 불변)**: 실 PI 온톨로지(`pi-ontology.owl`, 2064트리플)로 `wp create "cli test"` → `projects` → `export` 전 과정 동작 확인. 업로드 충실도 = ObjectProperty 16/16·DatatypeProperty 14/14 일치, Class 14→15(owl:Thing 정규화), 개체 241→242 보존.

**발견 → 해결 (CLI 작업, 이 repo)**: 재export를 `onto info`로 읽을 때 S1(이메일 `@` 망가짐)이 라이브 재현 + **임베디드 케이스**가 새 발견 — 이메일이 텍스트 중간에 박히면 가짜 lang-tag 뒤 원문(`, NPGS 무본드).`)이 따옴표 밖에 남아 파싱 차단(line 3113). 새니타이저 정규식을 EOL 종결자까지 trailing 원문을 끌어들이도록 확장 → 실 export에서 40/40 복구(잔여 0), 임베디드 값 원문 그대로 재구성. 테스트 24→**29 통과**. issues #8 ✅ 해결.

---

## Session 2026-06-26 (3b) — 공리 하드닝 명령(CLI) + 실데이터 필드테스트

**CLI 작업 vs 온톨로지 구축 구분**: 새 `onto` 명령 = CLI 작업(이 repo). 그 명령으로 PI 온톨로지를 실제로 고치는 것 = 온톨로지 구축(study_abroad). 이번엔 **복사본/테스트만** — study_abroad 캐노니컬 불변.

### CLI 작업 (이 repo에 커밋)
- `onto` 공리 명령 3종 추가: `add-disjoint`(2개→disjointWith, 3+→AllDisjointClasses, 멤버셋 멱등), `add-characteristic`(functional/inverse-functional/transitive/symmetric/asymmetric/reflexive/irreflexive, object-only 가드), `add-inverse`. 전부 존재검사(안티-할루시네이션). 단위테스트 24/24.

### 필드테스트 (복사본·합성, throwaway 계정 — 미커밋)
- 실 PI 온톨로지(2064트리플) 복사본에 핵심 세트(상위12 AllDisjoint + Applicant⊥PI + functional 7개=tier/recruiting/inCountry/inUniversity/year/city/rank) 적용 → `validate --reason` **consistent**(2098트리플).
- **네거티브 검증**(공리 실효성): Columbia를 University+Country로 → INCONSISTENT, TTIC에 도시 2개 → INCONSISTENT. 공리가 실제로 모델링 에러를 잡음.
- **라이브 라운드트립**(합성 ontology, S1 회피): create→apply-edits→export에서 AllDisjointClasses/Functional/Symmetric 전부 보존. apply-edits 변경수=OWL **축** 수(3)와 일치 → **WebProtégé MergeUpload가 새 공리 타입을 올바르게 diff/저장/재export**(긍정 발견, issues #13).

### 다음
- ② skill화, 또는 남은 강화(S3 pre-flight IRI / S5 prune-reification / S6 state-based waits / `wp sync`·`wp delete`). 실 PI 온톨로지에 공리 영구 반영은 study_abroad 세션에서 별도 결정.

---

## Session 2026-06-26 (3) — S2 reasoner datatype 강화

`validate --reason`가 실 PI 온톨로지의 `xsd:gYear`에서 중단되던 문제(S2) 해결 — ① 실데이터 공리 하드닝의 선행 블로커였음.

- **Pellet fallback 조사 → 기각**: owlready2 0.51 번들 Pellet이 Java 25(class file 69)를 요구, 이 머신 Java 21(65) → datatype 무관하게 `UnsupportedClassVersionError`. (근거: 직접 재현)
- **대신 datatype 자동 완화+재시도**: HermiT 중단 메시지의 datatype IRI 추출 → reasoning 임시 그래프에서만 불투명 string으로 치환 → 재시도. 사용자 파일 불변, 클래스 일관성 추론 완주, 완화 내역 명시 출력.
- **검증**: 실 ~2000트리플(14클래스/241인스턴스) `validate --reason` → "consistent, no unsatisfiable classes"(gYear 1건 완화). 단위테스트 11/11(회귀 테스트 추가, java-guarded).
- 환경 점검 결과: onto 엔진 OK, Java21, owlready2 0.51, 라이브 WebProtégé HTTP 200(떠 있음).

### 다음
- 이제 ① **실데이터 공리 하드닝**(`onto`로 disjointWith/inverseOf/cardinality 추가 → validate --reason → apply-edits) 가능. 또는 ② skill화. 남은 강화: S3 pre-flight IRI, S5 prune-reification, S6 state-based waits, `wp sync`/`wp delete`.

---

## Session 2026-06-26 (2) — 실데이터 강화 조사

실 PI 온톨로지(~2000 트리플, reification·다국어·이메일)로 CLI를 굴려 한계 탐색. 상세: `strengthening.md`.

### 발견 (전부 재현·증거 기반)
- **S1 (high)**: WebProtégé 라운드트립이 `@` 리터럴(이메일)을 깨진 lang-tag로 변환 → export 파싱 불가(Turtle+RDF/XML 모두). 임베디드 이메일은 구조 파손. → `onto` 새니타이저(단순 40/40 복구) + **"캐노니컬 파일=진실원" 가이드**(export를 편집 베이스로 쓰지 말 것).
- **S2 (med)**: `validate --reason`가 `xsd:gYear` 등에서 HermiT 중단 → graceful degrade, Pellet fallback 계획.
- **S3 (med, 해결)**: `apply-edits` IRI 불일치 시 조용한 무반영 → 0-change 경고 추가.
- **S4 (low, 해결)**: `onto info` 개체 카운트 누락 → class-instance 카운트 추가.
- **S5/S6 (low)**: remove의 reification 고아화, Playwright 고정대기 → 계획.

### 이번에 적용한 수정
- `onto.py`: 새니타이저(S1), info 카운트(S4). `src/cli.js`: apply-edits 0-change 경고(S3).
- 단위테스트 8/8 유지. push 영역(파일→WebProtégé)은 실 규모에서 견고.

### 다음
- README "파일=진실원" 반영(완료), 나머지 계획 항목은 `todo.md` §2c.

---

## Session 2026-06-26 — 초기 빌드 (제어 표면 분석 → Playwright CLI)

**서버**: 로컬 self-host WebProtégé `4.0.0-beta-3` @ `http://localhost:5000` (`protegeproject/webprotege:latest` + `mongo:4.0`, docker compose). `webprotege-selfhost` 런북으로 띄운 인스턴스.

### 1. 직전 작업 요약

- 2019 모놀리식 이미지의 제어 표면을 JAR 디컴파일(CFR)+엔드포인트 프로빙으로 분석 → **REST 없음, 전부 GWT-RPC(`/webprotege/dispatchservice`) + CHAP 인증 + 커스텀 직렬화기 다수**. (`references/control-surface.md`)
- 전송수단 결정: 핸드롤 GWT-RPC 대신 **헤드리스 브라우저(Playwright)** — 앱 자체 JS가 CHAP·직렬화를 처리.
- `WebProtegeClient`(`src/wp.js`) + `wp` CLI(`src/cli.js`, commander) 구현: `signup` / `login` / `projects` / `create` / `export`.
- 라이브 인스턴스 대상 셀렉터 전부 실측 확정 (로그인·가입 폼, 프로젝트 테이블, 행 메뉴, 다운로드 포맷 다이얼로그).
- **하이브리드 결정 + merge-upload 다리 검증**: Project ▸ Apply External Edits = 파일→프로젝트 양방향 diff(추가+삭제) 적용·새 리비전. 디컴파일+라이브 왕복으로 확인. `applyExternalEdits` 구현(`wp apply-edits`). 제약: 업로드 온톨로지 IRI가 프로젝트와 동일해야 함.
- **구조화 편집 엔진 `onto.py`(Python/rdflib+owlready2) 빌드**: add-class/subclass/objprop/dataprop/individual/annotation/remove/validate(--reason HermiT)/query. 존재하지 않는 엔티티 참조 거부(안티-할루시네이션), Ontology IRI 보존, delta 출력. 단위테스트 8/8.
- **전체 하이브리드 루프 라이브 실증**: create→export(IRI 보존)→`onto` 편집(:Ghost 거부 + Cog 추가 + 추론 일관성)→`wp apply-edits`→재export에서 반영 확인.

### 2. 현재 상태

| 기능 | 상태 |
|---|---|
| signup (계정 생성) | ✅ 동작 |
| login (+ storageState 캐시) | ✅ 동작 |
| projects (목록, `--json`) | ✅ 동작 |
| create (OWL 파일로 프로젝트 생성) | ✅ 동작 |
| export (Turtle/RDF-XML/… ZIP 다운로드) | ✅ 동작 |
| **apply-edits** (Apply External Edits, 파일→프로젝트 merge) | ✅ 동작·검증(R2 리비전) |
| **`onto` 구조화 편집 엔진**(add-*/remove/validate --reason/query) | ✅ 동작·검증(8/8) |
| **하이브리드 루프** (export→onto→apply-edits) | ✅ 라이브 실증 |
| `npm test` (e2e) / `onto_test.py` | ✅ PASS / 8 passed |
| read-only raw-HTTP fast-path (`/download`) | ⬜ 미구현(선택) |

검증: `test/fixtures/tiny.owl`(Widget, Gadget⊑Widget) 업로드 → 프로젝트 생성 → Turtle export → ZIP 내 `.ttl`에 클래스/subClassOf/label 보존 확인.

### 3. 다음 할 일 (즉시)

- [ ] (선택) `wp sync` 단일 래퍼: export→unzip→[편집]→apply-edits 자동화 (현재는 수동 3스텝, README에 문서화됨)
- [ ] `wp delete`(휴지통 이동) 추가 — 테스트 정리용
- [ ] `onto` IRI-변경 가드 강화 / merge preview 변경건수 정밀 파싱
- [ ] (선택) `onto`를 pi_research/instances.ttl 실제 편집에 적용

### 4. 메모

- 테스트는 throwaway 계정 `wpcli_test`로 수행 (사용자 실제 계정과 분리). 인스턴스에 `wpcli-smoke-1`, `wpcli-e2e-*` 테스트 프로젝트가 남아있음 — 해당 계정 한정, 무해.
- 셀렉터는 `4.0.0-beta-3` DOM에 핀됨. 이미지를 핀하므로 안정적.
