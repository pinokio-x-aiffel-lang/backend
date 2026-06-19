# 테스트셋 보완 — 사람 검수 (leeaain, 2026-06-19, v3) ✅ 완료

> **✅ 검수 완료 (260619): 7건 전부 `magnitude` 확정.**
> 반영처: `benchmark/data/7_metric/7_source_1.jsonl` — stage7 레코드 있는 187·188·209에 `mismatch_type=magnitude` + `mismatch_type_provenance=human_reviewed(leeaain,260619)`.
> 189·190·191·194는 무증거(stage7 채점제외)라 적용 대상 없음. 결정적 23건은 기존 magnitude 유지.

**(이력 보존용 — 아래는 검수 요청 원본)** 맨 오른쪽 `검수` 칸은 빈칸=초안(magnitude) 채택.

> 이전 v2의 **B(2단계 슬롯)·C(4단계 델타 기준표)는 검수 불필요로 확정·삭제**했습니다.
> 근거: 어떤 채점기도 그 gold를 읽지 않음 (`score_extract`=gold_claim/pred_claim/ctype · `score_retrieve`=gold_rank/success). "슬롯 정확도"나 "델타-기준표 채점" 지표를 새로 만들 때만 필요.

## A. 7단계 mismatch_type — %/파생 7건

거짓 기사 7건입니다. 제가 "왜 틀렸는지"를 `magnitude`(값 크기 차이)로 달았는데, 값이 **% · 전년대비 상승률 · 계산 비율(파생)** 이라 `magnitude`가 맞는지, 아니면 다른 유형인지 사람 판단이 필요합니다.

(결정적 23건은 직접 절대값 misquote라 `magnitude`로 이미 반영함 — 아래 7건만 검수.)

| row | 지표 | 기사값(거짓) | 공식값 | 내 초안 | 쟁점 | 검수(최종 mismatch_type) |
|---|---|---|---|---|---|---|
| 187 | 청년층 고용률 | 58.7% | 46.1% | magnitude | KOSIS 직접 셀(%) 존재. magnitude? 아니면 모집단(15~29) 확인 필요? |  |
| 188 | 청년층 실업률 | 12.4% | 5.9% | magnitude | 실업률 = 실업자/경활 파생율. magnitude 유지 OK? |  |
| 189 | 소비자물가지수(전년대비) | 5.8% (전년대비 상승률) | 2.3% | magnitude | '전년대비 %'는 change_rate(파생). magnitude vs 지수 자체 비교 — 어느 기준? |  |
| 190 | 생활물가지수(전년대비) | 7.9% (전년대비) | 2.7% | magnitude | 동일(전년대비 파생율). |  |
| 191 | 신선식품지수(전년대비) | 24.5% (전년대비) | 9.8% | magnitude | 동일(전년대비 파생율). |  |
| 194 | 60세 이상 고령인구 비율 | 31.5% (비율) | 26.85% (13,755,125 / 51,217,221 계산) | magnitude | 공식값이 count÷count 계산. magnitude? 아니면 aggregation(분모 다름)? |  |
| 209 | 농가 고령인구 비율(65세 이상) | 78.4% (비율) | 55.8% | magnitude | 계산 비율. magnitude 유지 OK? |  |

### 작성법
- 제 초안(`magnitude`)이 맞다 → `검수` 칸 **비워두기**
- 다른 유형이다 → enum 코드 적기: `magnitude` · `rounding` · `direction` · `unit` · `period` · `population` · `subject` · `aggregation`
