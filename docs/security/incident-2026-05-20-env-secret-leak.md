# 🔐 보안 이슈 리포트 — `.env` API 키 Git 히스토리 유출

| 항목 | 내용 |
|---|---|
| **이슈 ID** | SEC-2026-05-20-env-leak |
| **심각도** | 🔴 High (실제 API 키 유출) |
| **최초 발생일** | 2026-05-20 17:34 (KST) |
| **탐지일** | 2026-06-04 (product 레포 push 시 차단) |
| **현재 상태** | 진행 중 — ✅ product·origin(dev) 정리·push 완료 + `feature/table-embedding-search` 삭제 + 로컬 dev 정리 완료(2026-06-04) / ⛔ 키 폐기·팀 재동기화 공지·로컬 완전정리(re-clone) 미완 |
| **영향 레포** | `origin`(팀), `product`(배포) |

---

## 1. 요약 (TL;DR)

- 실제 **OpenAI / Anthropic API 키**가 든 `.env` 파일이 **2026-05-20** 커밋(`f809588`)에 섞여 들어가 git 히스토리에 영구히 박혔다.
- 이후 `.env`를 추적 해제(untrack)했지만, **과거 커밋의 블롭(`3daa981…`)은 그대로 남아** 있다.
- **`origin`(팀 저장소)** 에는 이미 올라가 있어 **유출 상태**다.
- **`product`(배포 레포)** 는 GitHub Push Protection이 막아줘서 **아직 깨끗**하다.
- 해결: ① **키 즉시 폐기·재발급** ② **히스토리 재작성으로 블롭 제거 후 push**. 단 재작성·force-push 과정에서 **팀원 push와 충돌** 가능성이 있어 조율이 필요하다.

---

## 2. 타임라인

| 시각 (KST) | 커밋 | 작성자 | 사건 |
|---|---|---|---|
| 2026-05-20 17:34 | `f809588` | leeaain2027 | **실제 키 든 `.env` 최초 커밋** (블롭 `3daa981`) |
| 2026-05-20 23:00 | `4e2cb23` | leeaain2027 | `.gitignore` 수정 (`.env` 여전히 추적 중) |
| 2026-05-21 14:54 | `df5d90e` | innnn | `.env` 추적 해제 — 트리에서는 사라짐, **히스토리엔 잔존** |
| 2026-05-21 15:47 | `d47d2fd` | innnn | dev 로 머지 |
| 2026-06-04 | — | — | `git push product dev` → **Push Protection 차단(GH013)**, 유출 탐지 |

> `.env`가 추적된 기간은 약 **21시간**이지만, 블롭은 한 번 커밋된 순간부터 **영구적**이다.

---

## 3. 원인

`.env`를 `.gitignore`에 추가하는 커밋에서, **정작 `.env` 파일 자체를 같이 커밋**해버렸다.
즉 ignore 처리 *전에* 이미 추적 상태로 올라갔고, 나중에 untrack해도 **과거 커밋에는 키가 든 블롭이 남는다.**

핵심 오해: "지금 트리에서 `.env`를 지웠으니 안전하다" → **틀림.** git은 과거 모든 커밋을 보존하므로, 과거 커밋을 직접 다시 쓰지 않는 한 키는 계속 도달 가능하다.

---

## 4. 노출된 시크릿 / 영향 범위

| | 값 |
|---|---|
| 노출 키 | **OpenAI API Key**(`.env:1`), **Anthropic API Key**(`.env:8`) |
| 문제 블롭 | `3daa981ace4381bc043623e1a5868cd0d1e9250d` (히스토리 내 유일 `.env` 버전) |
| 도달 가능 브랜치(origin) | `dev`, `feature/table-embedding-search` |

---

## 5. `.env`가 커밋에 섞이면 생기는 위험

- **무단 사용·과금**: 유출 키로 타인이 API 호출 → 비용 폭증·쿼터 소진.
- **영구성**: 파일을 지워도 과거 커밋/블롭은 **clone·fork·CI 캐시**에 남아 회수 불가.
- **통제 불가**: 한 번 push되면 누가 받아갔는지 알 수 없음 → 키는 **"이미 유출됐다"** 고 간주해야 함.
- **자동 수집**: 공개/외부 레포로 퍼지면 스캐너 봇이 **수초~수분 내** 키를 긁어 악용.
- → 그래서 "히스토리에서 지우기"보다 **키 폐기**가 먼저다.

---

## 6. 레포 비교 — 왜 `product`는 안전하고 `origin`은 위험한가

| | **origin** (팀 저장소) | **product** (배포 레포) |
|---|---|---|
| 시크릿 블롭 `3daa981` | ❌ **존재 (이미 유출)** | ✅ 없음 (깨끗) |
| 시크릿 커밋 `f809588` | 포함 (2개 브랜치) | 없음 |
| Push Protection | 미적용 → **그대로 통과** | **적용 → 차단** |
| 결과 | 키가 원격에 올라가 있음 | 키 유입 자체가 막힘 |

**product가 안전한 이유**
GitHub **Push Protection(secret scanning)** 이 켜져 있어, push되는 커밋에서 OpenAI/Anthropic 키 패턴을 감지하고 **GH013으로 거부**했다. 덕분에 블롭이 `product/dev`에 **도달하지 못했다.** 보호장치가 의도대로 작동한 것이다.

**origin이 위험한 이유**
Push Protection이 없어 블롭이 **그대로 올라가 있다.** `dev`와 `feature/table-embedding-search` 양쪽에서 도달 가능하고, 팀원들이 이미 clone했을 수 있으며 GitHub 캐시에도 남는다. 깨끗해 보이는 건 **최신 트리에만 `.env`가 없을 뿐**, 과거 커밋엔 살아 있다.

---

## 7. 중간에 팀원 push가 있어 강제 push를 못한 건

- 처음 `git push origin dev`가 **non-fast-forward**로 거부됨 → 로컬이 `origin/dev`보다 **77 커밋 뒤처져** 있었다(팀원 `innnn` 등이 먼저 push).
- 이때 **force-push는 위험**하다: force-push는 "내 커밋이 더 최신"인지와 **무관하게** 원격 ref를 통째로 덮어쓰므로, **내 로컬에 없는 팀원 커밋은 전부 소실**된다.
- 따라서 강제로 밀지 않고 **fetch → merge로 팀원 작업을 통합**한 뒤 진행해야 했다. (현재는 동기화 완료: `dev == origin/dev`.)
- 교훈: **재작성 + force-push 직전에는 반드시 최신 fetch + 팀 공지**가 선행돼야 한다.

---

## 8. 해결 방법 (상세)

### 8.0 즉시 — 키 폐기·재발급 (최우선, 필수)
이미 `origin`에 유출됐으므로 히스토리를 어떻게 고치든 **이미 나간 키는 못 주워담는다.**
→ **OpenAI / Anthropic 콘솔에서 두 키를 즉시 revoke 하고 재발급**, 새 키는 시크릿 매니저(Infisical 등)로만 주입.

### 8.1 "origin을 fresh mirror로 받는다"는 게 뭔가
```bash
git clone --mirror git@github.com:pinokio-x/fake-news-detector.git /tmp/fnd-purge.git
```
- **mirror clone** = 작업 트리 없이, 원격의 **모든 ref(브랜치·태그)와 git DB 전체**를 그대로 복제한 **bare 사본**.
- **fresh** = 내 실제 작업 폴더가 아닌, **새로 받은 깨끗한 사본**.
- **왜 쓰나**
  1. **비파괴적**: 내 실제 작업 저장소·`origin`을 전혀 건드리지 않고, 사본에서만 재작성·검증한다.
  2. **완전성**: 원본 그대로의 전체 히스토리를 받아 빠짐없이 정리한다.
  3. **안전**: 검증 통과한 정리본만 원격에 force-push하고, 잘못되면 **사본만 버리면 된다**(원본은 무사).

### 8.2 재작성 절차 (`git filter-repo`)
```bash
# 1) fresh mirror 복제 (8.1)
# 2) .env 를 전체 히스토리에서 제거
cd /tmp/fnd-purge.git
git filter-repo --path .env --invert-paths --force
# 3) 검증: 블롭이 어떤 ref에서도 도달 불가해야 함
git rev-list --objects --all | grep 3daa981ace4381bc043623e1a5868cd0d1e9250d   # 출력 없어야 정상
# 4) tip 트리가 원본과 동일한지(파일 손실 0) 확인
# 5) 원격에 force-push (아래 8.4 수칙 준수)
```

### 8.3 ⚠️ 이번에 발견한 주의점 — 단순 재작성 시 커밋 수 급감
- 기본 옵션으로 돌리니 **dev 커밋 160 → 87** 로 줄었다(merge가 얽힌 히스토리라 빈/중복 커밋이 정리됨).
- **검증 결과: tip 트리는 byte 단위로 동일(파일 손실 0), 시크릿 블롭은 완전 제거됨.** 하지만 `feat(dart)`, `feat(kosis)`, `feat(langfuse)` 등 **실제 작업 커밋 41개의 개별 이력이 collapse**됐다.
- **배포용 product**는 최종 결과물만 중요하므로 그대로도 무방하지만, **이력 보존이 필요하면** 다음으로 재실행:
  ```bash
  git filter-repo --path .env --invert-paths \
      --prune-empty never --prune-degenerate never --force
  ```
  이후 **커밋 수(≈160 유지)와 tip 트리 동일성**을 재검증한다.

### 8.4 force-push 안전 수칙 + 팀 조율
```bash
git fetch --all
git log --oneline origin/dev  --not dev   # 출력이 "비어야" 안전
git log --oneline product/dev --not dev   # 이것도 비어야 안전
```
- 둘 다 비어 있을 때만 무손실 force-push.
- 재작성은 **모든 커밋 SHA를 바꾸므로**, 진행 전 **팀원에게 "잠시 push 중단" 공지** → 완료 후 **전원 re-clone(또는 hard reset)**.

### 8.5 레포별 적용
| 레포 | 조치 |
|---|---|
| **product** | 정리본 `dev`를 force-push. `product/dev`엔 우리가 잃을 커밋이 0개라 안전. (bypass URL로 뚫지 말 것 — 그러면 product도 오염됨) |
| **origin** | `dev` **그리고** `feature/table-embedding-search` **둘 다** 재작성·force-push해야 블롭 완전 제거. 팀 전원 재동기화 필요. 단 이미 유출 + 키 폐기 시 무해해지므로, "지금 origin까지 갈아엎을지"는 disruption 대비 **선택**. |

---

## 9. 재발 방지

- `.env`는 **파일 생성 즉시 `.gitignore`에 먼저** 등록(추적 전에).
- **pre-commit 훅**으로 시크릿 스캔(gitleaks / trufflehog).
- **origin에도 Push Protection 활성화**(product처럼).
- 키는 코드/`.env`가 아니라 **시크릿 매니저**(Infisical 등)로만 관리.
- `.env.example`에는 **placeholder만**.

---

## 부록 — 검증 로그 (요약)

```
시크릿 블롭            : 3daa981ace4381bc043623e1a5868cd0d1e9250d (= f809588:.env)
product/dev 도달성     : ✅ 없음 (깨끗)
origin/dev 도달성      : ❌ 존재 (유출)
mirror 재작성 후       : ✅ 블롭 전 ref에서 제거, .env 만진 커밋 0개
tip 트리 비교          : a8edccb… == a8edccb…  (원본 == 정리본, 파일 손실 0)
커밋 수(기본 옵션)     : dev 160 → 87  (※ 8.3 참조, 이력 보존하려면 prune never 재실행)
커밋 수(prune never)   : dev 160 → 129 (감소분은 전부 byte-동일 중복/재중복 merge collapse, 고유 작업·파일 손실 0)
```

### product push 결과 (2026-06-04)
```
prune never 정리본 dev → product force-push : 6a8a6bd..229e8ee dev -> dev  (성공, GH013 차단 없음)
product/dev 시크릿 블롭 : ✅ 없음
product/dev tip 트리    : a8edccb… (== origin/dev, 파일 동일)
```

### 진행 경과 (2026-06-04)
- ✅ **로컬 dev 정리**: `git reset --hard product/dev` 로 정리본 적용 (160→129 커밋, dev에서 블롭 도달 불가).
- ✅ **origin/dev 재작성·force-push**: `1cd6304…229e8ee (forced update)`, origin/dev 블롭 도달 불가.
- ✅ **origin/feature/table-embedding-search 삭제**: 옛 dev(`1cd6304`)에 완전 포함된 브랜치(고유 커밋 0, tip `1447a1c`가 dev 조상)라 삭제로 블롭 제거. → **origin 전 브랜치 블롭 도달 불가 확인.**

### 남은 조치
- 🔴 **OpenAI / Anthropic 키 폐기·재발급** (이미 origin 유출, 필수·최우선 — git 정리로는 회수 불가).
- ⛔ **팀 재동기화 공지**: dev 히스토리 갈림 → 팀원 전원 `dev` re-clone 또는 hard reset(안 하면 옛 dev 재push로 블롭 부활).
- ⛔ **로컬 object DB 완전정리**: 옛 블롭이 reflog/타 브랜치 경유로 잔존 → 완전히 없애려면 re-clone.
