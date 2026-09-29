---
title: 제어 표면 조사 방법과 결과
---
문서화되지 않은 서버 앱(WebProtégé 2019 이미지)을 안전하게 자동화하려고, 그 제어 표면을 추측이 아니라 사실로 확정하는 절차다. 결과 전체는 `references/control-surface.md`에 있다.

## 4단계 절차
```
1 엔드포인트 프로빙 → 2 JAR 디컴파일 → 3 라이브 DOM 실측 → 4 e2e 검증
```

### 1. 엔드포인트 프로빙
평문 HTTP 제어 표면이 있는지, 인증 없이 닿는 곳이 있는지 확인한다. `web.xml`에는 catch-all 필터뿐이라 라우팅은 필터 코드에서 찾는다. 판정 신호는 HTTP 상태 코드다: 200은 호스트 페이지, 404는 없음, 405는 메서드 불일치, 500(빈 본문)은 엔드포인트 존재, 400/403은 파라미터 오류나 인증 필요.

```
curl -s -o /dev/null -w "%{http_code}" <후보 경로>   # GET/POST 모두
```

### 2. JAR 디컴파일
인증 방식과 직렬화 구조를 코드에서 직접 확인한다. 컨테이너에서 JAR을 꺼내 CFR 0.152로 디컴파일하고, `*.gwt.rpc` 직렬화 정책에서 액션이 허용 목록에 있는지 grep한다.

- dispatch 경로는 `@RemoteServiceRelativePath` 값에서 읽는다.
- CHAP 수식은 `*DigestAlgorithm` 클래스에서 직접 읽는다.
- 커스텀 직렬화기 존재 여부는 `*CustomFieldSerializer` 클래스 목록으로 판단한다.

### 3. 라이브 DOM 실측
브라우저 자동화 셀렉터를 실제 렌더된 DOM에서 확정한다. Playwright로 페이지를 열고 GWT 렌더를 기다린 뒤, 보이는 버튼·입력·링크·헤딩을 덤프하고 스크린샷을 찍는다. 가입, 생성, 행 메뉴, 다운로드 다이얼로그마다 클릭과 덤프를 반복한다. 안정 클래스(`wp-*`)와 모달이 열렸을 때의 불변식(입력 개수 등)을 셀렉터 근거로 쓰고, 난독화 클래스는 피한다([[I005]]).

### 4. e2e 검증
기능을 말로 장담하지 않고 왕복으로 증명한다. 알려진 클래스가 든 `tiny.owl`로 create → list(존재 확인) → export(Turtle) → ZIP 내용에 클래스가 남았는지 확인한다. `test/e2e.js`(`npm test`)가 이를 자동화한다.

## 결과 요약
- REST가 없다. 모든 기능이 GWT-RPC 서블릿 `/webprotege/dispatchservice`의 `executeAction(Action)`으로 간다. 유일한 비-GWT 엔드포인트 `/download`도 세션 쿠키가 필요하므로 인증 없이 닿는 표면은 없다([[I001]]).
- 인증은 `GetChapSession` → `PerformLogin`의 MD5 기반 CHAP이다([[I002]]).
- `AvailableProject`, `ProjectDetails`, `NewProjectSettings`, 엔티티·프레임 타입 등이 커스텀 직렬화기를 가져, 직접 만든 클라이언트는 액션마다 직렬화기를 구현해야 한다([[I003]]).
- 그래서 헤드리스 브라우저로 앱 자체 JavaScript를 쓴다([[overview]]).
- `/download`는 리비전 디렉터리를 ZIP으로 준다([[I004]]).
- Project ▸ Apply External Edits(`MergeUploadedProjectActionHandler`)는 업로드 파일과 프로젝트 사이의 양방향 공리·어노테이션 diff를 새 리비전 하나로 커밋한다. Ontology IRI가 같아야 하고, 프로젝트 수준 `UPLOAD_AND_MERGE`와 `EDIT_ONTOLOGY` 권한이 필요하다([[I006]], [[I007]], [[overview/hybrid-editing]]).
- 가능한 빠른 경로: 브라우저로 한 번 로그인한 뒤 `JSESSIONID` 쿠키를 재사용해 `/download`를 평문 GET으로 호출하면 export만 할 때 브라우저 실행을 생략할 수 있다. 아직 구현하지 않았다([[S002]]).
