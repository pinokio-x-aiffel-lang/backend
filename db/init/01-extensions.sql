-- pgvector 확장 활성화.
-- 이 스크립트는 DB 데이터 디렉터리가 비어 있는 "최초 초기화" 시 1회만 실행된다.
-- (이미 초기화된 볼륨에는 다시 실행되지 않음 → 확장 추가는 수동 마이그레이션 필요)
CREATE EXTENSION IF NOT EXISTS vector;
