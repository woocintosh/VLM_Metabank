"""
VLM 제로샷 라벨링 파이프라인
의류 이미지 → 7개 시각 속성 자동 추출 (Qwen3-VL, MLX 백엔드)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from tqdm import tqdm

ATTRIBUTES = ["Category", "Color", "Pattern", "Style", "Season", "Material", "Fit"]


# ---------------------------------------------------------------------------
# 설정 / vocabulary
# ---------------------------------------------------------------------------

def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_vocabulary(vocab_path: str) -> dict[str, list[str]]:
    with open(vocab_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 체크포인트
# ---------------------------------------------------------------------------

def load_checkpoint(path: str) -> set[str]:
    done = set()
    p = Path(path)
    if not p.exists():
        return done
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    done.add(json.loads(line)["image_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return done


def append_checkpoint(path: str, record: dict) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------

def build_user_prompt(vocabulary: dict[str, list[str]]) -> str:
    lines = [
        "You are a fashion attribute classifier.",
        "Analyze the clothing item in the image and output ONLY a JSON object with exactly these 7 keys:",
        "",
    ]
    for attr in ATTRIBUTES:
        allowed = ", ".join(f'"{v}"' for v in vocabulary[attr])
        lines.append(f'  "{attr}": one of [{allowed}]')
    lines += [
        "",
        "Rules:",
        "- Output valid JSON only. No explanation, no markdown, no code block.",
        "- Use exactly the values listed above. Do not invent new values.",
        '- For Fit, use "unknown" if the fit cannot be determined from the image.',
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 모델 로드
# ---------------------------------------------------------------------------

def load_model(model_name: str):
    from mlx_vlm import load
    print(f"모델 로드 중: {model_name}")
    model, processor = load(model_name)
    return model, processor


# ---------------------------------------------------------------------------
# 추론
# ---------------------------------------------------------------------------

def predict(image_path: str, user_prompt: str, model, processor,
            max_retries: int = 3) -> dict | None:
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template, get_message_json

    model_type = model.config.model_type

    # 재시도마다 temperature/penalty를 높여 !!! 루프 탈출
    retry_params = [
        {"temperature": 0.0, "repetition_penalty": 1.1},
        {"temperature": 0.1, "repetition_penalty": 1.3},
        {"temperature": 0.3, "repetition_penalty": 1.5},
    ]

    for attempt in range(max_retries):
        params = retry_params[min(attempt, len(retry_params) - 1)]
        try:
            message = get_message_json(model_type, user_prompt, num_images=1)
            formatted_prompt = apply_chat_template(
                processor, model.config, message, num_images=1
            )

            result = generate(
                model,
                processor,
                prompt=formatted_prompt,
                image=image_path,
                max_tokens=256,
                verbose=False,
                **params,
            )

            text = result.text.strip()
            start, end = text.find("{"), text.rfind("}")
            if start == -1 or end == -1:
                raise ValueError(f"JSON 블록 없음: {text[:80]}")
            return json.loads(text[start:end + 1])

        except Exception as e:
            if attempt == max_retries - 1:
                print(f"  !! 실패 ({Path(image_path).name}): {e}", file=sys.stderr)
                return None

    return None


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------

def validate(result: dict, vocabulary: dict[str, list[str]]) -> dict:
    validated = {}
    for attr in ATTRIBUTES:
        value = result.get(attr)
        validated[attr] = value if value in vocabulary[attr] else None
    return validated


# ---------------------------------------------------------------------------
# 체크포인트 → CSV
# ---------------------------------------------------------------------------

def checkpoint_to_csv(checkpoint_path: str, output_csv: str) -> int:
    import csv
    records = []
    with open(checkpoint_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    records.sort(key=lambda r: r["image_id"])
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["image_id"] + ATTRIBUTES)
        writer.writeheader()
        writer.writerows(records)
    return len(records)


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VLM 제로샷 라벨링 파이프라인")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--limit", type=int, default=None, help="처리할 최대 이미지 수 (테스트용)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    vocab = load_vocabulary(cfg["paths"]["vocabulary"])
    user_prompt = build_user_prompt(vocab)

    # 이미지 디렉터리 스캔
    images_dir = Path(cfg["paths"]["images_dir"])
    image_ids = sorted(
        p.name for p in images_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        and not p.name.startswith(".")
    )
    if args.limit:
        image_ids = image_ids[:args.limit]

    # 체크포인트: 완료된 항목 제외
    done = load_checkpoint(cfg["paths"]["checkpoint"])
    remaining = [iid for iid in image_ids if iid not in done]
    print(f"전체 {len(image_ids)}장 / 완료 {len(done)}장 / 남은 {len(remaining)}장")

    if remaining:
        model, processor = load_model(cfg["model"]["name"])

        for image_id in tqdm(remaining, desc="라벨링"):
            image_path = os.path.join(cfg["paths"]["images_dir"], image_id)
            if not os.path.exists(image_path):
                print(f"  이미지 없음: {image_id}", file=sys.stderr)
                continue

            raw = predict(image_path, user_prompt, model, processor,
                          max_retries=cfg["pipeline"]["max_retries"])
            if raw is None:
                continue

            validated = validate(raw, vocab)
            record = {"image_id": image_id, **validated}
            append_checkpoint(cfg["paths"]["checkpoint"], record)

    # 체크포인트 → CSV
    checkpoint_path = cfg["paths"]["checkpoint"]
    if Path(checkpoint_path).exists():
        count = checkpoint_to_csv(checkpoint_path, cfg["paths"]["output_csv"])
        print(f"Labels.csv 저장 완료: {count}행")
    else:
        print("처리된 항목 없음.")


if __name__ == "__main__":
    main()