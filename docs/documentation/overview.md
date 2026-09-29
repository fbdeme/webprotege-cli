---
title: webprotege-cli 개요
---
webprotege-cli는 self-host WebProtégé 인스턴스를 명령줄과 에이전트에서 조종하는 도구다. OWL/RDF 파일로 프로젝트를 만들고, 목록을 보고, 내보내고, 밖에서 고친 온톨로지를 새 리비전으로 반영하는 일을 웹 UI 클릭 없이 한다. 인스턴스는 별도 런북 `webprotege-selfhost`로 띄운다.

## 왜 브라우저 자동화인가
대상 이미지 `protegeproject/webprotege:latest`(`4.0.0-beta-3`, 유일하게 공개된 태그)에는 REST API가 없다. 모든 기능이 GWT-RPC 서블릿 하나(`/webprotege/dispatchservice`)를 거치고, 인증은 CHAP 핸드셰이크이며, 페이로드는 수십 개의 커스텀 GWT 직렬화기에 기대고 있다([[I001]], [[I002]], [[I003]]). 이 프로토콜을 직접 구현하면 액션마다 직렬화기를 새로 만들어야 한다. 반면 헤드리스 브라우저(Playwright)는 앱 자체 JavaScript가 CHAP과 직렬화를 처리하므로 쓰기 작업까지 견고하게 다루고, 유지할 것은 셀렉터뿐이다. UI 자동화의 흔한 약점인 바뀌는 DOM은 이미지 버전을 고정해서 사실상 없앤다.

## 구성
- `wp` CLI(Node, `src/cli.js`)와 라이브러리 `WebProtegeClient`(`src/wp.js`): `signup`, `login`, `projects`, `create`, `export`, `apply-edits`. 셀렉터는 `4.0.0-beta-3`에 고정돼 있다.
- `onto`(Python, `onto.py`, rdflib와 owlready2): 구조화되고 검증된 온톨로지 편집 명령. 없는 엔티티를 참조하는 편집을 거부하고 Ontology IRI를 보존한다.
- 온톨로지 편집은 가능하면 파일 수준에서 `onto`로 하고, WebProtégé 조종은 프로젝트 수명주기(생성, 목록, 내보내기)와 시각화에 집중한다. 앱 안에서의 세부 편집 명령은 가치와 안정성을 평가한 뒤 선택적으로 추가한다.
- Python 환경: `onto`는 venv에서 돌린다. 이 머신의 python에는 ensurepip이 없어 venv를 만든 뒤 `get-pip.py`로 pip을 설치했다.
- 테스트: `npm test`(`test/e2e.js`, 라이브 인스턴스 대상), `test/onto_test.py`(오프라인).

## 배포
- 저장소: `https://github.com/fbdeme/webprotege-cli`(공개, 기본 브랜치 main). `fbdeme/webprotege-selfhost` README 8행에 이 CLI를 가리키는 "Companion" 링크가 있다.
- Claude Code 스킬: 공개 저장소 `fbdeme/webprotege-cli-skill`(SKILL.md, README, LICENSE, `scripts/setup.sh`)로 2026-06-26에 발행했다. 도구 저장소가 `webprotege-cli` 이름을 쓰므로 스킬 저장소에는 `-skill`을 붙였다. 이 저장소 README가 스킬을 링크하고, 스킬의 SKILL.md에는 `onto diff`가 들어 있다.

## 하위 문서
- [[overview/control-surface]]: 제어 표면 조사 방법과 결과.
- [[overview/hybrid-editing]]: export → `onto` 편집 → `apply-edits` 흐름과 제약.
- [[overview/strengthening]]: 실데이터 강화 조사 결과(S1–S7).
- [[overview/accounts]]: 로컬 인스턴스의 계정 구성.
