---
title: 하이브리드 편집 흐름
---
LLM이 Turtle 원문을 고쳐 쓰게 하면 없는 IRI를 지어내거나 트리플을 빠뜨리거나 문법을 깨뜨리기 쉽다. 그래서 편집은 `onto`의 구조화된 명령으로 하고, 결과를 `wp apply-edits`로 WebProtégé 프로젝트에 새 리비전으로 반영한다.

## 흐름
1. 프로젝트에서 현재 온톨로지를 꺼낸다: `wp export <project> -F Turtle -o exp.zip` 후 압축 해제([[I004]]). Ontology IRI가 보존된다.
2. `onto` 명령으로 고친다: `add-class`, `add-subclass`, `add-objprop`, `add-dataprop`, `add-individual`, `add-annotation`, `add-disjoint`, `add-characteristic`, `add-inverse`, `remove`, `remove-subclass`. 각 명령은 참조하는 엔티티가 선언돼 있지 않으면 거부하고(exit 1, 파일 불변), 변경마다 다시 파싱하며, 저장할 때 Ontology IRI가 바뀌면 중단한다.
3. `onto validate [--reason]`로 파싱·구조 검사와 HermiT 일관성 검사를 한다([[I009]]).
4. `wp apply-edits <project> -f <file> -m <message>`로 반영한다. WebProtégé가 파일과 프로젝트의 차이(추가와 삭제 모두)를 계산해 새 리비전 하나로 커밋한다.
5. `onto diff <A> <B>`로 라운드트립 손실을 확인한다. A의 단언이 B에 없으면 exit 1이다([[I014]]).

## 제약
- 업로드 파일의 Ontology IRI가 프로젝트와 같고 익명이 아니어야 한다. 다르면 WebProtégé가 아무것도 반영하지 않는다([[I006]]). 이때 CLI는 0건 적용 경고를 낸다([[I010]]).
- Apply External Edits는 두 단계 다이얼로그이며 `wp apply-edits`가 둘 다 처리한다([[I007]]).
- WebProtégé는 트리플이 아니라 OWL 공리 단위로 diff한다. `add-disjoint`(2개면 `owl:disjointWith`, 3개 이상이면 `owl:AllDisjointClasses`), `add-characteristic`(functional, inverse-functional, transitive, symmetric, asymmetric, reflexive, irreflexive), `add-inverse`로 만든 공리는 apply-edits와 재export를 거쳐도 보존된다([[I013]]).
- WebProtégé 경계는 손실이 있다. `@`가 든 리터럴이 깨지고([[I008]]), RDF reification이 사라진다([[I014]]). 둘 다 export만 보면 정상처럼 보인다.

## 캐노니컬 파일 원칙
git에 둔 캐노니컬 온톨로지 파일이 진실원이다. 편집은 그 파일에 `onto`로 하고, `wp apply-edits`로 WebProtégé에 보기용으로 push만 한다. 새로 받은 `wp export`를 편집 베이스로 쓰지 않는다. export에서 시작해야 한다면 Turtle과 `onto` 새니타이저를 쓰고 이메일·자유 텍스트 필드를 확인한다. 상세한 손실 목록은 [[overview/strengthening]]에 있다.
