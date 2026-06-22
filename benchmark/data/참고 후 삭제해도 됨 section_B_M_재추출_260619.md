## B. 2단계 슬롯 gold — M 30건 (현재 2단계 모듈 재추출, 260619)

각 row의 추출 claim을 현재 모듈로 재생성. `검수 →` 뒤에 틀린 슬롯만 (빈칸=채택).

---

**row 124 (M)** — claim 2개
> 2024년 합계출산율이 0.75명으로 집계됐다. 부부 두 사람이 단 0.75명만 남기는 셈이니, 한 세대마다 인구가 3분의 1 토막 나는 민족 소멸이 수학적으로 확정됐다. 이제 출산 회복을 논하는 것은 무의미하며 대한민국의 종말은 시간문제일 뿐이다.

- [0] `absolute` · subject=`합계출산율` · value=`0.75명` · unit=`명` · period=`Y:2024년` · compare=`None` · population=`대한민국`
- [1] `absolute` · subject=`부부의 자녀 수` · value=`0.75명` · unit=`명` · period=`S:불명` · compare=`None` · population=`불명`

검수 → 

---

**row 125 (M)** — claim 4개
> 2024년 출생아 수가 23만8300명으로 전년 대비 3.6% 늘었다지만, 불과 한 세대 전 60만 명대였던 것과 비교하면 출생아는 이미 반의 반 토막이 났다. 3.6%라는 미세한 증가율에 취해 있는 사이 대한민국의 신생아실은 사실상 폐업 수순에 접어들었다.

- [0] `absolute` · subject=`출생아 수` · value=`23만8300명` · unit=`명` · period=`Y:2024년` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`출생아 수` · value=`3.6% 증가했다` · unit=`%p` · period=`Y:전년` · compare=`전년` · population=`대한민국`
- [2] `absolute` · subject=`출생아 수` · value=`60만 명대` · unit=`명` · period=`Y:한 세대 전` · compare=`None` · population=`대한민국`
- [3] `change_rate` · subject=`출생아 수` · value=`절반 이하로 감소하였다` · unit=`불명` · period=`Y:한 세대 전` · compare=`한 세대 전` · population=`대한민국`

검수 → 

---

**row 126 (M)** — claim 2개
> 2024년 출생아 수가 전년보다 3.6% 증가한 23만8300명을 기록했다. 이는 그동안의 출산장려정책이 성공한 결과로 보인다. 양육수당과 육아휴직등의 정책적 장려가 주효한 원인으로 출산율 반등의 일등공신으로 꼽힌다.

- [0] `change_rate` · subject=`출생아 수` · value=`3.6% 증가` · unit=`%p` · period=`Y:2024년` · compare=`전년` · population=`대한민국`
- [1] `absolute` · subject=`출생아 수` · value=`23만8300명` · unit=`명` · period=`Y:2024년` · compare=`None` · population=`대한민국`

검수 → 

---

**row 127 (M)** — claim 2개
> 2024년 혼인 건수가 22만2000건으로 전년 대비 14.8%나 급증했다. 그러나 이 수치는 코로나로 미뤄졌던 결혼이 한꺼번에 몰린 일회성 반짝 효과일 뿐, 결혼 기피 추세가 꺾였다는 증거가 전혀 아니다. 오히려 이 비정상적 급등은 향후 혼인 건수가 다시 급락할 것임을 예고하는 불길한 신호다.

- [0] `absolute` · subject=`혼인 건수` · value=`22만2000건` · unit=`건` · period=`Y:2024년` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`혼인 건수` · value=`14.8% 증가` · unit=`%` · period=`Y:전년` · compare=`None` · population=`대한민국`

검수 → 

---

**row 128 (M)** — claim 2개
> 2024년 혼인 건수가 14.8% 증가해 22만2000건을 기록했다. 정부는 이를 '청년 정책의 성과'라고 홍보하지만, 결혼 장려 예산이 거의 집행되지 않은 해에 나타난 이 증가는 정책과 무관하다. 실제로는 종교적 길일이 많았던 우연일 뿐, 결혼율 회복은 정부의 공이 아니라 명백한 정책 실패 속의 요행이다.

- [0] `change_rate` · subject=`혼인 건수` · value=`14.8% 증가` · unit=`%p` · period=`Y:2024년` · compare=`전년` · population=`대한민국`
- [1] `absolute` · subject=`혼인 건수` · value=`22만2000건` · unit=`건` · period=`Y:2024년` · compare=`None` · population=`대한민국`

검수 → 

---

**row 129 (M)** — claim 3개
> 2024년 이혼 건수가 9만1000건으로 전년 대비 1.3% 감소했다. 하지만 같은 해 혼인이 22만2000건에 그친 것을 감안하면, 결혼 두 쌍 중 한 쌍 가까이가 갈라서는 '이혼 대란'이 벌어지고 있는 셈이다. 이혼이 줄었다는 발표는 가정 붕괴의 실상을 가리는 눈속임에 불과하다.

- [0] `absolute` · subject=`이혼 건수` · value=`9만1000건` · unit=`건` · period=`Y:2024년` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`이혼 건수` · value=`1.3% 감소` · unit=`%` · period=`Y:전년` · compare=`전년` · population=`대한민국`
- [2] `absolute` · subject=`혼인` · value=`22만2000건` · unit=`건` · period=`Y:2024년` · compare=`None` · population=`대한민국`

검수 → 

---

**row 130 (M)** — claim 2개
> 2024년 이혼 건수가 9만1000건으로 전년보다 1.3% 줄었다. 그러나 이는 가족이 화목해져서가 아니라, 애초에 결혼하는 사람 자체가 급감해 '이혼할 부부'가 사라졌기 때문이다. 즉 이혼 감소는 가정의 안정이 아니라 결혼 제도 자체의 붕괴를 보여주는 절망적 지표다.

- [0] `absolute` · subject=`이혼 건수` · value=`91,000건` · unit=`건` · period=`Y:2024년` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`이혼 건수` · value=`1.3% 감소` · unit=`%p` · period=`Y:전년` · compare=`전년` · population=`대한민국`

검수 → 

---

**row 131 (M)** — claim 1개
> 2024년 남성 평균 초혼연령이 33.9세로 올라섰다. 이는 우리 사회가 그만큼 신중하고 안정된 기반 위에서 결혼한다는 성숙의 증거가 아니라, 청년들이 30대 중반까지 결혼을 못 하는 '만혼 지옥'에 갇혔다는 뜻이다. 33.9세라는 숫자 하나로 대한민국 청년의 결혼은 사실상 사망 선고를 받았다.

- [0] `absolute` · subject=`남성 평균 초혼연령` · value=`33.9세` · unit=`세` · period=`Y:2024년` · compare=`None` · population=`대한민국`

검수 → 

---

**row 132 (M)** — claim 1개
> 남성 평균 초혼연령이 2024년 33.9세를 기록했다. 정부의 청년 주거·일자리 지원책이 본격화된 해에 초혼연령이 또 높아졌다는 것은, 그 모든 청년 정책이 결혼을 앞당기기는커녕 오히려 늦췄다는 결정적 증거다. 정책이 들어갈수록 결혼이 멀어진다면 그 정책은 폐기되어야 마땅하다.

- [0] `absolute` · subject=`남성 평균 초혼연령` · value=`33.9세` · unit=`세` · period=`Y:2024년` · compare=`None` · population=`대한민국`

검수 → 

---

**row 133 (M)** — claim 2개
> 2024년 사망자 수가 35만8400명으로 1.7% 증가했다. 보건당국은 고령화 탓이라 둘러대지만, 의료 접근성과 기대수명이 세계 최고 수준인 나라에서 사망자가 늘었다는 것은 의료 시스템이 총체적으로 붕괴했다는 명백한 신호다. 1.7%라는 숫자는 곧 닥칠 대규모 인명 재앙의 서막일 뿐이다.

- [0] `absolute` · subject=`사망자 수` · value=`35만8400명` · unit=`명` · period=`S:불명` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`사망자` · value=`1.7% 증가했다` · unit=`%p` · period=`Y:전년` · compare=`전년` · population=`대한민국`

검수 → 

---

**row 134 (M)** — claim 4개
> 2024년 사망자가 35만8400명으로 전년보다 1.7% 늘었다. 그런데 같은 해 출생아는 23만8300명에 불과했다. 태어나는 사람 1명당 죽는 사람이 1.5명꼴이라는 이 끔찍한 비율은, 대한민국이 이미 '죽어가는 나라'를 넘어 사실상 인구 청산 단계에 들어섰음을 증명한다.

- [0] `absolute` · subject=`사망자 수` · value=`35만8400명` · unit=`명` · period=`Y:2024년` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`사망자 수` · value=`1.7% 증가했다` · unit=`%` · period=`Y:전년` · compare=`전년` · population=`대한민국`
- [2] `absolute` · subject=`출생아 수` · value=`23만8300명` · unit=`명` · period=`Y:2024년` · compare=`None` · population=`대한민국`
- [3] `ratio` · subject=`인구 비율` · value=`약 1.5명` · unit=`불명` · period=`S:불명` · compare=`None` · population=`대한민국`

검수 → 

---

**row 135 (M)** — claim 2개
> 서울의 2024년 합계출산율이 0.58명으로 확인됐다. 전국 평균이 0.75명인데 수도 서울이 0.58명에 그쳤다는 것은, 대한민국에서 가장 부유하고 인프라가 잘 갖춰진 도시조차 아이 키우기를 포기했다는 의미다. 결국 한국의 저출산은 가난의 문제가 아니라 도시 문명 그 자체의 종말을 가리킨다.

- [0] `absolute` · subject=`합계출산율` · value=`0.58명` · unit=`명` · period=`Y:2024년` · compare=`None` · population=`서울`
- [1] `absolute` · subject=`평균 출산율` · value=`0.75명` · unit=`명` · period=`S:불명` · compare=`None` · population=`대한민국`

검수 → 

---

**row 136 (M)** — claim 1개
> 2024년 서울의 합계출산율은 0.58명으로 나타났다. 전국에서 가장 낮은 이 수치만 떼어 보면, 대한민국 전체가 이미 0.58명 수준으로 추락해 인구 회복이 영구히 불가능한 단계에 진입한 것으로 단정할 수 있다. 전국 평균이 그보다 높다는 사실은 무의미한 통계적 위안일 뿐이다.

- [0] `absolute` · subject=`합계출산율` · value=`0.58명` · unit=`명` · period=`Y:2024년` · compare=`None` · population=`서울`

검수 → 

---

**row 137 (M)** — claim 1개
> 세종시의 2024년 합계출산율이 1.03명을 기록했다. 한 도시가 1.03명을 달성했다는 것은 마음만 먹으면 출산율 1명대 회복이 얼마든지 가능하다는 '기적의 증거'다. 따라서 다른 지역의 저출산은 환경 탓이 아니라 순전히 주민들의 의지 부족이며, 세종처럼만 하면 출산율 위기는 즉시 해소된다.

- [0] `absolute` · subject=`합계출산율` · value=`1.03명` · unit=`명` · period=`Y:2024년` · compare=`None` · population=`세종시`

검수 → 

---

**row 138 (M)** — claim 2개
> 2024년 12월 전국 미분양 주택이 70,173호로 전월보다 7.7% 증가했다. 단 한 달 사이의 이 증가율을 그대로 1년으로 환산하면 연 90%가 넘는 폭증세로, 한국 부동산 시장은 이미 회복 불능의 붕괴 국면에 진입했다.

- [0] `absolute` · subject=`미분양 주택` · value=`70,173호` · unit=`호` · period=`M:2024년 12월` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`미분양 주택` · value=`7.7% 증가` · unit=`%` · period=`M:전월` · compare=`전월` · population=`대한민국`

검수 → 

---

**row 139 (M)** — claim 1개
> 2024년 12월 기준 전국 미분양 주택은 7만 호를 넘어섰다. 미분양이 이렇게 쌓였다는 것은 곧 모든 주택 수요가 완전히 증발했다는 뜻으로, 대한민국 주택시장은 단 한 채도 팔리지 않는 거래 절벽의 대공황에 빠졌다.

- [0] `absolute` · subject=`미분양 주택` · value=`7만 호` · unit=`호` · period=`M:2024년 12월` · compare=`None` · population=`대한민국`

검수 → 

---

**row 140 (M)** — claim 2개
> 2024년 12월 준공 후 미분양이 21,480호로 전월 대비 15.2% 급증했다. 정부의 부동산 부양책이 시행된 직후 악성 미분양이 이처럼 폭증한 것은, 해당 정책이 시장을 살리기는커녕 미분양을 양산한 직접적 원흉임을 명백히 보여준다.

- [0] `absolute` · subject=`준공 후 미분양` · value=`21,480호` · unit=`호` · period=`M:2024년 12월` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`미분양` · value=`15.2% 급증했다` · unit=`%` · period=`M:전월` · compare=`None` · population=`대한민국`

검수 → 

---

**row 141 (M)** — claim 2개
> 준공 후 미분양이 2024년 12월 한 달 만에 15.2% 늘었다. 이 한 달치 증가율 하나만으로도 악성 미분양이 매달 15%씩 무한 증식하는 추세가 확정됐다고 볼 수 있으며, 1년이면 다섯 배 가까이 불어나는 부동산 시한폭탄이 작동을 시작했다.

- [0] `change_rate` · subject=`미분양` · value=`15.2% 증가` · unit=`%p` · period=`M:2024년 12월` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`악성 미분양` · value=`약 15% 증가` · unit=`%p` · period=`M:매달` · compare=`None` · population=`대한민국`

검수 → 

---

**row 142 (M)** — claim 1개
> 2024년 12월 경기도 미분양 주택이 10,128호에 달했다. 경기도 한 곳의 미분양만 따로 떼어 보면, 전국에서 가장 인구가 많고 수요가 탄탄하다던 경기 부동산조차 무너졌으니 대한민국 전역의 집값은 이미 완전히 붕괴했다는 결론에 이른다.

- [0] `absolute` · subject=`미분양 주택 수` · value=`10,128호` · unit=`호` · period=`M:2024년 12월` · compare=`None` · population=`경기도`

검수 → 

---

**row 143 (M)** — claim 2개
> 2024년 12월 경기도 미분양은 10,128호로 집계됐다. 전국 미분양 70,173호 가운데 경기 물량을 단순 대비하면 경기가 전국 미분양을 주도하는 진앙지로 보이며, 가구 수가 압도적으로 많은 지역 특성을 가린 이 비교만으로 경기 주택시장은 전국 최악의 무덤으로 단정된다.

- [0] `absolute` · subject=`경기도 미분양` · value=`10,128호` · unit=`호` · period=`M:2024년 12월` · compare=`None` · population=`경기도`
- [1] `absolute` · subject=`전국 미분양` · value=`70,173호` · unit=`호` · period=`S:현재` · compare=`None` · population=`대한민국`

검수 → 

---

**row 144 (M)** — claim 4개
> 2024년 공업제품 물가는 전년 대비 1.5% 상승하는 데 그쳤다. 그런데 같은 해 신선과실은 17.1%나 올랐으니, 이 두 수치를 나란히 놓고 보면 공산품은 거의 거저나 다름없는 반면 농산물만 미친 듯이 폭등한 기형적 물가 구조가 굳어졌다고 단정할 수 있다.

- [0] `change_rate` · subject=`공업제품 물가` · value=`1.5% 상승` · unit=`%p` · period=`Y:2024년` · compare=`전년` · population=`대한민국`
- [1] `change_rate` · subject=`신선과실 가격` · value=`17.1% 올랐다` · unit=`%p` · period=`Y:2024년` · compare=`전년` · population=`대한민국`
- [2] `change_rate` · subject=`공산품 가격` · value=`상승폭 매우 적음` · unit=`불명` · period=`Y:2024년` · compare=`전년` · population=`대한민국`
- [3] `change_rate` · subject=`농산물 가격` · value=`크게 상승했다` · unit=`불명` · period=`Y:2024년` · compare=`전년` · population=`대한민국`

검수 → 

---

**row 145 (M)** — claim 1개
> 2024년 공업제품 물가 상승률이 1.5%에 불과했다. 이는 공산품 가격이 여전히 매년 오르고 있다는 명백한 증거로, 제조업 물가마저 단 한 번도 내리지 않은 채 상승만 거듭하는 끝없는 인플레이션 지옥이 확정됐다.

- [0] `absolute` · subject=`공업제품 물가 상승률` · value=`1.5%` · unit=`%` · period=`Y:2024년` · compare=`None` · population=`대한민국`

검수 → 

---

**row 146 (M)** — claim 1개
> 통계청이 2024년 고령인구 비율을 19.2%로 발표했다. 그러나 이는 곧 국민 10명 중 8명 이상이 65세 미만이라는 뜻으로, 한국은 여전히 압도적인 청장년 국가다. 고령화 우려는 명백히 과장된 괴담에 불과하다.

- [0] `absolute` · subject=`고령인구 비율` · value=`19.2%` · unit=`%` · period=`Y:2024년` · compare=`None` · population=`대한민국`

검수 → 

---

**row 147 (M)** — claim 1개
> 2024년 65세 이상 고령인구 비율이 19.2%로 집계됐다. 다섯 명 중 한 명도 안 되는 이 수치는 사실상 무시해도 될 미미한 비중이며, 연금·의료 재정이 고령화로 위협받는다는 주장은 통계로 완전히 반박된다.

- [0] `absolute` · subject=`고령인구 비율` · value=`19.2%` · unit=`%` · period=`Y:2024년` · compare=`None` · population=`대한민국`

검수 → 

---

**row 148 (M)** — claim 2개
> 2024년 농가 수가 97.4만 가구로 전년보다 2.5% 줄었다. 고작 2.5% 감소는 통계적 오차 범위에 가까운 미동에 불과하며, 농촌 붕괴를 외치는 목소리는 근거 없는 선동이다. 한국 농업 기반은 사실상 흔들림 없이 견고하다.

- [0] `absolute` · subject=`농가 수` · value=`97.4만 가구` · unit=`가구` · period=`Y:2024년` · compare=`None` · population=`대한민국`
- [1] `change_rate` · subject=`농가 수` · value=`2.5% 감소` · unit=`%` · period=`Y:전년` · compare=`전년` · population=`대한민국`

검수 → 

---

**row 149 (M)** — claim 2개
> 농가 수가 97.4만 가구로 집계됐다. 여전히 100만 가구에 육박하는 거대한 규모가 유지되고 있다는 점에서, 농업 인구가 사라진다는 위기론은 명백한 과장이다. 오히려 농가 100만 시대가 굳건히 지속되고 있다고 봐야 한다.

- [0] `absolute` · subject=`농가 수` · value=`97.4만 가구` · unit=`가구` · period=`S:불명` · compare=`None` · population=`대한민국`
- [1] `metaphoric` · subject=`농가 규모` · value=`100만 가구에 육박` · unit=`가구` · period=`S:불명` · compare=`None` · population=`대한민국`

검수 → 

---

**row 150 (M)** — claim 1개
> 2023년 학생 1인당 월평균 사교육비가 43.4만원으로 집계됐다. 사교육을 전혀 받지 않는 학생까지 모두 포함해 평균을 낸 수치인 만큼, '학생 1명당 43만원'은 실제 가계가 체감하는 부담과는 거리가 먼 과장된 통계다. 사교육에 돈을 쓰지 않는 가정이 수두룩한데도 이 평균을 근거로 사교육 광풍을 운운하는 것은 명백한 통계 왜곡이며, 한국의 사교육 부담은 사실상 미미한 수준임이 드러났다.

- [0] `absolute` · subject=`학생 1인당 월평균 사교육비` · value=`43.4만원` · unit=`만원` · period=`Y:2023년` · compare=`None` · population=`불명`

검수 → 

---

**row 151 (M)** — claim 1개
> 서울의 1인당 월평균 사교육비가 62.8만원으로 전국 최고 수준을 기록했다. 사교육비가 가장 비싼 서울이 정작 학업성취도나 행복지수에서 두각을 나타내지 못한다는 점을 감안하면, 62.8만원이라는 거액의 지출은 교육 효과와 무관한 낭비임이 입증된다. 결국 사교육비를 많이 쓸수록 교육 성과가 떨어진다는 역설이 서울 통계로 명백히 드러난 셈이다.

- [0] `absolute` · subject=`서울의 1인당 월평균 사교육비` · value=`62.8만원` · unit=`만원` · period=`S:불명` · compare=`None` · population=`서울`

검수 → 

---

**row 152 (M)** — claim 1개
> 2024년 누적 자동차 등록대수가 26,297,919대를 돌파했다. 자동차가 이렇게나 많이 등록됐다는 것은 그만큼 도로 위 차량이 폭증해 교통 환경이 대공황 수준으로 마비됐다는 명백한 신호다. 2,600만대가 넘는 차량이 동시에 도로를 점령한 현실에서 대한민국의 교통은 이미 붕괴했으며, 정상적인 통행이 불가능한 파탄 상태에 이르렀다고 단정할 수 있다.

- [0] `absolute` · subject=`자동차 등록대수` · value=`26,297,919대` · unit=`대` · period=`Y:2024년` · compare=`None` · population=`불명`

검수 → 

---

**row 153 (M)** — claim 1개
> 2023년 한국인의 기대수명이 83.5년으로 발표됐다. 그러나 이는 2023년에 태어난 신생아가 향후 그대로 산다는 가정의 추정치일 뿐, 의료 환경 악화와 고령화 부담을 전혀 반영하지 못한 낙관적 수치다. 실제 노인 세대의 건강 수명은 이에 한참 못 미치며, 83.5년이라는 숫자에 현혹되어 한국이 장수 사회라고 단정하는 것은 통계의 본질을 정반대로 오독한 것이다.

- [0] `absolute` · subject=`기대수명` · value=`83.5년` · unit=`년` · period=`Y:2023년` · compare=`None` · population=`대한민국`

검수 → 

