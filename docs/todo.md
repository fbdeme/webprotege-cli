# TODO

> 카테고리별 체크리스트. 완료 시 [x] + 날짜 기록. 완료 항목 삭제 X.

---

## 1. 분석 / 설계

- [x] 2019 이미지 제어 표면 분석 (REST/GWT-RPC/CHAP) (2026-06-26)
- [x] 전송수단 결정 — 브라우저 자동화 채택 (2026-06-26)
- [x] 제어 표면 reference 문서화 (`references/control-surface.md`) (2026-06-26)

## 2. 구현 (CLI)

- [x] `WebProtegeClient` 라이프사이클 + storageState 캐시 (2026-06-26)
- [x] `signup` / `login` (2026-06-26)
- [x] `projects` 목록 (`--json`) (2026-06-26)
- [x] `create` — OWL 파일로 프로젝트 생성 (2026-06-26)
- [x] `export` — 포맷 선택 ZIP 다운로드 (2026-06-26)
- [x] `apply-edits` — Apply External Edits(파일→프로젝트 양방향 merge, 새 리비전) + `openProject` (2026-06-26)
- [ ] `delete` — 프로젝트 휴지통 이동 (테스트 정리·관리용)
- [ ] `export --unzip` — ZIP 자동 해제해 단일 파일 저장

## 2b. 하이브리드 편집

- [x] 구조화 편집 엔진 `onto.py`(rdflib): `add-class`/`add-subclass`/`add-objprop`/`add-dataprop`/`add-individual`/`add-annotation`/`remove`/`remove-subclass`/`info`/`query` (2026-06-26)
  - [x] 각 명령 = 엔티티 존재검사(없으면 거부) + delta 적용 + parse 가드 (2026-06-26)
  - [x] `validate --reason` = HermiT 일관성/불충족 클래스 검사(owlready2) (2026-06-26)
  - [x] Ontology IRI 보존 — save 시 변경되면 abort (2026-06-26)
  - [x] 단위테스트 `test/onto_test.py` 8/8 (2026-06-26)
- [x] 통합 워크플로우 라이브 실증: export(IRI 보존) → `onto` 편집 → `wp apply-edits` 반영 (2026-06-26)
- [x] 공리 하드닝 명령 `add-disjoint`(disjointWith/AllDisjointClasses) / `add-characteristic`(functional·inverse-functional·transitive·symmetric·asymmetric·reflexive·irreflexive) / `add-inverse` — 존재검사+멱등, 단위테스트 포함(24/24) (2026-06-26)
- [x] 공리 하드닝 라이브 실증: create→apply-edits→export 라운드트립에서 AllDisjointClasses/Functional/Symmetric 보존, 변경수=OWL 축 수 (2026-06-26)
- [ ] (선택) `wp sync` 단일 래퍼로 3스텝 자동화
- [ ] merge preview의 변경 건수/내용 정밀 파싱(현재 근사치)
- [ ] (선택) `add-cardinality`(min/max/exact 제약) — 현재는 functional로 "≤1"만 커버

## 2c. 강화 (실데이터 ~2000트리플 실험 발견 — 상세 `strengthening.md`)

- [x] (S1) `onto` load 새니타이저: WebProtégé가 깨뜨린 `@` 이메일 리터럴 복구 (2026-06-26)
- [x] (S3) `apply-edits` 0-change 경고(IRI 불일치 안내) (2026-06-26)
- [x] (S4) `onto info` class-instance 카운트 추가 (2026-06-26)
- [x] (S1) **README에 "파일=진실원" 패턴 명문화** — WebProtégé export를 편집 베이스로 쓰지 말 것 (2026-06-26)
- [ ] (S1) 임베디드 이메일(자유텍스트 내) 라인지향 복구(필요 시)
- [x] (S2) `validate --reason` 미지원 datatype 자동 완화+재시도 (Pellet은 Java25 요구로 기각) (2026-06-26)
- [ ] (S3) `apply-edits` 업로드 전 IRI 사전 비교 체크
- [ ] (S5) `onto remove --prune-reification`
- [ ] (S6) Playwright 고정 대기 → 상태기반 대기(대용량/느린 인스턴스 대비)

## 3. 테스트 / 검증

- [x] 라이브 e2e (create→list→export→내용 검증) — `npm test` PASS (2026-06-26)
- [ ] 다중 프로젝트 목록 파싱 회귀 테스트
- [ ] 로그인 실패/중복 가입 등 에러 경로 테스트

## 4. 문서화

- [x] README (설치/사용/라이브러리) (2026-06-26)
- [x] docs-pattern 5종 부트스트랩 + 채우기 (2026-06-26)
- [ ] `webprotege-selfhost` README에서 본 CLI를 companion으로 상호 링크

## 5. 배포 / 인프라

- [ ] GitHub repo 생성 (공개여부 확인) + push
- [ ] (선택) Claude Code 스킬로 래핑할지 검토 — 또는 selfhost 스킬에서 참조
- [ ] read-only `/download` raw-HTTP fast-path (브라우저로 1회 로그인→쿠키 재사용)
