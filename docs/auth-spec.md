# 인증/로그인 API 합의 스펙 (프론트 ↔ 백엔드)

> 프론트엔드가 **이미 구현해 둔** 동작 기준으로 작성. 백엔드는 이 형태에 맞춰 주세요.
> 다른 형태가 좋다면 "합의 필요 항목"(맨 아래)에서 같이 정합니다.

---

## 0. 결정 요약

| 항목 | 결정 |
|---|---|
| 로그인 방식 | **아이디(`user_id`) + 비밀번호** (이메일 로그인 아님) |
| 토큰 전달 | **httpOnly 쿠키** (응답 body로 토큰 주지 않음) |
| 배포 형태 | **교차 사이트(cross-site)** 확정 — 같은 사이트로 못 묶음 |
| 쿠키 속성 | `HttpOnly; Secure; SameSite=None; Path=/` |
| CSRF 방어 | **double-submit 토큰** (SameSite=None이라 필수) |
| 비밀번호 저장 | **bcrypt / argon2 해싱** (평문 저장·로그 금지) |

---

## 1. 배포 토폴로지 (교차 사이트)

```
프론트  https://pinokiox-frontend.onrender.com   (정적 사이트)
백엔드  https://backend-1-hbvq.onrender.com       (web service)
```

- `onrender.com`은 Public Suffix List에 등록 → **서로 다른 서브도메인 = 다른 사이트(cross-site)**.
- 따라서 쿠키는 **`SameSite=None; Secure`** 여야 교차 사이트 요청에 전송됨. (`Lax/Strict`는 전송 안 됨)
- `SameSite=None`은 CSRF 자동 방어가 없으므로 **CSRF 토큰을 별도로 둠**(§4).
- (실제 배포 도메인이 다르면 알려주세요 — CORS 허용 origin을 그 값으로 맞춰야 함)

---

## 2. 엔드포인트

### 2-1. `POST /auth/login`

요청:
```http
POST /auth/login
Content-Type: application/json
X-CSRF-Token: <csrf 쿠키 값>      # csrf 쿠키가 있을 때만 (§4)

{ "user_id": "hong123", "password": "********" }
```

성공 응답 (200) — **토큰은 body에 넣지 말고 Set-Cookie로**:
```http
HTTP/1.1 200 OK
Set-Cookie: access_token=<JWT>; HttpOnly; Secure; SameSite=None; Path=/; Max-Age=3600
Set-Cookie: refresh_token=<JWT>; HttpOnly; Secure; SameSite=None; Path=/auth; Max-Age=1209600
Set-Cookie: csrf_token=<random>; Secure; SameSite=None; Path=/        # HttpOnly 아님(프론트가 읽어야 함)
Content-Type: application/json

{ "user": { "id": 1, "user_id": "hong123", "name": "홍길동" } }
```

- body는 `{ "user": {...} }` 만. `name`은 선택.
- 실패 응답:
  - `401` — 아이디/비밀번호 불일치 (**아이디 존재 여부를 구분하지 말 것**, §5)
  - `422` — 입력 형식 오류

### 2-2. `GET /auth/me`  ← 로그인 상태 확인용 (중요)

httpOnly 쿠키는 **프론트 JS가 못 읽으므로**, "지금 로그인돼 있나?"를 이 엔드포인트로 판단합니다.

```http
GET /auth/me            # 브라우저가 access_token 쿠키 자동 첨부
```
- 쿠키 유효 → `200 { "id": 1, "user_id": "hong123", "name": "홍길동" }`
- 쿠키 없음/만료 → `401`

### 2-3. `POST /auth/logout`

httpOnly 쿠키는 프론트가 못 지우므로 **백엔드가 만료시켜야** 합니다.
```http
POST /auth/logout
X-CSRF-Token: <csrf 쿠키 값>
```
- 응답: `200 { "ok": true }` + `Set-Cookie`로 access/refresh/csrf 쿠키 **만료(Max-Age=0)**.
- ⚠️ **204(No Content) 말고 JSON body**(`{}` 이상)를 주세요. 프론트 공통 `apiFetch`가 `res.json()`을 호출해서 빈 본문이면 에러납니다.

### 2-4. `POST /auth/refresh` (권장)

access token 만료 시 refresh 쿠키로 재발급.
```http
POST /auth/refresh      # refresh_token 쿠키 자동 첨부
```
- 성공 → `200 { "ok": true }` + 새 `access_token` 쿠키 Set-Cookie (가능하면 refresh도 회전).
- 실패 → `401` (재로그인 필요).

---

## 3. CORS 설정 (교차 사이트라 필수)

쿠키를 주고받으려면 백엔드 응답에 다음이 **반드시** 있어야 합니다:

```http
Access-Control-Allow-Origin: https://pinokiox-frontend.onrender.com   # 정확한 origin (와일드카드 * 불가)
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
```

- `Allow-Credentials: true`일 때 `Allow-Origin`에 `*` 사용 불가 → **정확한 origin 반사**.
- preflight(`OPTIONS`) 요청에도 위 헤더 응답 필요.
- (FastAPI면 `CORSMiddleware(allow_origins=[프론트URL], allow_credentials=True, allow_methods=[...], allow_headers=["Content-Type","X-CSRF-Token"])`)

---

## 4. CSRF (double-submit) 흐름

`SameSite=None`이라 CSRF 토큰이 필요합니다. 프론트는 아래 흐름을 **이미 구현**해 뒀습니다:

1. 백엔드가 **읽기 가능한**(HttpOnly 아님) `csrf_token` 쿠키를 내려줌 (로그인 시 또는 별도 `GET /auth/csrf`).
2. 프론트가 상태 변경 요청(POST 등) 시 그 값을 `X-CSRF-Token` 헤더에 실어 보냄.
3. 백엔드가 **헤더 값 == 쿠키 값**인지 비교해서 다르면 거부(403).

→ 공격 사이트는 피해자의 `csrf_token` 쿠키 **값을 읽을 수 없어**(다른 origin) 헤더를 못 맞춤 → CSRF 차단.

> 백엔드가 CSRF를 다른 방식으로 처리하고 싶으면(예: Origin/Referer 검증) 알려주세요. 프론트는 csrf 쿠키가 없으면 헤더를 안 붙이므로 무해합니다.

---

## 5. 백엔드 보안 책임 (프론트가 못 하는 것)

- **Rate limiting / brute-force 방어** — 로그인 IP·계정별 시도 제한, N회 실패 시 지연·잠금. (credential stuffing 방어)
- **사용자 열거(enumeration) 방지** — "없는 아이디"와 "틀린 비밀번호"를 **동일한 401 + 동일 메시지 + 비슷한 응답시간**으로. (프론트는 401을 "아이디 또는 비밀번호가 올바르지 않아요"로 고정 표시)
- **비밀번호 해싱** — bcrypt 또는 argon2. 평문 저장·로그 절대 금지.
- **토큰** — access는 짧게(예: 1시간), refresh로 갱신, 로그아웃 시 무효화. 가능하면 refresh 회전(rotation).
- **HTTPS 강제**, 민감정보(비번/토큰) 로그 금지.

---

## 6. 프론트엔드가 이미 맞춰 둔 동작 (참고: `src/lib/api/auth.ts`)

- 모든 인증 요청에 `credentials: 'include'` → 쿠키 자동 송수신.
- `csrf_token` 쿠키가 있으면 `X-CSRF-Token` 헤더로 반송.
- 토큰을 **localStorage 등에 저장하지 않음** (httpOnly 쿠키에 위임).
- 로그인 상태는 `GET /auth/me`로 확인.
- 기대 응답 스키마: `login`/`me` → `user { id, user_id, name? }`.

---

## 7. 합의 필요 항목 체크리스트

- [ ] 실제 배포 도메인 확정 (CORS `Allow-Origin` 값)
- [ ] access token 만료 시간 / refresh token 도입 여부
- [ ] CSRF 방식: double-submit(현재 가정) vs Origin·Referer 검증
- [ ] `user_id` 규칙 (길이·허용 문자) — 프론트 추가 검증 필요 시
- [ ] 응답 `user` 필드 확정 (`id` 타입, `name` 포함 여부, 추가 필드)
- [ ] 엔드포인트 경로 확정 (`/auth/login`, `/auth/me`, `/auth/logout`, `/auth/refresh`)
