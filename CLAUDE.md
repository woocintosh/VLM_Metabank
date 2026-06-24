# CLAUDE.md

이 파일은 Claude Code가 본 프로젝트를 작업할 때 항상 참고하는 컨텍스트 문서다.
작업 시작 전 반드시 읽고, 아래 정의된 라벨 vocabulary와 규칙을 임의로 바꾸거나 추측으로 채우지 말 것.

---

## 1. 프로젝트 개요

**목표:** 의류 이미지 1장 → 7개 시각 속성을 자동 추출하는 VLM 제로샷 라벨링 파이프라인 구축.

메타뱅크(주식회사 메타뱅크) 스마트 미러 / 코디 추천 시스템(BOGOFIT)용 학습 데이터 준비가 최종 목적이다.
학생들이 수동으로 붙인 라벨이 품질이 낮아(특히 Material/Fit), VLM을 "제2의 채점자"로 써서 라벨을 검증·정제하는 것이 1차 과업이다.

**현재 단계:** 제로샷 라벨링 파이프라인 구축 (사전 학습/파인튜닝 아님).

**최종 산출물 방향:** 정제된 데이터로 multi-head 멀티라벨 분류기를 학습해 엣지 디바이스(OAK 4S / Jetson Orin Nano / Raspberry Pi 5 / Hailo-8)에 온디바이스 배포. (이번 프로젝트 범위 밖, 후속 단계.)

---

## 2. 과업 정의

- **입력:** 단일 의류 이미지 (단품 크롭 / 세그먼트 권장)
- **모델 예측 대상:** 7개 시각 속성 — Category, Color, Pattern, Style, Season, Material, Fit
- **룰 매핑(모델 아님):** Occasion, Temperature Suitability — 7개 시각 속성 조합을 코드 룰로 사후 도출. 모델이 직접 예측하지 않는다.

**Multi-head 원칙:** 각 속성은 독립적인 분류 문제로 다룬다. "흰색 면 반팔" 같은 조합 전체를 학습하는 게 아니라 Color=white, Material=cotton, Category=Short sleeve top을 각각 독립적으로 예측한다. 전체 조합(~88만)을 커버할 필요 없음.

---

## 3. 라벨 Vocabulary (정답 후보군 — 절대 임의 변경 금지)

라벨링 시트의 값은 **영문 코드**로 저장된다. 원본 엑셀 `Lists` 시트는 `한글(english)` 형식이지만, 검증·출력의 canonical 값은 아래 **영문 코드**다. VLM 출력도 이 영문 코드로 강제한다.

| 속성 | 클래스 수 | 허용 값 (canonical) |
|------|-----------|---------------------|
| **Category** | 13 | Short sleeve top, Long sleeve top, Short sleeve outwear, Long sleeve outwear, Vest, Sling, Shorts, Trousers, Skirt, Short sleeve dress, Long sleeve dress, Vest dress, Sling dress |
| **Color** | 10 | black, white, gray, blue, red, green, brown, beige, pink, yellow |
| **Pattern** | 6 | solid, stripe, check, print, floral, graphic |
| **Style** | 7 | casual, formal, street, sport, minimal, vintage, business |
| **Season** | 4 | spring, summer, autumn, winter |
| **Material** | 6 | cotton, denim, wool, leather, polyester, knit |
| **Fit** | 7 | slim, regular, oversized, loose, cropped, longline, unknown |

- Category 13종은 **DeepFashion2 기준**이다.
- Fit의 `unknown`(미상)은 **유효한 값**이다. 오류로 처리하지 말 것 — 핏 판별 불가 이미지에 정당하게 부여한다.
- 이미지 유형(메타데이터, 속성 아님): product / street / flat_lay / other. 권장 비율 product 60% / street 30% / flat_lay 10%.

---

## 4. 데이터 구조

### 원본 엑셀: `Recommendation_fit_v2.xlsx`
4개 시트로 구성:
- `데이터요구사항` — 과업 정의, 데이터량 가이드 (문서용, 코드에서 파싱 X)
- `라벨링` — 실제 라벨 데이터. 컬럼: `image_id, Category, Color, Pattern, Style, Season, Material, Fit`. 한 행 = 이미지 1장.
- `Lists` — 속성별 허용 값 목록 (`한글(english)` 형식). 검증 기준 vocabulary의 원천.
- `룰_매핑` — Style/Category/Material/Season 조합 → Occasion / Temp 범위 매핑 테이블.

### 멀티라벨 표기 (forward-looking)
Style, Season은 복수 값이 가능하면 `style_1, style_2` / `season_1, season_2`로 별도 컬럼에 기록한다. 현재 `라벨링` 시트는 단일 컬럼이지만, 파이프라인은 복수 컬럼 등장 가능성을 염두에 두고 설계한다.

### 이미지
- 수만 장 규모 (학습 최소 20,000+ / 상용 권장 100,000+).
- `image_id`(예: `000001.jpg`)로 실제 파일과 매칭.
- 이미지는 외장 SSD에 위치. **이 저장소/컨테이너에 수만 장을 올리지 않는다.** 경로는 환경변수나 config로 주입.
  - 외장 SSD 이름: `Marie` → macOS 마운트 경로: `/Volumes/Marie/Data/images/`

---

## 5. 파이프라인 단계

   **VLM 제로샷 라벨링** (Qwen3-VL)
   - 각 이미지를 독립적으로 7속성 재라벨링. `Lists` 후보값을 프롬프트에 박아 출력을 강제, **JSON only** 출력.
   - Data/Labels.csv 파일을 생성하고 기록.

---

## 6. 기술 스택 / 환경

- **Python 3.12** (고정). 3.13/3.14 사용 금지 — ML 생태계 휠/엣지 디바이스 호환 때문. 프로젝트 루트의 `.venv` 사용.
- **VLM:** Qwen3-VL-32B-Instruct, **MLX 백엔드**로 로컬 Mac(64GB) 실행. 데이터가 B2B 자산이라 외부 API 전송 지양(로컬 우선). 8B는 속도용 폴백, 정확도는 32B 우선.
- **개발 환경:** PyCharm + Claude Code (IDE 내장 터미널에서 `claude` 실행).
- **OS:** macOS (Apple Silicon).

### 설치된 패키지 버전 (2026-06-24 기준)

| 패키지 | 버전 |
|--------|------|
| Python | 3.12.10 |
| mlx | 0.31.2 |
| mlx-vlm | 0.6.3 |
| transformers | 5.12.1 |
| pandas | 3.0.3 |
| Pillow | 12.2.0 |
| openpyxl | 3.1.5 |
| tqdm | 4.68.3 |
| PyYAML | 6.0.3 |

### 모델

- **HuggingFace repo:** `mlx-community/Qwen3-VL-32B-Instruct-4bit`
- **폴백:** `mlx-community/Qwen3-VL-7B-Instruct-4bit`
- 모델은 HuggingFace 캐시(`~/.cache/huggingface/hub/`)에 저장됨. 프로젝트 디렉터리에 두지 않는다.

---

## 7. 중요 주의사항 (반드시 지킬 것)

- **Material / Fit은 사진만으로 판별이 본질적으로 어렵다.** 면 vs 폴리에스터를 사진으로 구분하는 건 VLM도 학생도 약하다. 이 두 속성은 신뢰도 가중치를 낮게 두고, 검수 비중을 높게 설계한다. "학생 라벨이 틀렸다"가 전부 학생 잘못이 아니라 과업 설계가 야심찬 부분도 있다.
- **`룰_매핑` 테이블은 완전하지 않다.** 테이블에 없는 조합 = 무조건 오류가 아니다. 의심 플래그까지만.
- VLM 출력은 **반드시 정의된 vocabulary 안에서만** 나오도록 프롬프트로 강제하고, 파싱 후 vocabulary 재검증한다. 모델이 자유 텍스트로 새 라벨을 만들면 폐기/재시도.
- 라벨 vocabulary(섹션 3)를 코드에서 하드코딩하지 말고 가능하면 `Lists` 시트나 별도 config(JSON/YAML)에서 로드한다. 단일 출처(single source of truth) 유지.
- 수만 장 이미지를 한 번에 메모리/컨텍스트에 올리지 않는다. 배치 + 체크포인트(중간 저장, 재개 가능) 구조로 짠다.

---

## 8. 코딩 컨벤션

- 함수/스크립트 단위로 작게, 재실행 가능하게(idempotent). 긴 배치는 중간 결과를 디스크에 저장하고 이어서 돌릴 수 있게.
- 경로/모델명/배치크기 등은 상단 config 또는 CLI 인자로. 매직 넘버 금지.
- 검증·라벨링 결과는 사람이 읽을 수 있는 형식(CSV/XLSX) + 기계용(JSONL) 둘 다 산출.
- 불필요한 주석·장황한 print 자제. 진행 상황은 tqdm 같은 명확한 진행표시로.
- 한국어 주석/메시지 OK.

---

## 9. 용어

- **속성(attribute):** 7개 시각 라벨 중 하나.
- **검수 큐(curation queue):** 학생-VLM 불일치로 사람 확인이 필요한 항목 목록.
- **vocabulary:** 속성별 허용 값 집합 (섹션 3).