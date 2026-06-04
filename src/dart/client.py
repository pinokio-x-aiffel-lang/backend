"""OpenDART API 호출.

requests + 상태코드 검증. JSON 엔드포인트(list, fnlttSinglAcntAll)와
바이너리 엔드포인트(corpCode.xml, document.xml = zip)를 분리해 다룬다.

OpenDART status 코드: 000=정상, 013=조회된 데이터 없음(정상적 '없음'),
010=미등록키, 020=요청한도초과, 100=필드값오류, 901=만료된 계정.
013 은 에러가 아니라 "없음" 이므로 raise 하지 않고 호출부가 판단한다.
(KOSIS client 는 urllib 을 쓰지만, 이 모듈은 요청대로 requests 사용 +
 zip/바이너리 응답 처리가 편하다.)
"""
from __future__ import annotations

import io
import zipfile

import requests

BASE_URL = "https://opendart.fss.or.kr/api"

# raise 하지 않고 호출부로 넘기는 정상 상태코드.
_OK_STATUS = {"000", "013"}


class DartError(Exception):
    """OpenDART 호출 실패 또는 응답 비정상."""


def call_dart(path: str, params: dict, timeout: float = 30.0) -> dict:
    """JSON 엔드포인트 호출 → 파싱된 dict 반환.

    status 가 000/013 이면 그대로 반환(013 = 데이터 없음, 호출부가 처리).
    그 외 status(010/020/100/901 등)는 DartError.

    Raises:
        DartError: HTTP non-200, JSON 파싱 실패, 또는 에러 상태코드.
    """
    url = f"{BASE_URL}/{path}"
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise DartError(f"호출 실패: {e}") from e

    if resp.status_code != 200:
        raise DartError(f"HTTP {resp.status_code}: {resp.text[:500]}")

    try:
        data = resp.json()
    except ValueError as e:
        raise DartError(f"JSON 파싱 실패: {e}; 원본 앞 500자: {resp.text[:500]}") from e

    status = data.get("status")
    if status not in _OK_STATUS:
        raise DartError(f"OpenDART status={status}: {data.get('message')}")
    return data


def fetch_zip_xml(path: str, params: dict, timeout: float = 60.0) -> bytes:
    """zip 응답(corpCode.xml, document.xml) 호출 → 첫 XML 파일 bytes 반환.

    에러 시 OpenDART 는 zip 대신 JSON/XML 에러 본문을 주므로, zip 시그니처
    (PK)로 판별해 에러면 DartError.

    Raises:
        DartError: HTTP non-200, zip 이 아닌 에러 응답, 또는 zip 파싱 실패.
    """
    url = f"{BASE_URL}/{path}"
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise DartError(f"호출 실패: {e}") from e

    if resp.status_code != 200:
        raise DartError(f"HTTP {resp.status_code}: {resp.text[:500]}")

    raw = resp.content
    if raw[:2] != b"PK":
        raise DartError(f"zip 응답 아님 (에러?): {raw[:500]!r}")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        return zf.read(zf.namelist()[0])
    except (zipfile.BadZipFile, IndexError) as e:
        raise DartError(f"zip 파싱 실패: {e}") from e
