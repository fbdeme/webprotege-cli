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

### 2. 현재 상태

| 기능 | 상태 |
|---|---|
| signup (계정 생성) | ✅ 동작 |
| login (+ storageState 캐시) | ✅ 동작 |
| projects (목록, `--json`) | ✅ 동작 |
| create (OWL 파일로 프로젝트 생성) | ✅ 동작 |
| export (Turtle/RDF-XML/… ZIP 다운로드) | ✅ 동작 |
| `npm test` (e2e: create→list→export→검증) | ✅ PASS |
| 인앱 미세 편집(클래스/프로퍼티/공리 추가) | ⬜ 미구현 |
| read-only raw-HTTP fast-path (`/download`) | ⬜ 미구현 |

검증: `test/fixtures/tiny.owl`(Widget, Gadget⊑Widget) 업로드 → 프로젝트 생성 → Turtle export → ZIP 내 `.ttl`에 클래스/subClassOf/label 보존 확인.

### 3. 다음 할 일 (즉시)

- [ ] GitHub repo 생성 여부/공개여부 사용자 확인 후 push
- [ ] `wp delete`(휴지통 이동) 추가 — 테스트 정리용
- [ ] 인앱 편집 커맨드 스파이크 (`addClass` 등) — 가치/안정성 평가

### 4. 메모

- 테스트는 throwaway 계정 `wpcli_test`로 수행 (사용자 실제 계정과 분리). 인스턴스에 `wpcli-smoke-1`, `wpcli-e2e-*` 테스트 프로젝트가 남아있음 — 해당 계정 한정, 무해.
- 셀렉터는 `4.0.0-beta-3` DOM에 핀됨. 이미지를 핀하므로 안정적.
