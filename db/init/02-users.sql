-- 자체 ID/PW 로그인 사용자 테이블.
-- 최초 DB 초기화 시 1회 실행된다.
CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    hashed_password TEXT NOT NULL,
    name            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
