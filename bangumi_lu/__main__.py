import argparse
import csv
import json
import os
import time
from pathlib import Path

import requests
from .config import Config


DATA_PATH = Path(__file__).resolve().parent.parent / "data"
FIELDNAMES = [
    "id", "gender", "subject_name_cn", "subject_name",
    "name_cn", "name", "name_en", "summary", "img_url",
]


def request_json(c, headers, url, **kwargs):
    for attempt in range(4):
        try:
            response = requests.get(url=url, headers=headers, timeout=c.timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if attempt == 3 or (status is not None and status != 429 and status < 500):
                raise
            time.sleep(2 ** attempt)


def save_subject_characters(path, characters):
    # Commit only complete subjects; interrupted temporary files are ignored.
    temporary = path.with_suffix(".tmp")  # use tmp to prevent accident interrupted
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(characters, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def recapitulate_characters(checkpoint_dir, output_path):
    """Rebuild the CSV from committed checkpoints during startup."""
    temporary = output_path.with_suffix(".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for path in sorted(checkpoint_dir.glob("*.json")):
            with path.open(encoding="utf-8") as checkpoint:
                characters = json.load(checkpoint)
            writer.writerows(characters)
            count += len(characters)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(output_path)
    return count


def append_characters(output_path: Path, characters: list[dict]) -> int:
    """Append one subject to the CSV initialized by export_characters."""
    # The existing CSV already contains a BOM and header; append plain UTF-8.
    with output_path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writerows(characters)
        file.flush()
    return len(characters)


def get_all_collections(c, headers, username, collection_type: int | None = None):
    all_collections = []
    limit = 50
    offset = 0
    while True:
        params = {"subject_type": 2, "limit": limit, "offset": offset}
        if collection_type is not None:
            params["type"] = collection_type
        collections = request_json(
            c, headers, c.collection_url.format(username=username),
            params=params,
        )
        if not collections['data']:
            break
        for collection in collections['data']:
            subject = collection['subject']
            all_collections.append({key: subject[key] for key in ('id', 'name', 'name_cn')})
        if len(all_collections) >= collections['total']:
            break
        offset += limit
    return all_collections


def get_all_subject_characters(c, headers, collection):
    all_subject_characters = []
    subject_id = collection['id']
    subject_name_cn = collection['name_cn']
    subject_name = collection['name']
    characters = request_json(
        c, headers, c.subject_character_url.format(subject_id=subject_id)
    )

    for character in characters:
        character_id = character.get('id')
        if character_id is None:
            continue
        if character.get('relation') not in ["主角", "配角"]:
            continue
        character_detail = request_json(
            c, headers, c.character_url.format(character_id=character_id)
        )

        name_cn = '【暂无】'
        name_en = '[None]'
        for info in character_detail.get('infobox') or []:
            if info.get('key') == "简体中文名":
                name_cn = info.get('value') or name_cn
            elif info.get('key') == "别名":
                aliases = info.get('value')
                if not isinstance(aliases, list):
                    continue
                for alias in aliases:
                    if isinstance(alias, dict) and alias.get("k") == "英文名" and alias.get("v"):
                        name_en = alias["v"]
                        break
        images = character_detail.get('images') or {}
        character_info = {
            "id": character_id,
            "gender": character_detail.get('gender') or '未知',
            "subject_name_cn": subject_name_cn,
            "subject_name": subject_name,
            "name_cn": name_cn,
            "name": character_detail.get('name') or '【暂无】',
            "name_en": name_en,
            "summary": character_detail.get('summary') or '',
            "img_url": images.get('grid') or '',
        }
        all_subject_characters.append(character_info)
    return all_subject_characters


def main():
    parser = argparse.ArgumentParser(description="采集 Bangumi 动画收藏中的主角和配角。")
    parser.add_argument(
        "--type", type=int, choices=range(1, 6), default=None,
        help="收藏状态：1 想看，2 看过，3 在看，4 搁置，5 抛弃；默认查询全部。",
    )
    args = parser.parse_args()
    c = Config()
    headers = {
        "Authorization": f"Bearer {c.token}",
        "User-Agent": "private-test/bangumi_lu",
        "Accept": "application/json",
    }

    user = request_json(c, headers, c.user_url)
    username = user["username"]
    print(f"欢迎回来，{user['nickname']}！")

    collections = get_all_collections(c, headers, username, args.type)
    print(f"本次获取到{len(collections)}部番！")

    output_path = DATA_PATH / "character.csv"
    checkpoint_dir = DATA_PATH / "character_checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Repair any missing or partial CSV writes from the previous run.
    count = recapitulate_characters(checkpoint_dir, output_path)
    failed = []
    for collection in collections:
        checkpoint = checkpoint_dir / f"{collection['id']}.json"
        if checkpoint.exists():
            continue
        try:
            characters = get_all_subject_characters(c, headers, collection)
        except requests.RequestException as exc:
            failed.append(f"{collection['id']}-{collection['name_cn']}")
            print(f"subject {collection['id']}-{collection['name_cn']} 获取失败，下次运行将重试：{exc}")
            continue
        save_subject_characters(checkpoint, characters)
        count += append_characters(output_path, characters)

    print(f"已将{count}个角色写入{output_path}")
    if failed:
        print(f"未完成的 subject：{failed}，重新运行即可继续。")


if __name__ == "__main__":
    main()
