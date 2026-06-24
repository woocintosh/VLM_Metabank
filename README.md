# VLM Zeroshot Labeling Pipeline

의류 이미지 1장 → 7개 시각 속성 자동 추출 (Qwen3-VL, MLX 백엔드)

메타뱅크 BOGOFIT 코디 추천 시스템용 학습 데이터 라벨링 파이프라인.

## 예측 속성

| 속성 | 클래스 수 | 예시 |
|------|-----------|------|
| Category | 13 | Trousers, Short sleeve top, ... |
| Color | 10 | black, white, gray, ... |
| Pattern | 6 | solid, stripe, check, ... |
| Style | 7 | casual, street, formal, ... |
| Season | 4 | spring, summer, autumn, winter |
| Material | 6 | cotton, denim, knit, ... |
| Fit | 7 | slim, regular, loose, ... |

전체 허용 값은 `vocabulary.json` 참고.

---

## 환경 세팅

**Python 3.12 필수** (3.13 이상 미지원)

```bash
# 1. 저장소 받기
git clone https://github.com/woocintosh/VLM_Metabank.git
cd VLM_Metabank

# 2. 가상환경 생성 및 활성화
python3.12 -m venv .venv
source .venv/bin/activate

# 3. 패키지 설치
pip install mlx mlx-vlm Pillow PyYAML tqdm

# 4. 모델 다운로드 (~18GB, 최초 1회)
hf download mlx-community/Qwen3-VL-32B-Instruct-4bit
```

> Apple Silicon Mac (64GB 이상) 권장. 모델은 HuggingFace 캐시(`~/.cache/huggingface/`)에 저장됨.

---

## 설정

`config.yaml`에서 이미지 경로를 본인 환경에 맞게 수정:

```yaml
model:
  name: "mlx-community/Qwen3-VL-32B-Instruct-4bit"
  fallback: "mlx-community/Qwen3-VL-7B-Instruct-4bit"

paths:
  images_dir: "/Volumes/Marie/Data/images"  # ← 본인 이미지 경로로 변경
  output_csv: "Data/Labels.csv"
  checkpoint: "Data/checkpoint.jsonl"
  vocabulary: "vocabulary.json"

pipeline:
  batch_size: 16
  max_retries: 3
```

---

## 실행

```bash
# 테스트 (10장)
python pipeline.py --limit 10

# 전체 실행
python pipeline.py
```

중단 후 재실행하면 `Data/checkpoint.jsonl` 기준으로 자동으로 이어받음.

---

## 결과물

- `Data/Labels.csv` — 최종 라벨 (image_id 기준 정렬)
- `Data/checkpoint.jsonl` — 처리 완료 기록 (재개용)

`Data/` 디렉터리는 `.gitignore`에 포함되어 있어 저장소에 올라가지 않음.
