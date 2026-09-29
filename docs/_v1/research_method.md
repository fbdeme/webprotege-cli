# Investigation Method — 제어 표면 리버스 엔지니어링

> 최종 업데이트: 2026-06-26
> 버전: v1.0 (초기 — 디컴파일+프로빙 절차 확립)

문서화되지 않은 서버 앱(여기선 WebProtégé 2019 이미지)을 안전하게 자동화하기 위해, 그 제어
표면을 **추측이 아니라 사실로** 확정하는 절차. (산출물: `references/control-surface.md`)

---

## 전체 파이프라인 개요

```
Stage 1: 엔드포인트 프로빙 → Stage 2: JAR 디컴파일 → Stage 3: 라이브 DOM 실측 → Stage 4: e2e 검증
```

---

## Stage 1: 엔드포인트 프로빙 (HTTP 표면)

### 설계 목표

비-GWT(평문 HTTP) 제어 표면이 있는지, 인증 없이 닿는 게 있는지 확정.

### 핵심 결정

| # | 요소 | 채택안 | 이유 |
|---|---|---|---|
| 1 | 라우팅 출처 | `web.xml` 대신 필터 코드 | web.xml은 catch-all 필터뿐 |
| 2 | 판정 신호 | HTTP 코드 (404 vs 500 vs 403) | 404=없음, 500=존재(빈 body), 403=인증 필요 |

### 절차

```
curl -s -o /dev/null -w "%{http_code}" <후보경로>   # GET/POST 양쪽
# 200=호스트페이지, 404=오답, 405=메서드, 500=엔드포인트 존재, 400/403=파라미터/인증
```

---

## Stage 2: JAR 디컴파일 (인증·직렬화 사실 확정)

### 설계 목표

인증 방식과 직렬화 구조를 코드에서 직접 확인 (CHAP 수학, 액션 핸들러 존재, 커스텀 직렬화기).

### 절차 (vN)

```
docker cp <container>:.../WEB-INF/lib/<jar> ./x.jar
unzip -o x.jar '<pkg>/**' -d ext
java -jar cfr.jar ext/<path>/<Class>.class       # CFR 0.152
# 정책 화이트리스트 확인:
docker exec <c> grep -l <Action> .../webprotege/*.gwt.rpc
```

### 핵심 산출

- dispatch 경로 = `@RemoteServiceRelativePath` 값.
- CHAP 수학 = `*DigestAlgorithm` 클래스에서 직독.
- 커스텀 직렬화기 존재 여부 = `*CustomFieldSerializer` 클래스 목록.

---

## Stage 3: 라이브 DOM 실측 (셀렉터 grounding)

### 설계 목표

브라우저 자동화 셀렉터를 **추측 없이** 실제 렌더된 DOM에서 확정.

### 절차

- Playwright로 페이지 로드 → GWT 렌더 대기 → 보이는 버튼/입력/링크/헤딩 덤프 + 스크린샷.
- 각 상호작용(가입 다이얼로그, 생성 다이얼로그, 행 메뉴, 다운로드 다이얼로그)마다 클릭→덤프 반복.
- 안정 클래스(`wp-*`)와 불변식(모달 오픈 시 입력 개수 등)을 셀렉터 근거로 채택. 난독화 클래스는 회피.

---

## Stage 4: e2e 검증 (왕복)

### 설계 목표

"보고 전 반드시 검증" — 기능을 말로 장담하지 않고 왕복으로 증명.

### 절차

```
tiny.owl(알려진 클래스) → create → list(존재 확인) → export(Turtle) → ZIP 내용에 클래스 보존 확인
```

`test/e2e.js` = `npm test`로 자동화.

---

## 변경 이력

| 버전 | 날짜 | 변경 |
|---|---|---|
| v1.0 | 2026-06-26 | 4-stage 절차 확립 (프로빙→디컴파일→DOM 실측→e2e) |
