# 배포 (Docker, 일반 Linux VM)

FastAPI 앱(`main:app`)과 pgvector(PostgreSQL) DB를 Docker Compose로 함께 띄운다.

| 서비스 | 이미지 | 역할 |
|---|---|---|
| `app` | 로컬 빌드(`Dockerfile`) | FastAPI 서버. Infisical CLI 로 LLM/HCX 시크릿 주입 후 uvicorn 기동 |
| `db`  | `pgvector/pgvector:pg16` | 임베딩 검색용 PostgreSQL. 최초 기동 시 `vector` 확장 자동 생성 |

## 구성 파일

- `Dockerfile` — uv + Infisical CLI 기반 앱 이미지
- `docker/entrypoint.sh` — `infisical run -- uv run uvicorn ...` (토큰 없으면 Infisical 생략)
- `docker-compose.yml` — app + db 스택
- `db/init/01-extensions.sql` — `CREATE EXTENSION vector` (DB 최초 1회)
- `.env.docker.example` — 배포 환경변수 템플릿

## 사전 준비 (VM)

- Docker Engine + Docker Compose plugin 설치
- 인바운드: 앱 포트(기본 8000)만 개방. DB 포트(5433)는 `127.0.0.1` 바인딩이라 외부 비노출

## 배포 절차

```bash
# 1) 코드 가져오기
git clone <repo> && cd fake-news-detector

# 2) 환경변수 작성 (시크릿 — 커밋 금지)
cp .env.docker.example .env.docker
#   INFISICAL_TOKEN : 배포 프로젝트+환경에 스코프된 서비스/머신 토큰
#   KOSIS_API_KEY   : KOSIS 키
#   POSTGRES_PASSWORD : 강한 비밀번호로 교체 + DATABASE_URL 의 비번도 일치시키기
vi .env.docker

# 3) 빌드 + 기동
docker compose --env-file .env.docker up -d --build

# 4) 상태 확인
docker compose --env-file .env.docker ps
curl http://localhost:8000/health        # {"status":"ok"}
```

## 시크릿 주입 (Infisical)

앱은 `infisical run --token=$INFISICAL_TOKEN -- uv run uvicorn main:app` 으로 기동되어
`CLOVASTUDIO_API_KEY`, `CLOVA_EMBEDDING_*` 등을 런타임에 주입받는다.

- `INFISICAL_TOKEN` 은 **서비스 토큰 또는 머신 아이덴티티 토큰**을 사용한다(대화형 로그인 불가).
- 토큰이 프로젝트/환경에 스코프되므로 컨테이너에서 `--env`/`--projectId` 를 따로 줄 필요는 없다.
- 토큰을 비워두면 Infisical 없이 기동된다(시크릿 미주입 — 로컬 점검용).

## pgvector 사용 (앱 연동은 추후)

현재 앱에는 DB 연동 코드가 없다. DB는 임베딩 검색을 위해 미리 띄워둔 상태다.

```bash
# 확장 설치 확인
docker compose --env-file .env.docker exec db \
  psql -U fnd -d fnd -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
```

앱 코드에서 연결할 때는 컨테이너 내부 DSN `postgresql://<user>:<pw>@db:5432/<db>` (= `DATABASE_URL`)을 쓴다.
호스트에서 직접 접속하려면 `localhost:5433` 을 사용한다.

> 참고: `db/init/*.sql` 은 **데이터 볼륨이 비어 있을 때만** 실행된다. 이미 만들어진
> `pgdata` 볼륨에 확장/스키마를 추가하려면 `psql` 로 수동 적용하거나 마이그레이션을 돌려야 한다.

## 운영 메모

- 로그: `docker compose --env-file .env.docker logs -f app`
- 재시작: `docker compose --env-file .env.docker restart app`
- 중지: `docker compose --env-file .env.docker down` (DB 데이터는 `pgdata` 볼륨에 보존)
- 데이터 포함 완전 삭제: `docker compose --env-file .env.docker down -v`
- **CORS**: `main.py` 의 `allow_origins` 가 `http://localhost:5174` 로 고정돼 있다.
  실제 프런트엔드 도메인으로 배포 시 이 값을 운영 도메인으로 바꿔야 한다.
