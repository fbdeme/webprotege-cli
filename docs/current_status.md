# Current Status

> 최종 업데이트: 2026-06-26 (MVP 동작 — create/list/export 라이브 검증 완료)

---

## Session 2026-06-26 — 초기 빌드 (제어 표면 분석 → Playwright CLI)

**서버**: 로컬 self-host WebProtégé `4.0.0-beta-3` @ `http://localhost:5000` (`protegeproject/webprotege:latest` + `mongo:4.0`, docker compose). `webprotege-selfhost` 런북으로 띄운 인스턴스.

### 1. 직전 작업 요약

- 2019 모놀리식 이미지의 제어 표면을 JAR 디컴파일(CFR)+엔드포인트 프로빙으로 분석 → **REST 없음, 전부 GWT-RPC(`/webprotege/dispatchservice`) + CHAP 인증 + 커스텀 직렬화기 다수**. (`references/control-surface.md`)
- 전송수단 결정: 핸드롤 GWT-RPC 대신 **헤드리스 브라우저(Playwright)** — 앱 자체 JS가 CHAP·직렬화를 처리.
- `WebProtegeClient`(`src/wp.js`) + `wp` CLI(`src/cli.js`, commander) 구현: `signup` / `login` / `projects` / `create` / `export`.
- 라이브 인스턴스 대상 셀렉터 전부 실측 확정 (로그인·가입 폼, 프로젝트 테이블, 행 메뉴, 다운로드 포맷 다이얼로그).
- **하이브리드 결정 + merge-upload 다리 검증**: Project ▸ Apply External Edits = 파일→프로젝트 양방향 diff(추가+삭제) 적용·새 리비전. 디컴파일+라이브 왕복으로 확인. `applyExternalEdits` 구현(`wp apply-edits`). 제약: 업로드 온톨로지 IRI가 프로젝트와 동일해야 함.

### 2. 현재 상태

| 기능 | 상태 |
|---|---|
| signup (계정 생성) | ✅ 동작 |
| login (+ storageState 캐시) | ✅ 동작 |
| projects (목록, `--json`) | ✅ 동작 |
| create (OWL 파일로 프로젝트 생성) | ✅ 동작 |
| export (Turtle/RDF-XML/… ZIP 다운로드) | ✅ 동작 |
| **apply-edits** (Apply External Edits, 파일→프로젝트 merge) | ✅ 동작·검증(R2 리비전) |
| `npm test` (e2e: create→list→export→검증) | ✅ PASS |
| 구조화 편집 엔진(owlready2: add-class/subclass/axiom + 검증·추론) | ⬜ 다음 단계 |
| read-only raw-HTTP fast-path (`/download`) | ⬜ 미구현 |

검증: `test/fixtures/tiny.owl`(Widget, Gadget⊑Widget) 업로드 → 프로젝트 생성 → Turtle export → ZIP 내 `.ttl`에 클래스/subClassOf/label 보존 확인.

### 3. 다음 할 일 (즉시)

- [ ] **구조화 편집 엔진** 빌드 (owlready2): `add-class` / `add-subclass` / `add-objprop` / `add-annotation` / `remove` — 각 명령이 엔티티 존재검사 + parse + 일관성 검사. (할루시네이션 방어의 본체)
- [ ] 편집 엔진 ↔ apply-edits 연결: export(IRI 보존) → 구조화 편집 → `apply-edits`로 WebProtégé 반영. `wp edit ...` 또는 통합 워크플로우.
- [ ] apply-edits/openProject 코드 push (현재 미커밋)
- [ ] `wp delete`(휴지통 이동) 추가 — 테스트 정리용

### 4. 메모

- 테스트는 throwaway 계정 `wpcli_test`로 수행 (사용자 실제 계정과 분리). 인스턴스에 `wpcli-smoke-1`, `wpcli-e2e-*` 테스트 프로젝트가 남아있음 — 해당 계정 한정, 무해.
- 셀렉터는 `4.0.0-beta-3` DOM에 핀됨. 이미지를 핀하므로 안정적.
