---
title: 로컬 인스턴스 계정 구성
---
CLI는 `webprotege-selfhost` 런북으로 띄운 로컬 WebProtégé(`http://localhost:5000`)에 붙는다. 인스턴스는 가입(sign-up)이 켜져 있어야 하며, 가입을 켜는 MongoDB 시드는 그 런북에 있다.

## 계정 종류
- 사용자 실제 계정: 사람이 WebProtégé를 쓰는 계정이다. CLI 테스트에는 쓰지 않는다.
- 일회용 테스트 계정: CLI 개발과 테스트는 실제 계정과 분리된 일회용 계정으로 한다.
  - `wpcli_test`: 초기 빌드의 e2e 테스트용. 이 계정 아래에 테스트 프로젝트 `wpcli-smoke-1`과 `wpcli-e2e-*`가 남아 있으며, 이 계정에만 속하므로 다른 계정에는 영향이 없다.
  - `wpcli_h135555`: 실 PI 온톨로지 end-to-end 필드테스트용. 이 계정으로 `cli test` 프로젝트를 만들었다([[I008]], [[I014]]).
- WebProtégé에서 프로젝트는 소유 계정별로만 보인다. 한 계정이 만든 프로젝트는 다른 계정의 목록에 나오지 않는다. 로컬 인스턴스에는 사람이 쓰는 계정 1개와 자동화용 일회용 계정이 함께 있다.
- `wp delete` 명령이 없어서 테스트 프로젝트 정리는 웹 UI에서 손으로 한다.
- 새 계정은 `wp signup --email <주소>`로 만든다. `test/e2e.js`는 `WP_EMAIL`이 있고 계정이 없으면 먼저 가입한다.

## 자격 증명 전달
사용자 이름과 비밀번호는 플래그나 환경 변수로 넘긴다: `WP_USER`/`--user`, `WP_PASS`/`--pass`, `WP_EMAIL`/`--email`(가입 때만). `WP_STATE`/`--state`로 로그인 세션을 파일에 캐시할 수 있다. 비밀번호 값은 저장소 문서에 적지 않는다.

## 권한
Apply External Edits에는 프로젝트 수준 `UPLOAD_AND_MERGE`와 `EDIT_ONTOLOGY` 권한이 필요하며, 프로젝트 소유자는 둘 다 가진다. Apply External Edits 흐름은 [[overview/hybrid-editing]]에 있다.
