-- Google OAuth 로그인 사용자 테이블.
-- 최초 DB 초기화 시 1회 실행된다.
CREATE TABLE IF NOT EXISTS users (
    google_id  TEXT PRIMARY KEY,
    email      TEXT UNIQUE NOT NULL,
    name       TEXT,
    picture    TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
