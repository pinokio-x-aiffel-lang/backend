# 보안 감사 보고서 — 2026-06-11

- **감사 대상**: 백엔드 `/Users/leeaain/project/pinokio-x/fake_news_detect`, 프론트엔드 `/Users/leeaain/project/pinokio-x/frontend`
- **감사 방식**: 정적 코드 분석(읽기 전용). 동적 실행·침투 테스트 미포함.
- **감사자**: Claude Code
- **검증 메모**: 에이전트 자동 탐색 결과를 직접 교차 검증함. 오탐 1건 정정(아래 §오탐 정정).

---

## 요약 (우선순위순)

| 우선순위 | 항목 | 심각도 | 위치 |
|---|---|---|---|
| 1 | API 키 git 히스토리 유출 (미해결) | 🔴 Critical | git 히스토리 blob `3daa981` |
| 2 | SSRF — 기사 URL 페칭 무검증 | 🔴 Critical | `src/modules/load_article.py` |
| 3 | JWT secret 기본값 하드코딩 | 🟠 High | `src/config.py:41` |
| 4 | SSE IDOR — job_id 무인증 구독 | 🟠 High | `frontend/src/hooks/useVerifySSE.ts:107` |
| 5 | JWT 토큰 localStorage 저장 | 🟠 High | `frontend/src/lib/api/token.ts` |
| 6 | 미처리 예외 원문 응답 노출 | 🟠 High | `src/api/chat_app.py:54-63` |
| 7 | CORS 와일드카드 methods/headers | 🟠 High | `main.py:63-69` |
| 8 | docker-compose DB 자격증명 기본값 | 🟠 High | `docker-compose.yml` |
| 9 | 프롬프트 인젝션(부분 완화) | 🟡 Medium | `src/modules/extract_statistical_claims.py:67` |
| 10 | 회원가입 409 사용자 열거 | 🟡 Medium | `src/auth/router.py:48-53` |
| 11 | rate-limit IP X-Forwarded-For 신뢰 | 🟡 Medium | `src/security.py:32-40` |
| 12 | 에러 메시지·BASE_URL UI 노출 | 🟡 Medium | `useVerifySSE.ts:123-131`, `client.ts:50-55` |

---

## 🔴 Critical

### 1. API 키 git 히스토리 유출 (미해결)
- 사건 기록: `docs/security/incident-2026-05-20-env-secret-leak.md`
- 직접 확인: 유출 blob `3daa981`이 로컬 object DB에 존재(`git cat-file -e 3daa981` 성공). 문서상 origin 레포에도 도달 가능.
- **영향**: 실제 OpenAI/Anthropic API 키가 히스토리에 영구 박힘 → 비용 폭증·쿼터 소진·무단 호출.
- **미완 조치**:
  - [ ] OpenAI/Anthropic 키 폐기 및 재발급 (우선순위 1)
  - [ ] origin 히스토리 재작성(`git filter-repo --path .env --invert-paths`) 후 force-push (팀 공지·조율)
  - [ ] 팀원 전원 re-clone 또는 hard reset
  - [ ] 로컬 object DB 정리(re-clone)
  - [ ] 시크릿은 Infisical에서만 관리

### 2. SSRF — 기사 URL 페칭 무검증
- 위치: `src/modules/load_article.py` (`_fetch_html` → `requests.get(url, ...)`)
- 사용자 제공 URL을 검증 없이 페칭. `allow_redirects=True` + 타임아웃만 설정, 내부 IP/메타데이터 차단 없음.
- **공격 시나리오**: `http://169.254.169.254/...`(클라우드 메타데이터), `http://localhost:5432/`, 사설 IP 페칭 → 내부망/크리덴셜 정보 유출. Render 등 클라우드 배포 시 실질 위협.
- **권장 수정**: `urllib.parse`+`ipaddress`로 loopback/link-local/private IP 차단, 가능하면 뉴스 도메인 화이트리스트.

---

## 🟠 High

### 3. JWT secret 기본값 하드코딩
- 위치: `src/config.py:41` — `jwt_secret_key: str = "change-me-in-production"`
- 환경변수 미설정 시 알려진 secret으로 토큰 위조 가능.
- **권장 수정**: 기본값 제거(빈 문자열) + 기동 시 미설정이면 `RuntimeError`로 fail-fast.

### 4. SSE IDOR — job_id 무인증 구독
- 위치: `frontend/src/hooks/useVerifySSE.ts:107` — `new EventSource(${BASE_URL}/verify/stream?job_id=${job_id})`
- EventSource는 Authorization 헤더를 못 실어 job_id만으로 구독. job_id를 알면 타인의 검증 진행/결과를 구독 가능(IDOR).
- **권장 수정(백엔드)**: job_id–사용자 바인딩 검증, HMAC 서명, 만료 시간.

### 5. JWT 토큰 localStorage 저장
- 위치: `frontend/src/lib/api/token.ts` — `localStorage.setItem('auth-token', ...)`
- XSS 발생 시 토큰 탈취. 현재 코드에 XSS 벡터는 없음(§양호 참고)이나 구조적 위험. 파일 주석에 위험 인지 기재돼 있음.
- **권장 수정**: httpOnly 쿠키(+CSRF 토큰) 또는 access token 메모리 보관 + refresh token 도입.

### 6. 미처리 예외 원문 응답 노출
- 위치: `src/api/chat_app.py:54-63` — `unhandled_exc_handler`가 `str(exc)`를 그대로 응답, validation 핸들러도 `str(exc.errors())` 전체 노출.
- 내부 구조·라이브러리 정보 유출.
- **권장 수정**: 로그에만 상세 기록, 사용자에는 일반 메시지.

### 7. CORS 와일드카드 methods/headers
- 위치: `main.py:63-69` — `allow_origins`는 화이트리스트(OK)이나 `allow_methods=["*"]`, `allow_headers=["*"]` + `allow_credentials=True`.
- **권장 수정**: 필요한 메서드/헤더만 명시(`["GET","POST","OPTIONS"]`, `["Content-Type","Authorization"]`).

### 8. docker-compose DB 자격증명 기본값
- 위치: `docker-compose.yml` — `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-fnd}` 등 `fnd:fnd` 기본값.
- `.env.docker`는 gitignore됨(OK)이나 기본값이 명시돼 있어 운영 배포 시 위험.
- **권장 수정**: 기본값 제거, 환경변수 필수화.

---

## 🟡 Medium

### 9. 프롬프트 인젝션 (부분 완화)
- 위치: `src/modules/extract_statistical_claims.py:67` — 기사 본문을 검증 없이 프롬프트에 삽입.
- JSON 파싱 + enum 검증으로 부분 완화. 단, LLM 출력이 무검증으로 UI까지 가는 경로(아래 §프론트 표시 버그 §1)가 있어 악성 기사로 UI 문구 조작 가능 → 수치 출력 검증 수정 필요.
- **권장 수정**: 입력 길이 제한, LLM 출력 형식 검증.

### 10. 회원가입 409 사용자 열거
- 위치: `src/auth/router.py:48-53` — 중복 아이디면 `409 "이미 사용 중인 아이디입니다."`, 없으면 `201`. 응답 차이로 계정 존재 여부 판별 가능.
- 단, `login`은 단일 admin만 인증하고 register로 만든 User는 login에 미사용이라 실제 위험도 낮음. login은 존재 여부 무관 `401` 통일(OK).
- **권장 수정**: register 미사용 시 라우트 비활성화, 사용 시 일반 응답 + rate limiting.

### 11. rate-limit IP X-Forwarded-For 신뢰
- 위치: `src/security.py:32-40` — `CF-Connecting-IP`/`X-Forwarded-For` 헤더 신뢰.
- Cloudflare 뒤면 안전. 그 외 프록시 구성에서 스푸핑 가능.
- **권장 수정**: 신뢰 프록시 CIDR 정책 명시.

### 12. 에러 메시지·BASE_URL UI 노출
- 위치: `frontend/src/hooks/useVerifySSE.ts:123-131`(SSE 에러 원문 표시), `frontend/src/lib/api/client.ts:50-55`(에러 메시지에 `BASE_URL` 노출).
- **권장 수정**: 프로덕션은 일반 메시지, 상세는 `import.meta.env.DEV`에서만.

---

## ✋ 오탐 정정
- 자동 탐색이 "프론트 `.env`가 git에 커밋됨(Critical)"으로 보고했으나, `git ls-files`·`git log --all -- .env` 확인 결과 **frontend/backend 모두 `.env`는 추적·히스토리에 없음**(`.env.example`만 커밋). Critical 아님.
- 다만 `frontend/.env`에 `KOSIS_API_KEY`가 들어 있음 — 프론트는 KOSIS를 직접 호출하지 않으므로 **이 키는 프론트 .env에서 제거 권장**(빌드 번들 유입 위험 제거).

## ✅ 양호 확인 항목
- 비밀번호 bcrypt 해싱(`src/auth/password.py`)
- SQLAlchemy 파라미터화 쿼리 — SQL injection 없음(`src/auth/database.py`, `models.py`)
- `eval`/`exec`/`pickle`/`subprocess`/`os.system` 미사용
- outbound HTTP TLS 검증 활성(`verify=False` 없음), 타임아웃 전부 설정(KOSIS·DART 30s, LLM 60s, article 15s)
- 프론트 `dangerouslySetInnerHTML`/`innerHTML` 미사용 — React 자동 이스케이프, LLM 텍스트도 평문 렌더
- 프론트 Zod 입력 검증, 의존성 최신(React 19, Vite 8 등)
- login 사용자 열거 방지(존재 여부 무관 401 통일)

---

## 부록 — 프론트 표시 버그 (별건, 본 감사 중 동시 조사)

사용자 신고("백엔드 출력이 프론트에 반영 안 됨")는 프론트 버그가 아니라 **백엔드 출력 자체의 문제**로 확인됨. 프론트(`ResultLayout.tsx:362`)는 `result.claim_value`를 무가공 렌더링.

1. **LLM 거절 문장이 "기사 속 수치"로 표시** — `src/modules/parse_korean_number.py:177-178`이 LLM 폴백 출력을 `text if text else None`로만 처리(숫자 형식 검증 없음). 빈 문자열 대신 설명 문장이 오면 그대로 통과. → 수치 형식 regex 검증 추가 필요.
2. **공식 통계 `—`/근거 0건** — KOSIS 조회가 실제 0건(API 키 미주입 또는 시점 정규화 실패 `fetch_kosis_data.py:283-284`).
3. **신뢰도 0%** — `src/modules/decide_verdict.py:49` confidence 산출이 TODO라 항상 0 전송.
4. **계약 갭** — `kosis_search.error_msg`·`needs_hitl` 등 실패 사유가 `src/api/verify.py:60-68` DTO에 없어 프론트가 사유 표시 불가.
