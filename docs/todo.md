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

## 2b. 하이브리드 편집 (다음 단계)

- [ ] 구조화 편집 엔진(owlready2/rdflib): `add-class`/`add-subclass`/`add-objprop`/`add-annotation`/`remove`
  - [ ] 각 명령 = 엔티티 존재검사 + delta 적용 + parse 검증
  - [ ] `validate` = 일관성/추론 검사(HermiT)
  - [ ] Ontology IRI 보존(apply-edits 전제) 보장
- [ ] 통합 워크플로우: export(IRI 보존) → 구조화 편집 → `apply-edits` 반영
- [ ] merge preview의 변경 건수/내용 파싱해 반환(현재 근사치)

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
