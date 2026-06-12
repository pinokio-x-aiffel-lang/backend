# 260610_1-10_full-pipeline_leeaain

### 1. 테스트 목적
문장 1개를 넣어 runner.py 전체 파이프라인([1]~[10])이 끝까지 동작하고 verdict·설명을 산출하는지 확인.
### 2. 검증 대상 모듈
- src/pipeline/runner.py (Pipeline) + src/modules/* [1]~[10] 전 단계
### 3. 도구로만 쓰인 모듈
- 없음 (Pipeline().run 직접 호출)
### 4. 일자 / 작성자
- 2026-06-10 / leeaain

### 5. 결과 · 원자료: 260610_1-10_full-pipeline_leeaain.json
- 입력 문장: **지난해(2023년) 북한의 경제성장률은 1.4%에 그쳤다.**
- overall_verdict: **N**

**추출 claims**

| 유형 | subject | population | 값(raw→정규화) | 시점 |
|---|---|---|---|---|
| absolute | 경제성장률 | 북한 | 1.4%→1.4 | Y:2023 |

**검증 결과**

| verdict | 주장값 | KOSIS값 | 표 | 설명 |
|---|---|---|---|---|
| N | 1.4 | 1.6 | 경제성장률(시도) | 2023년 경제성장률에 대한 KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다. |


---

# 단계별 기록 (각 단계가 채운 부분)

## 1. 기사 내용 확인

- **article.article_id**: art-0001
- **article.title**: None
- **article.content**: 지난해(2023년) 북한의 경제성장률은 1.4%에 그쳤다.
- **article.published_at**: 2025-04
- **article.source**: None
- **article.url**: None

## 2. 클레임 추출

- **claims[0].claim_id**: clm-0001
- **claims[0].article_id**: art-0001
- **claims[0].sentence**: 지난해(2023년) 북한의 경제성장률은 1.4%에 그쳤다.
- **claims[0].claim_type**: ClaimType.ABSOLUTE
- **claims[0].subject**: 경제성장률
- **claims[0].value.raw**: 1.4%
- **claims[0].value.llm_value**: 
- **claims[0].value.is_inferred**: False
- **claims[0].unit**: %
- **claims[0].aggregation**: 값
- **claims[0].period_type**: Y
- **claims[0].period_value.raw**: 2023년
- **claims[0].period_value.llm_value**: 
- **claims[0].period_value.is_inferred**: False
- **claims[0].compare_period_value**: None
- **claims[0].compare_conquer**: None
- **claims[0].population**: 북한
- **claims[0].cited_source**: 불명

## 3. 한국어 수사 산술로 변환

- **claims[0].value.llm_value**:  → 1.4
- **claims[0].period_value.llm_value**:  → 2023

## 4. KOSIS 통계표 n개 찾기

- **analysis[0].claim_id**: clm-0001
- **analysis[0].kosis_search.api**: statisticsSearch.do
- **analysis[0].kosis_search.query**: 경제성장률
- **analysis[0].kosis_search.params**: {"method": "getList", "searchNm": "경제성장률", "startCount": "1", "resultCount": "10", "sort": "RANK", "format": "json"}
- **analysis[0].kosis_search.hits**: 10
- **analysis[0].kosis_search.selected_tbl_id**: DT_2KAA905
- **analysis[0].kosis_search.selected_tbl_name**: 경제성장률(불변가격)
- **analysis[0].kosis_search.success**: 1
- **analysis[0].kosis_search.error_msg**: None
- **analysis[0].kosis_search.duration_ms**: 214
- **analysis[0].candidates[0].org_id**: 101
- **analysis[0].candidates[0].tbl_id**: DT_2KAA905
- **analysis[0].candidates[0].tbl_nm**: 경제성장률(불변가격)
- **analysis[0].candidates[0].org_nm**: 국가데이터처
- **analysis[0].candidates[0].stat_nm**: 국제통계연감
- **analysis[0].candidates[0].prd_de**: 1961~2024
- **analysis[0].candidates[1].org_id**: 388
- **analysis[0].candidates[1].tbl_id**: TX_38803_A026
- **analysis[0].candidates[1].tbl_nm**: 연도별 전력수급 실적
- **analysis[0].candidates[1].org_nm**: 한국전력거래소
- **analysis[0].candidates[1].stat_nm**: 발전설비현황
- **analysis[0].candidates[1].prd_de**: 2002~2024
- **analysis[0].candidates[2].org_id**: 101
- **analysis[0].candidates[2].tbl_id**: DT_XNS0110
- **analysis[0].candidates[2].tbl_nm**: 경제성장률(불변가격) - 남부·동남아시아
- **analysis[0].candidates[2].org_nm**: 국가데이터처
- **analysis[0].candidates[2].stat_nm**: 신남방신북방통계
- **analysis[0].candidates[2].prd_de**: 1961~2024
- **analysis[0].candidates[3].org_id**: 101
- **analysis[0].candidates[3].tbl_id**: DT_XNN0110
- **analysis[0].candidates[3].tbl_nm**: 경제성장률(불변가격) - 동북·중앙아시아
- **analysis[0].candidates[3].org_nm**: 국가데이터처
- **analysis[0].candidates[3].stat_nm**: 신남방신북방통계
- **analysis[0].candidates[3].prd_de**: 1961~2024
- **analysis[0].candidates[4].org_id**: 101
- **analysis[0].candidates[4].tbl_id**: DT_1YL20571
- **analysis[0].candidates[4].tbl_nm**: 경제성장률(시도)
- **analysis[0].candidates[4].org_nm**: 국가데이터처
- **analysis[0].candidates[4].stat_nm**: e-지방지표
- **analysis[0].candidates[4].prd_de**: 2016~2024
- **analysis[0].candidates[5].org_id**: 301
- **analysis[0].candidates[5].tbl_id**: DT_200Y123
- **analysis[0].candidates[5].tbl_nm**: 경제활동별 성장기여도(계절조정, 실질, 분기)
- **analysis[0].candidates[5].org_nm**: 한국은행
- **analysis[0].candidates[5].stat_nm**: 국민계정
- **analysis[0].candidates[5].prd_de**: 1960~2026
- **analysis[0].candidates[6].org_id**: 301
- **analysis[0].candidates[6].tbl_id**: DT_200Y124
- **analysis[0].candidates[6].tbl_nm**: 경제활동별 성장기여도(원계열, 실질, 분기 및 연간)
- **analysis[0].candidates[6].org_nm**: 한국은행
- **analysis[0].candidates[6].stat_nm**: 국민계정
- **analysis[0].candidates[6].prd_de**: 1954~2026
- **analysis[0].candidates[7].org_id**: 101
- **analysis[0].candidates[7].tbl_id**: DT_2UNS0080
- **analysis[0].candidates[7].tbl_nm**: 성별 연령별 실업률
- **analysis[0].candidates[7].org_nm**: 국가데이터처
- **analysis[0].candidates[7].stat_nm**: UN
- **analysis[0].candidates[7].prd_de**: 2000~2024
- **analysis[0].candidates[8].org_id**: 101
- **analysis[0].candidates[8].tbl_id**: DT_2UNS0216
- **analysis[0].candidates[8].tbl_nm**: 경제 활동에 참여하는 아동 비율
- **analysis[0].candidates[8].org_nm**: 국가데이터처
- **analysis[0].candidates[8].stat_nm**: UN
- **analysis[0].candidates[8].prd_de**: 2010~2023
- **analysis[0].candidates[9].org_id**: 101
- **analysis[0].candidates[9].tbl_id**: DT_XNN0050
- **analysis[0].candidates[9].tbl_nm**: 인간개발지수 - 동북·중앙아시아
- **analysis[0].candidates[9].org_nm**: 국가데이터처
- **analysis[0].candidates[9].stat_nm**: 신남방신북방통계
- **analysis[0].candidates[9].prd_de**: 1990~2023
- **analysis[0].kosis_query.api**: statisticsData.do
- **analysis[0].kosis_query.tbl_id**: 
- **analysis[0].kosis_query.params**: 
- **analysis[0].kosis_query.rows_returned**: 0
- **analysis[0].kosis_query.success**: 0
- **analysis[0].kosis_query.error_msg**: None
- **analysis[0].kosis_query.duration_ms**: 0

## 5. KOSIS 셀 값 조회

- **analysis[0].cell_attempts[0].tbl_id**: DT_2KAA905
- **analysis[0].cell_attempts[0].tbl_nm**: 경제성장률(불변가격)
- **analysis[0].cell_attempts[0].matched**: False
- **analysis[0].cell_attempts[0].value**: None
- **analysis[0].cell_attempts[0].unit**: None
- **analysis[0].cell_attempts[0].itm_id**: T10
- **analysis[0].cell_attempts[0].items[0]**: 경제성장률(기준년가격 GDP)
- **analysis[0].cell_attempts[0].axes.국가별[0]**: 세계
- **analysis[0].cell_attempts[0].axes.국가별[1]**: 아시아
- **analysis[0].cell_attempts[0].axes.국가별[2]**: 대한민국
- **analysis[0].cell_attempts[0].axes.국가별[3]**: 아프가니스탄
- **analysis[0].cell_attempts[0].axes.국가별[4]**: 아르메니아
- **analysis[0].cell_attempts[0].axes.국가별[5]**: 아제르바이잔
- **analysis[0].cell_attempts[0].axes.국가별[6]**: 바레인
- **analysis[0].cell_attempts[0].axes.국가별[7]**: 방글라데시
- **analysis[0].cell_attempts[0].axes.국가별[8]**: 부탄
- **analysis[0].cell_attempts[0].axes.국가별[9]**: 브루나이
- **analysis[0].cell_attempts[0].axes.국가별[10]**: 캄보디아
- **analysis[0].cell_attempts[0].axes.국가별[11]**: 중국
- **analysis[0].cell_attempts[0].axes.국가별[12]**: 키프로스
- **analysis[0].cell_attempts[0].axes.국가별[13]**: 조지아
- **analysis[0].cell_attempts[0].axes.국가별[14]**: 홍콩
- **analysis[0].cell_attempts[0].axes.국가별[15]**: …외 226개
- **analysis[0].cell_attempts[0].population_fallback**: False
- **analysis[0].cell_attempts[0].match_source**: rule
- **analysis[0].cell_attempts[0].error**: 셀 조회 실패: 30: 데이터가 존재하지 않습니다.
- **analysis[0].cell_attempts[1].tbl_id**: TX_38803_A026
- **analysis[0].cell_attempts[1].tbl_nm**: 연도별 전력수급 실적
- **analysis[0].cell_attempts[1].matched**: False
- **analysis[0].cell_attempts[1].value**: None
- **analysis[0].cell_attempts[1].unit**: None
- **analysis[0].cell_attempts[1].itm_id**: None
- **analysis[0].cell_attempts[1].items[0]**: 연도별 전력수급 실적
- **analysis[0].cell_attempts[1].axes.실적구분별[0]**: 경제성장률
- **analysis[0].cell_attempts[1].axes.실적구분별[1]**: 설비용량(연말)
- **analysis[0].cell_attempts[1].axes.실적구분별[2]**: 설비용량(연말)-성장률
- **analysis[0].cell_attempts[1].axes.실적구분별[3]**: 최대전력
- **analysis[0].cell_attempts[1].axes.실적구분별[4]**: 최대전력-성장률
- **analysis[0].cell_attempts[1].axes.실적구분별[5]**: 설비예비율
- **analysis[0].cell_attempts[1].axes.실적구분별[6]**: 공급예비율
- **analysis[0].cell_attempts[1].axes.실적구분별[7]**: 총발전량
- **analysis[0].cell_attempts[1].axes.실적구분별[8]**: 총발전량-성장률
- **analysis[0].cell_attempts[1].axes.실적구분별[9]**: 이용률
- **analysis[0].cell_attempts[1].axes.실적구분별[10]**: 발전소내 소비전력률
- **analysis[0].cell_attempts[1].axes.실적구분별[11]**: 발전소내 소비전력량
- **analysis[0].cell_attempts[1].axes.실적구분별[12]**: 판매전력량
- **analysis[0].cell_attempts[1].axes.실적구분별[13]**: 판매전력량-수요성장률
- **analysis[0].cell_attempts[1].axes.실적구분별[14]**: 송전전력량(양수제외)
- **analysis[0].cell_attempts[1].axes.실적구분별[15]**: …외 12개
- **analysis[0].cell_attempts[1].population_fallback**: False
- **analysis[0].cell_attempts[1].match_source**: rule
- **analysis[0].cell_attempts[1].error**: itmId 매칭 실패: subject='경제성장률'
- **analysis[0].cell_attempts[2].tbl_id**: DT_XNS0110
- **analysis[0].cell_attempts[2].tbl_nm**: 경제성장률(불변가격) - 남부·동남아시아
- **analysis[0].cell_attempts[2].matched**: False
- **analysis[0].cell_attempts[2].value**: None
- **analysis[0].cell_attempts[2].unit**: None
- **analysis[0].cell_attempts[2].itm_id**: T10
- **analysis[0].cell_attempts[2].items[0]**: 경제성장률(기준년가격 GDP)
- **analysis[0].cell_attempts[2].axes.국가별[0]**: 브루나이
- **analysis[0].cell_attempts[2].axes.국가별[1]**: 캄보디아
- **analysis[0].cell_attempts[2].axes.국가별[2]**: 인도
- **analysis[0].cell_attempts[2].axes.국가별[3]**: 인도네시아
- **analysis[0].cell_attempts[2].axes.국가별[4]**: 라오스
- **analysis[0].cell_attempts[2].axes.국가별[5]**: 말레이시아
- **analysis[0].cell_attempts[2].axes.국가별[6]**: 미얀마
- **analysis[0].cell_attempts[2].axes.국가별[7]**: 필리핀
- **analysis[0].cell_attempts[2].axes.국가별[8]**: 싱가포르
- **analysis[0].cell_attempts[2].axes.국가별[9]**: 태국
- **analysis[0].cell_attempts[2].axes.국가별[10]**: 베트남
- **analysis[0].cell_attempts[2].population_fallback**: False
- **analysis[0].cell_attempts[2].match_source**: rule
- **analysis[0].cell_attempts[2].error**: 분류축 A 매칭 실패: population='북한'
- **analysis[0].cell_attempts[3].tbl_id**: DT_XNN0110
- **analysis[0].cell_attempts[3].tbl_nm**: 경제성장률(불변가격) - 동북·중앙아시아
- **analysis[0].cell_attempts[3].matched**: False
- **analysis[0].cell_attempts[3].value**: None
- **analysis[0].cell_attempts[3].unit**: None
- **analysis[0].cell_attempts[3].itm_id**: T10
- **analysis[0].cell_attempts[3].items[0]**: 경제성장률(기준년가격 GDP)
- **analysis[0].cell_attempts[3].axes.국가별[0]**: 아르메니아
- **analysis[0].cell_attempts[3].axes.국가별[1]**: 아제르바이잔
- **analysis[0].cell_attempts[3].axes.국가별[2]**: 중국
- **analysis[0].cell_attempts[3].axes.국가별[3]**: 조지아
- **analysis[0].cell_attempts[3].axes.국가별[4]**: 카자흐스탄
- **analysis[0].cell_attempts[3].axes.국가별[5]**: 키르기스스탄
- **analysis[0].cell_attempts[3].axes.국가별[6]**: 몽골
- **analysis[0].cell_attempts[3].axes.국가별[7]**: 타지키스탄
- **analysis[0].cell_attempts[3].axes.국가별[8]**: 투르크메니스탄
- **analysis[0].cell_attempts[3].axes.국가별[9]**: 우즈베키스탄
- **analysis[0].cell_attempts[3].axes.국가별[10]**: 벨라루스
- **analysis[0].cell_attempts[3].axes.국가별[11]**: 몰도바
- **analysis[0].cell_attempts[3].axes.국가별[12]**: 러시아
- **analysis[0].cell_attempts[3].axes.국가별[13]**: 우크라이나
- **analysis[0].cell_attempts[3].population_fallback**: False
- **analysis[0].cell_attempts[3].match_source**: rule
- **analysis[0].cell_attempts[3].error**: 분류축 A 매칭 실패: population='북한'
- **analysis[0].cell_attempts[4].tbl_id**: DT_1YL20571
- **analysis[0].cell_attempts[4].tbl_nm**: 경제성장률(시도)
- **analysis[0].cell_attempts[4].matched**: True
- **analysis[0].cell_attempts[4].value**: 1.6
- **analysis[0].cell_attempts[4].unit**: %
- **analysis[0].cell_attempts[4].itm_id**: T10
- **analysis[0].cell_attempts[4].items[0]**: 성장률
- **analysis[0].cell_attempts[4].axes.행정구역별[0]**: 전국
- **analysis[0].cell_attempts[4].axes.행정구역별[1]**: 서울특별시
- **analysis[0].cell_attempts[4].axes.행정구역별[2]**: 부산광역시
- **analysis[0].cell_attempts[4].axes.행정구역별[3]**: 대구광역시
- **analysis[0].cell_attempts[4].axes.행정구역별[4]**: 인천광역시
- **analysis[0].cell_attempts[4].axes.행정구역별[5]**: 광주광역시
- **analysis[0].cell_attempts[4].axes.행정구역별[6]**: 대전광역시
- **analysis[0].cell_attempts[4].axes.행정구역별[7]**: 울산광역시
- **analysis[0].cell_attempts[4].axes.행정구역별[8]**: 세종특별자치시
- **analysis[0].cell_attempts[4].axes.행정구역별[9]**: 경기도
- **analysis[0].cell_attempts[4].axes.행정구역별[10]**: 강원특별자치도
- **analysis[0].cell_attempts[4].axes.행정구역별[11]**: 충청북도
- **analysis[0].cell_attempts[4].axes.행정구역별[12]**: 충청남도
- **analysis[0].cell_attempts[4].axes.행정구역별[13]**: 전북특별자치도
- **analysis[0].cell_attempts[4].axes.행정구역별[14]**: 전라남도
- **analysis[0].cell_attempts[4].axes.행정구역별[15]**: …외 3개
- **analysis[0].cell_attempts[4].population_fallback**: True
- **analysis[0].cell_attempts[4].match_source**: rule
- **analysis[0].cell_attempts[4].error**: None
- **analysis[0].cell_attempts[5].tbl_id**: DT_200Y123
- **analysis[0].cell_attempts[5].tbl_nm**: 경제활동별 성장기여도(계절조정, 실질, 분기)
- **analysis[0].cell_attempts[5].matched**: False
- **analysis[0].cell_attempts[5].value**: None
- **analysis[0].cell_attempts[5].unit**: None
- **analysis[0].cell_attempts[5].itm_id**: None
- **analysis[0].cell_attempts[5].items[0]**: 경제활동별 성장기여도(계절조정 실질 분기)
- **analysis[0].cell_attempts[5].axes.계정항목별[0]**: 농림어업
- **analysis[0].cell_attempts[5].axes.계정항목별[1]**: 음식료품 제조업
- **analysis[0].cell_attempts[5].axes.계정항목별[2]**: 전기업
- **analysis[0].cell_attempts[5].axes.계정항목별[3]**: 주거용 건물 건설업
- **analysis[0].cell_attempts[5].axes.계정항목별[4]**: 건물건설 및 건축보수업
- **analysis[0].cell_attempts[5].axes.계정항목별[5]**: 도소매 및 숙박음식업
- **analysis[0].cell_attempts[5].axes.계정항목별[6]**: 도소매업
- **analysis[0].cell_attempts[5].axes.계정항목별[7]**: 예술 스포츠 및 여가관련 서비스업
- **analysis[0].cell_attempts[5].axes.계정항목별[8]**: 통신업
- **analysis[0].cell_attempts[5].axes.계정항목별[9]**: 전문 과학 및 기술관련 서비스업
- **analysis[0].cell_attempts[5].axes.계정항목별[10]**: 광업
- **analysis[0].cell_attempts[5].axes.계정항목별[11]**: 섬유 및 가죽제품 제조업
- **analysis[0].cell_attempts[5].axes.계정항목별[12]**: 가스 증기 및 공기조절 공급업
- **analysis[0].cell_attempts[5].axes.계정항목별[13]**: 비주거용 건물 건설업
- **analysis[0].cell_attempts[5].axes.계정항목별[14]**: 토목건설업
- **analysis[0].cell_attempts[5].axes.계정항목별[15]**: …외 33개
- **analysis[0].cell_attempts[5].population_fallback**: False
- **analysis[0].cell_attempts[5].match_source**: rule
- **analysis[0].cell_attempts[5].error**: itmId 매칭 실패: subject='경제성장률'
- **analysis[0].cell_attempts[6].tbl_id**: DT_200Y124
- **analysis[0].cell_attempts[6].tbl_nm**: 경제활동별 성장기여도(원계열, 실질, 분기 및 연간)
- **analysis[0].cell_attempts[6].matched**: False
- **analysis[0].cell_attempts[6].value**: None
- **analysis[0].cell_attempts[6].unit**: None
- **analysis[0].cell_attempts[6].itm_id**: None
- **analysis[0].cell_attempts[6].items[0]**: 경제활동별 성장기여도(원계열 실질 분기 및 연간)
- **analysis[0].cell_attempts[6].axes.계정항목별[0]**: 농림어업
- **analysis[0].cell_attempts[6].axes.계정항목별[1]**: 재배업
- **analysis[0].cell_attempts[6].axes.계정항목별[2]**: 음식료품 제조업
- **analysis[0].cell_attempts[6].axes.계정항목별[3]**: 전기업
- **analysis[0].cell_attempts[6].axes.계정항목별[4]**: 주거용 건물 건설업
- **analysis[0].cell_attempts[6].axes.계정항목별[5]**: 건물건설 및 건축보수업
- **analysis[0].cell_attempts[6].axes.계정항목별[6]**: 도소매 및 숙박음식업
- **analysis[0].cell_attempts[6].axes.계정항목별[7]**: 도소매업
- **analysis[0].cell_attempts[6].axes.계정항목별[8]**: 예술 스포츠 및 여가관련 서비스업
- **analysis[0].cell_attempts[6].axes.계정항목별[9]**: 통신업
- **analysis[0].cell_attempts[6].axes.계정항목별[10]**: 전문 과학 및 기술관련 서비스업
- **analysis[0].cell_attempts[6].axes.계정항목별[11]**: 축산업
- **analysis[0].cell_attempts[6].axes.계정항목별[12]**: 광업
- **analysis[0].cell_attempts[6].axes.계정항목별[13]**: 섬유 및 가죽제품 제조업
- **analysis[0].cell_attempts[6].axes.계정항목별[14]**: 가스 증기 및 공기조절 공급업
- **analysis[0].cell_attempts[6].axes.계정항목별[15]**: …외 37개
- **analysis[0].cell_attempts[6].population_fallback**: False
- **analysis[0].cell_attempts[6].match_source**: rule
- **analysis[0].cell_attempts[6].error**: itmId 매칭 실패: subject='경제성장률'
- **analysis[0].cell_attempts[7].tbl_id**: DT_2UNS0080
- **analysis[0].cell_attempts[7].tbl_nm**: 성별 연령별 실업률
- **analysis[0].cell_attempts[7].matched**: False
- **analysis[0].cell_attempts[7].value**: None
- **analysis[0].cell_attempts[7].unit**: None
- **analysis[0].cell_attempts[7].itm_id**: None
- **analysis[0].cell_attempts[7].items[0]**: 성별 연령별 실업률
- **analysis[0].cell_attempts[7].axes.국가[0]**: 아시아
- **analysis[0].cell_attempts[7].axes.국가[1]**: 대한민국
- **analysis[0].cell_attempts[7].axes.국가[2]**: 아제르바이잔
- **analysis[0].cell_attempts[7].axes.국가[3]**: 바레인
- **analysis[0].cell_attempts[7].axes.국가[4]**: 중국
- **analysis[0].cell_attempts[7].axes.국가[5]**: 키프로스
- **analysis[0].cell_attempts[7].axes.국가[6]**: 조지아
- **analysis[0].cell_attempts[7].axes.국가[7]**: 홍콩
- **analysis[0].cell_attempts[7].axes.국가[8]**: 인도
- **analysis[0].cell_attempts[7].axes.국가[9]**: 인도네시아
- **analysis[0].cell_attempts[7].axes.국가[10]**: 이란
- **analysis[0].cell_attempts[7].axes.국가[11]**: 이라크
- **analysis[0].cell_attempts[7].axes.국가[12]**: 이스라엘
- **analysis[0].cell_attempts[7].axes.국가[13]**: 일본
- **analysis[0].cell_attempts[7].axes.국가[14]**: 요르단
- **analysis[0].cell_attempts[7].axes.국가[15]**: …외 125개
- **analysis[0].cell_attempts[7].axes.성별[0]**: 전체
- **analysis[0].cell_attempts[7].axes.성별[1]**: 남자
- **analysis[0].cell_attempts[7].axes.성별[2]**: 여자
- **analysis[0].cell_attempts[7].axes.연령별[0]**: 15-24세
- **analysis[0].cell_attempts[7].axes.연령별[1]**: 15세 이상
- **analysis[0].cell_attempts[7].axes.연령별[2]**: 25세 이상
- **analysis[0].cell_attempts[7].population_fallback**: False
- **analysis[0].cell_attempts[7].match_source**: rule
- **analysis[0].cell_attempts[7].error**: itmId 매칭 실패: subject='경제성장률'
- **analysis[0].cell_attempts[8].tbl_id**: DT_2UNS0216
- **analysis[0].cell_attempts[8].tbl_nm**: 경제 활동에 참여하는 아동 비율
- **analysis[0].cell_attempts[8].matched**: False
- **analysis[0].cell_attempts[8].value**: None
- **analysis[0].cell_attempts[8].unit**: None
- **analysis[0].cell_attempts[8].itm_id**: None
- **analysis[0].cell_attempts[8].items[0]**: 성별 연령별 경제활동 참여 아동 비율
- **analysis[0].cell_attempts[8].axes.국가[0]**: 아시아
- **analysis[0].cell_attempts[8].axes.국가[1]**: 대한민국
- **analysis[0].cell_attempts[8].axes.국가[2]**: 아제르바이잔
- **analysis[0].cell_attempts[8].axes.국가[3]**: 바레인
- **analysis[0].cell_attempts[8].axes.국가[4]**: 중국
- **analysis[0].cell_attempts[8].axes.국가[5]**: 키프로스
- **analysis[0].cell_attempts[8].axes.국가[6]**: 조지아
- **analysis[0].cell_attempts[8].axes.국가[7]**: 홍콩
- **analysis[0].cell_attempts[8].axes.국가[8]**: 인도
- **analysis[0].cell_attempts[8].axes.국가[9]**: 인도네시아
- **analysis[0].cell_attempts[8].axes.국가[10]**: 이란
- **analysis[0].cell_attempts[8].axes.국가[11]**: 이라크
- **analysis[0].cell_attempts[8].axes.국가[12]**: 이스라엘
- **analysis[0].cell_attempts[8].axes.국가[13]**: 일본
- **analysis[0].cell_attempts[8].axes.국가[14]**: 요르단
- **analysis[0].cell_attempts[8].axes.국가[15]**: …외 125개
- **analysis[0].cell_attempts[8].axes.성별[0]**: 남여합계
- **analysis[0].cell_attempts[8].axes.성별[1]**: 남자
- **analysis[0].cell_attempts[8].axes.성별[2]**: 여자
- **analysis[0].cell_attempts[8].axes.연령별[0]**: 5-14세
- **analysis[0].cell_attempts[8].axes.연령별[1]**: 5-17세
- **analysis[0].cell_attempts[8].axes.연령별[2]**: 7-17세
- **analysis[0].cell_attempts[8].axes.연령별[3]**: 10-17세
- **analysis[0].cell_attempts[8].population_fallback**: False
- **analysis[0].cell_attempts[8].match_source**: rule
- **analysis[0].cell_attempts[8].error**: itmId 매칭 실패: subject='경제성장률'
- **analysis[0].cell_attempts[9].tbl_id**: DT_XNN0050
- **analysis[0].cell_attempts[9].tbl_nm**: 인간개발지수 - 동북·중앙아시아
- **analysis[0].cell_attempts[9].matched**: False
- **analysis[0].cell_attempts[9].value**: None
- **analysis[0].cell_attempts[9].unit**: None
- **analysis[0].cell_attempts[9].itm_id**: None
- **analysis[0].cell_attempts[9].items[0]**: HDI 순위
- **analysis[0].cell_attempts[9].items[1]**: 인간개발지수
- **analysis[0].cell_attempts[9].items[2]**: 기대수명(세)
- **analysis[0].cell_attempts[9].items[3]**: 평균교육기간(년)
- **analysis[0].cell_attempts[9].items[4]**: 기대교육기간(년)
- **analysis[0].cell_attempts[9].items[5]**: 1인당 GNI(2021 PPP$)
- **analysis[0].cell_attempts[9].axes.국가별[0]**: 아르메니아
- **analysis[0].cell_attempts[9].axes.국가별[1]**: 아제르바이잔
- **analysis[0].cell_attempts[9].axes.국가별[2]**: 중국
- **analysis[0].cell_attempts[9].axes.국가별[3]**: 조지아
- **analysis[0].cell_attempts[9].axes.국가별[4]**: 카자흐스탄
- **analysis[0].cell_attempts[9].axes.국가별[5]**: 키르기스스탄
- **analysis[0].cell_attempts[9].axes.국가별[6]**: 몽골
- **analysis[0].cell_attempts[9].axes.국가별[7]**: 타지키스탄
- **analysis[0].cell_attempts[9].axes.국가별[8]**: 투르크메니스탄
- **analysis[0].cell_attempts[9].axes.국가별[9]**: 우즈베키스탄
- **analysis[0].cell_attempts[9].axes.국가별[10]**: 벨라루스
- **analysis[0].cell_attempts[9].axes.국가별[11]**: 몰도바
- **analysis[0].cell_attempts[9].axes.국가별[12]**: 러시아
- **analysis[0].cell_attempts[9].axes.국가별[13]**: 우크라이나
- **analysis[0].cell_attempts[9].population_fallback**: False
- **analysis[0].cell_attempts[9].match_source**: rule
- **analysis[0].cell_attempts[9].error**: itmId 매칭 실패: subject='경제성장률'
- **analysis[0].kosis_query.api**: statisticsData.do → statisticsParameterData.do
- **analysis[0].kosis_query.tbl_id**:  → DT_1YL20571
- **analysis[0].kosis_query.params**:  → {"method": "getList", "orgId": "101", "tblId": "DT_1YL20571", "itmId": "T10", "objL1": "00", "objL2": "", "objL3": "", "objL4": "", "prdSe": "Y", "startPrdDe": "2023", "endPrdDe": "2023", "match_filters": {"C1": "00"}}
- **analysis[0].kosis_query.rows_returned**: 0 → 1
- **analysis[0].kosis_query.success**: 0 → 1
- **analysis[0].kosis_query.duration_ms**: 0 → 3601
- **analysis[0].evidences[0].claim_id**: clm-0001
- **analysis[0].evidences[0].source**: KOSIS
- **analysis[0].evidences[0].subject**: 경제성장률
- **analysis[0].evidences[0].unit**: %
- **analysis[0].evidences[0].period_type**: Y
- **analysis[0].evidences[0].period**: 2023
- **analysis[0].evidences[0].population**: 북한
- **analysis[0].evidences[0].evidence_id**: None
- **analysis[0].evidences[0].value**: 1.6
- **analysis[0].evidences[0].kosis_org_id**: 101
- **analysis[0].evidences[0].kosis_tbl_id**: DT_1YL20571
- **analysis[0].evidences[0].table_name**: 경제성장률(시도)
- **analysis[0].evidences[0].kosis_item_id**: T10
- **analysis[0].evidences[0].url**: None
- **analysis[0].evidences[0].classification.C1**: 00
- **analysis[0].evidences[0].last_updated**: 2025-12-24
- **analysis[0].evidences[0].retrieved_at**: 2026-06-11T09:20:43+00:00
- **analysis[0].evidences[0].population_fallback**: True
- **analysis[0].evidences[0].match_source**: rule

### 📊 5단계 상세 — claim 추출값 · 검색값 · 후보 표 디버깅

**[clm-0001] 경제성장률**
- 📌 claim 추출값: 값 `1.4`(원문 `1.4%`) | 시점 `2023`(원문 `2023년`) | 모집단 `북한` | 단위 `%` | subject `경제성장률`
- 🔍 KOSIS 에 넣은 값: subject `경제성장률`(공백 제거) | population `북한` | period `2023`
- 📑 후보 표별 조회 시도 10개:
    - `DT_2KAA905` 경제성장률(불변가격)
        - 항목: 경제성장률(기준년가격 GDP)
        - 분류축 [국가별]: 세계, 아시아, 대한민국, 아프가니스탄, 아르메니아, 아제르바이잔, 바레인, 방글라데시, 부탄, 브루나이, 캄보디아, 중국, 키프로스, 조지아, 홍콩, …외 226개
        - 결과: ❌ 셀 조회 실패: 30: 데이터가 존재하지 않습니다.
    - `TX_38803_A026` 연도별 전력수급 실적
        - 항목: 연도별 전력수급 실적
        - 분류축 [실적구분별]: 경제성장률, 설비용량(연말), 설비용량(연말)-성장률, 최대전력, 최대전력-성장률, 설비예비율, 공급예비율, 총발전량, 총발전량-성장률, 이용률, 발전소내 소비전력률, 발전소내 소비전력량, 판매전력량, 판매전력량-수요성장률, 송전전력량(양수제외), …외 12개
        - 결과: ❌ itmId 매칭 실패: subject='경제성장률'
    - `DT_XNS0110` 경제성장률(불변가격) - 남부·동남아시아
        - 항목: 경제성장률(기준년가격 GDP)
        - 분류축 [국가별]: 브루나이, 캄보디아, 인도, 인도네시아, 라오스, 말레이시아, 미얀마, 필리핀, 싱가포르, 태국, 베트남
        - 결과: ❌ 분류축 A 매칭 실패: population='북한'
    - `DT_XNN0110` 경제성장률(불변가격) - 동북·중앙아시아
        - 항목: 경제성장률(기준년가격 GDP)
        - 분류축 [국가별]: 아르메니아, 아제르바이잔, 중국, 조지아, 카자흐스탄, 키르기스스탄, 몽골, 타지키스탄, 투르크메니스탄, 우즈베키스탄, 벨라루스, 몰도바, 러시아, 우크라이나
        - 결과: ❌ 분류축 A 매칭 실패: population='북한'
    - `DT_1YL20571` 경제성장률(시도) ★채택
        - 항목: 성장률
        - 분류축 [행정구역별]: 전국, 서울특별시, 부산광역시, 대구광역시, 인천광역시, 광주광역시, 대전광역시, 울산광역시, 세종특별자치시, 경기도, 강원특별자치도, 충청북도, 충청남도, 전북특별자치도, 전라남도, …외 3개
        - 결과: ✅ 1.6 % (itmId T10)
    - `DT_200Y123` 경제활동별 성장기여도(계절조정, 실질, 분기)
        - 항목: 경제활동별 성장기여도(계절조정 실질 분기)
        - 분류축 [계정항목별]: 농림어업, 음식료품 제조업, 전기업, 주거용 건물 건설업, 건물건설 및 건축보수업, 도소매 및 숙박음식업, 도소매업, 예술 스포츠 및 여가관련 서비스업, 통신업, 전문 과학 및 기술관련 서비스업, 광업, 섬유 및 가죽제품 제조업, 가스 증기 및 공기조절 공급업, 비주거용 건물 건설업, 토목건설업, …외 33개
        - 결과: ❌ itmId 매칭 실패: subject='경제성장률'
    - `DT_200Y124` 경제활동별 성장기여도(원계열, 실질, 분기 및 연간)
        - 항목: 경제활동별 성장기여도(원계열 실질 분기 및 연간)
        - 분류축 [계정항목별]: 농림어업, 재배업, 음식료품 제조업, 전기업, 주거용 건물 건설업, 건물건설 및 건축보수업, 도소매 및 숙박음식업, 도소매업, 예술 스포츠 및 여가관련 서비스업, 통신업, 전문 과학 및 기술관련 서비스업, 축산업, 광업, 섬유 및 가죽제품 제조업, 가스 증기 및 공기조절 공급업, …외 37개
        - 결과: ❌ itmId 매칭 실패: subject='경제성장률'
    - `DT_2UNS0080` 성별 연령별 실업률
        - 항목: 성별 연령별 실업률
        - 분류축 [국가]: 아시아, 대한민국, 아제르바이잔, 바레인, 중국, 키프로스, 조지아, 홍콩, 인도, 인도네시아, 이란, 이라크, 이스라엘, 일본, 요르단, …외 125개
        - 분류축 [성별]: 전체, 남자, 여자
        - 분류축 [연령별]: 15-24세, 15세 이상, 25세 이상
        - 결과: ❌ itmId 매칭 실패: subject='경제성장률'
    - `DT_2UNS0216` 경제 활동에 참여하는 아동 비율
        - 항목: 성별 연령별 경제활동 참여 아동 비율
        - 분류축 [국가]: 아시아, 대한민국, 아제르바이잔, 바레인, 중국, 키프로스, 조지아, 홍콩, 인도, 인도네시아, 이란, 이라크, 이스라엘, 일본, 요르단, …외 125개
        - 분류축 [성별]: 남여합계, 남자, 여자
        - 분류축 [연령별]: 5-14세, 5-17세, 7-17세, 10-17세
        - 결과: ❌ itmId 매칭 실패: subject='경제성장률'
    - `DT_XNN0050` 인간개발지수 - 동북·중앙아시아
        - 항목: HDI 순위, 인간개발지수, 기대수명(세), 평균교육기간(년), 기대교육기간(년), 1인당 GNI(2021 PPP$)
        - 분류축 [국가별]: 아르메니아, 아제르바이잔, 중국, 조지아, 카자흐스탄, 키르기스스탄, 몽골, 타지키스탄, 투르크메니스탄, 우즈베키스탄, 벨라루스, 몰도바, 러시아, 우크라이나
        - 결과: ❌ itmId 매칭 실패: subject='경제성장률'
- 🎯 얻으려는 셀 좌표: `{"method": "getList", "orgId": "101", "tblId": "DT_1YL20571", "itmId": "T10", "objL1": "00", "objL2": "", "objL3": "", "objL4": "", "prdSe": "Y", "startPrdDe": "2023", "endPrdDe": "2023", "match_filters": {"C1": "00"}}`
- 🎯 얻어낸 cell 값: **1.6 %** | 시점 2023 | 표 `DT_1YL20571` | itmId T10


## 6. 증거 랭킹

_(변경 없음)_

## 7. 통계 수치 비교 판단

- **verifications.summary.total_claims**: 1
- **verifications.summary.overall_verdict**: UNVERIFIED
- **verifications.summary.average_confidence**: 0.0
- **verifications.claim_results[0].claim_id**: clm-0001
- **verifications.claim_results[0].verdict**: N
- **verifications.claim_results[0].verdict_human**: None
- **verifications.claim_results[0].verdict_human_note**: None
- **verifications.claim_results[0].mismatch_type**: None
- **verifications.claim_results[0].claim_value**: 1.4
- **verifications.claim_results[0].kosis_value**: 1.6
- **verifications.claim_results[0].explanation**: 
- **verifications.claim_results[0].confidence**: 0.0
- **verifications.claim_results[0].llm_model**: 
- **verifications.claim_results[0].evidence[0].claim_id**: clm-0001
- **verifications.claim_results[0].evidence[0].source**: KOSIS
- **verifications.claim_results[0].evidence[0].subject**: 경제성장률
- **verifications.claim_results[0].evidence[0].unit**: %
- **verifications.claim_results[0].evidence[0].period_type**: Y
- **verifications.claim_results[0].evidence[0].period**: 2023
- **verifications.claim_results[0].evidence[0].population**: 북한
- **verifications.claim_results[0].evidence[0].evidence_id**: None
- **verifications.claim_results[0].evidence[0].value**: 1.6
- **verifications.claim_results[0].evidence[0].kosis_org_id**: 101
- **verifications.claim_results[0].evidence[0].kosis_tbl_id**: DT_1YL20571
- **verifications.claim_results[0].evidence[0].table_name**: 경제성장률(시도)
- **verifications.claim_results[0].evidence[0].kosis_item_id**: T10
- **verifications.claim_results[0].evidence[0].url**: None
- **verifications.claim_results[0].evidence[0].classification.C1**: 00
- **verifications.claim_results[0].evidence[0].last_updated**: 2025-12-24
- **verifications.claim_results[0].evidence[0].retrieved_at**: 2026-06-11T09:20:43+00:00
- **verifications.claim_results[0].evidence[0].population_fallback**: True
- **verifications.claim_results[0].evidence[0].match_source**: rule
- **verifications.claim_results[0].metric.operation**: absolute
- **verifications.claim_results[0].metric.claim_value**: 1.4
- **verifications.claim_results[0].metric.kosis_value**: 1.6
- **verifications.claim_results[0].metric.rel_diff**: 0.1250000000000001
- **verifications.claim_results[0].metric.within_tolerance**: False
- **verifications.claim_results[0].metric.verdict**: Verdict.NOT_ENOUGH_INFO
- **verifications.claim_results[0].metric.mismatch_type**: None
- **verifications.claim_results[0].metric.note**: population_fallback: 요청 집단 대신 전체(합계)값과 비교 — [8] 정합성 확인 대상 | 요청 집단을 어느 표에서도 매칭 못 함(전부 전체값 폴백) → 검증 불가
- **verifications.claim_results[0].metric.align_reason**: None
- **verifications.claim_results[0].metric.align_source**: None
- **verifications.claim_results[0].metric.compare_id**: None
- **verifications.claim_results[0].metric.computed_value**: None
- **verifications.claim_results[0].needs_hitl**: False
- **verifications.claim_results[0].hitl_category**: None
- **verifications.claim_results[0].hitl_reason**: None

## 8. 통계수치와 문장의 정합성 판단

_(변경 없음)_

## 9. 종합 분석·검증 결과 생성

- **verifications.summary.overall_verdict**: UNVERIFIED → N

## 10. 설명 생성

- **verifications.claim_results[0].explanation**:  → 2023년 경제성장률에 대한 KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다.
