# Langfuse 시크릿 Infisical 주입 안내 (팀장님용)

Langfuse self-host 에 필요한 인프라 시크릿 11개를 Infisical `dev` 환경의
`/LangFuse` 폴더에 넣어주세요. (현재 제 계정은 읽기만 되고 쓰기 권한이 없어
직접 못 넣습니다.)

> 이 값들은 **외부 API 키가 아니라** Langfuse 스택 내부용 비밀번호(DB·캐시·
> 객체저장소 비번 + 인증/암호화 키)입니다. 그냥 무작위로 생성하면 됩니다.

## 방법 1) CLI 한 번에 (권장)

`infisical` 로그인 상태에서, 이 저장소 폴더(`.infisical.json` 있는 곳)에서
아래를 그대로 실행하세요. 시크릿을 자동 생성해서 `/LangFuse` 에 넣습니다.

**macOS / Linux (bash):**
```bash
PG=$(openssl rand -hex 16)
CH=$(openssl rand -hex 16)
RD=$(openssl rand -hex 16)
MN=$(openssl rand -hex 16)
SALT=$(openssl rand -base64 24)
ENC=$(openssl rand -hex 32)
NA=$(openssl rand -base64 32)

infisical secrets set --env dev --path /LangFuse \
  POSTGRES_PASSWORD="$PG" \
  DATABASE_URL="postgresql://postgres:$PG@postgres:5432/postgres" \
  CLICKHOUSE_PASSWORD="$CH" \
  REDIS_AUTH="$RD" \
  MINIO_ROOT_PASSWORD="$MN" \
  LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY="$MN" \
  LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY="$MN" \
  LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY="$MN" \
  SALT="$SALT" \
  ENCRYPTION_KEY="$ENC" \
  NEXTAUTH_SECRET="$NA"
```

**Windows (PowerShell):**
```powershell
function rnd-hex($n){ -join ((1..$n) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) }) }
$PG = rnd-hex 16
$CH = rnd-hex 16
$RD = rnd-hex 16
$MN = rnd-hex 16
$SALT = [Convert]::ToBase64String((1..24 | ForEach-Object { Get-Random -Max 256 }))
$ENC = rnd-hex 32
$NA  = [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Max 256 }))

infisical secrets set --env dev --path /LangFuse `
  POSTGRES_PASSWORD="$PG" `
  DATABASE_URL="postgresql://postgres:$PG@postgres:5432/postgres" `
  CLICKHOUSE_PASSWORD="$CH" `
  REDIS_AUTH="$RD" `
  MINIO_ROOT_PASSWORD="$MN" `
  LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY="$MN" `
  LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY="$MN" `
  LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY="$MN" `
  SALT="$SALT" `
  ENCRYPTION_KEY="$ENC" `
  NEXTAUTH_SECRET="$NA"
```

## 방법 2) Infisical 웹 UI

대시보드 → `dev` 환경 → `LangFuse` 폴더 → 아래 11개 키를 추가:

| 키 | 값 |
|----|----|
| `POSTGRES_PASSWORD` | 랜덤 (예: `openssl rand -hex 16`) |
| `DATABASE_URL` | `postgresql://postgres:<POSTGRES_PASSWORD>@postgres:5432/postgres` |
| `CLICKHOUSE_PASSWORD` | 랜덤 |
| `REDIS_AUTH` | 랜덤 |
| `MINIO_ROOT_PASSWORD` | 랜덤 |
| `LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY` | `MINIO_ROOT_PASSWORD` 와 **동일 값** |
| `LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY` | `MINIO_ROOT_PASSWORD` 와 **동일 값** |
| `LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY` | `MINIO_ROOT_PASSWORD` 와 **동일 값** |
| `SALT` | 랜덤 (`openssl rand -base64 24`) |
| `ENCRYPTION_KEY` | **정확히 64자 hex** (`openssl rand -hex 32`) |
| `NEXTAUTH_SECRET` | 랜덤 (`openssl rand -base64 32`) |

## 주의사항

- **`DATABASE_URL` 의 비번**은 `POSTGRES_PASSWORD` 와 반드시 같아야 합니다.
- **S3 secret 3개**는 모두 `MINIO_ROOT_PASSWORD` 와 같은 값이어야 합니다.
- **`ENCRYPTION_KEY` 는 한 번 정하면 절대 바꾸지 마세요.** 바꾸면 기존에
  암호화 저장된 데이터를 못 읽습니다. (반드시 64자 hex)
- 넣은 뒤, 제 계정(innnn)에 `/LangFuse` 폴더 **읽기 권한**이 있으면 됩니다
  (이미 읽기는 되는 상태).

## 완료 확인

```bash
infisical secrets --env dev --path /LangFuse
```
키 11개가 보이면 끝입니다. 그 다음은 제가
`infisical run --path /LangFuse -- docker compose ...` 로 Langfuse 를 띄웁니다.
