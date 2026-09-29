---
title: 실데이터 강화 조사 결과
---
장난감 fixture 대신 실제 규모의 온톨로지(필드테스트 대상인 PI 온톨로지: 199 KB, 2,064 트리플, 14 클래스, 약 240 class instance, object property 16개, data property 14개, reified provenance statement, 다국어 label, 이메일 연락처 리터럴)로 CLI를 돌려 깨지는 곳을 찾은 결과다. 각 발견은 재현했다.

다룬 범위: `wp create`/`wp export` 라운드트립, WebProtégé export와 캐노니컬 원본 양쪽에 대한 `onto info`/`query`/`validate --reason`/`add-*`/`remove`, 실제 규모의 `wp apply-edits`와 IRI 불일치 경우.

## 발견과 처리 상태

| # | 심각도 | 발견 | 처리 상태 |
|---|---|---|---|
| S1 | high | 라운드트립이 `@`가 든 리터럴(이메일)을 잘못된 언어 태그 리터럴로 바꾸고, 텍스트 중간의 이메일은 직렬화 구조를 깨뜨림 | 해결: 새니타이저가 단순·임베디드 모두 복구, 캐노니컬 파일 원칙 ([[I008]]) |
| S7 | high | 라운드트립이 RDF reification(`rdf:subject/predicate/object`)을 조용히 버려 provenance 어노테이션이 고아가 됨. 개수·파싱으로는 안 보이고 구조 set-diff로만 드러남 | 경고와 `onto diff`로 대응, 캐노니컬 파일 원칙 ([[I014]]) |
| S2 | med | `validate --reason`(HermiT)이 OWL 2 datatype map 밖의 타입(`xsd:gYear` 등)에서 중단 | 해결: 지원 안 되는 datatype 자동 완화 후 재시도 ([[I009]]) |
| S3 | med | IRI가 다른 파일로 `apply-edits`하면 0건 적용하고 exit 0 | 해결: 0건이면 경고 ([[I010]]). 업로드 전 IRI 비교는 미구현 |
| S4 | low | `onto info`가 `owl:NamedIndividual`만 세어 `a :Class`로 선언된 개체를 빠뜨림 | 해결: class instance 수도 출력 ([[I011]]) |
| S5 | low | reified statement의 `rdf:subject/object`인 엔티티를 `onto remove`하면 `rdf:Statement` blank node가 고아로 남음 | 보류: `--prune-reification` 후보 ([[I012]]) |
| S6 | low | 브라우저 작업이 실 온톨로지에서 9–15초 걸림. 고정 `waitForTimeout`은 2,000 트리플에서는 충분했으나 더 크거나 느린 인스턴스에 대한 여유가 없음 | 계획: 상태 기반 대기(예: merge preview 변경 목록 대기) |

## 대응 원칙
- WebProtégé와의 경계는 설계상 손실이 있다(RDF와 OWL이 1:1이 아님). 손실을 하나씩 막는 대신, 어떤 손실도 모르고 지나가지 않게 한다. `onto diff <A> <B>`는 blank node 없는 트리플을 정확히 비교하고 blank node 구조(reification, list, restriction)를 predicate별 개수로 비교하며 reification을 따로 검사한다. A의 단언이 B에 없으면 exit 1이다. 새니타이저가 놓친 `@` 손상도 잡는다.
- 캐노니컬 파일이 진실원이고 WebProtégé는 보기 전용이다([[overview/hybrid-editing]]). 이 원칙을 지키면 경계의 손실이 데이터에 영향을 주지 않는다.
- 새니타이저는 안전망이지 정식 경로가 아니다.
- 파일 → WebProtégé 방향(push)은 실제 규모에서 견고하다.

남은 후보(`owl:Axiom` 인코딩, `validate --profile owlapi-safe`, push 뒤 자동 diff, S3 사전 IRI 비교, S5, S6)는 [[S002]]의 완료 조건에 있다.
