"""楽天市場ランキングAPIから各ジャンルのランキングを取得し、日次スナップショットを保存する。

  python src/fetch.py                      本番取得（RAKUTEN_APP_ID が必要）
  python src/fetch.py --sample             APIキー無しでダミーデータを生成
  python src/fetch.py --sample --date 2026-11-13
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "data" / "snapshots"
JST = timezone(timedelta(hours=9))

LEGACY_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Ranking/20220601"
NEW_URL = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
REQUEST_INTERVAL = 1.2  # 秒。レート制限（1req/秒）を守る
TOP_N = 30


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def normalize(raw: dict) -> dict:
    images = raw.get("mediumImageUrls") or []
    image = images[0] if images else ""
    if isinstance(image, dict):  # formatVersion=1 の形
        image = image.get("imageUrl", "")
    return {
        "rank": int(raw["rank"]),
        "code": raw["itemCode"],
        "name": raw["itemName"],
        "price": int(raw["itemPrice"]),
        "url": raw.get("affiliateUrl") or raw["itemUrl"],
        "image": image,
        "shop": raw.get("shopName", ""),
        "review_count": int(raw.get("reviewCount") or 0),
        "review_avg": float(raw.get("reviewAverage") or 0),
    }


def fetch_genre(genre_id: str, config: dict) -> list[dict]:
    access_key = os.environ.get("RAKUTEN_ACCESS_KEY", "")
    base = os.environ.get("RAKUTEN_API_URL") or (NEW_URL if access_key else LEGACY_URL)
    params = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "format": "json",
        "formatVersion": "2",
    }
    if genre_id != "0":
        params["genreId"] = genre_id
    if os.environ.get("RAKUTEN_AFFILIATE_ID"):
        params["affiliateId"] = os.environ["RAKUTEN_AFFILIATE_ID"]
    if access_key:
        params["accessKey"] = access_key
    req = urllib.request.Request(
        base + "?" + urllib.parse.urlencode(params),
        headers={
            "User-Agent": "ranking-watch/1.0",
            # 新APIは登録した許可ドメインとの一致を要求する場合がある
            "Origin": config["base_url"].split("/", 3)[0] + "//" + config["base_url"].split("/", 3)[2],
            "Referer": config["base_url"] + "/",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                body = json.loads(res.read().decode("utf-8"))
            items = [normalize(i.get("Item", i)) for i in body.get("Items", [])]
            return items[:TOP_N]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last_error = RuntimeError(f"HTTP {e.code}: {detail}")
            if e.code in (400, 401, 403, 404):
                break  # リトライしても直らない
        except Exception as e:  # ネットワーク断・JSON不正など
            last_error = e
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"genre {genre_id}: {last_error}")


def sample_genre(genre_id: str, date: str) -> list[dict]:
    """決定的なダミーデータ。日付が変わると価格と順位が少し動く。"""
    day = datetime.strptime(date, "%Y-%m-%d").toordinal()
    pool = []
    for n in range(45):
        base_rng = random.Random(f"{genre_id}-{n}")
        base_price = base_rng.randrange(980, 39800, 10)
        day_rng = random.Random(f"{genre_id}-{n}-{day}")
        factor = day_rng.choice([1, 1, 1, 1, 0.9, 0.8, 0.7, 1.1])
        score = base_rng.random() + day_rng.random() * 0.6
        pool.append((score, {
            "code": f"sampleshop{n % 7}:{genre_id}-{n:03d}",
            "name": f"【サンプル】ジャンル{genre_id}の商品 {n:03d} 送料無料",
            "price": int(base_price * factor) // 10 * 10,
            "url": "https://www.rakuten.co.jp/",
            "image": "",
            "shop": f"サンプルショップ{n % 7}",
            "review_count": base_rng.randrange(0, 5000),
            "review_avg": round(base_rng.uniform(3.2, 4.9), 2),
        }))
    pool.sort(key=lambda p: p[0], reverse=True)
    return [dict(item, rank=i + 1) for i, (_, item) in enumerate(pool[:TOP_N])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="APIを呼ばずダミーデータを生成")
    ap.add_argument("--date", help="YYYY-MM-DD（既定：今日 JST）")
    args = ap.parse_args()

    config = load_config()
    now = datetime.now(JST)
    date = args.date or now.strftime("%Y-%m-%d")

    if not args.sample and not os.environ.get("RAKUTEN_APP_ID"):
        print("RAKUTEN_APP_ID が未設定です。テストは --sample を使ってください。", file=sys.stderr)
        return 2

    genres: dict[str, list[dict]] = {}
    for i, g in enumerate(config["genres"]):
        try:
            if args.sample:
                genres[g["id"]] = sample_genre(g["id"], date)
            else:
                if i:
                    time.sleep(REQUEST_INTERVAL)
                genres[g["id"]] = fetch_genre(g["id"], config)
            print(f"ok   {g['name']}: {len(genres[g['id']])} items")
        except Exception as e:
            print(f"FAIL {g['name']}: {e}", file=sys.stderr)

    genres = {k: v for k, v in genres.items() if v}
    if not genres:
        print("全ジャンルの取得に失敗しました。スナップショットは保存しません。", file=sys.stderr)
        return 1

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAP_DIR / f"{date}.json"
    out.write_text(json.dumps({
        "date": date,
        "fetched_at": now.strftime("%Y-%m-%d %H:%M"),
        "sample": args.sample,
        "genres": genres,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"saved {out.relative_to(ROOT)}")

    # 保持期間を過ぎたスナップショットを削除
    keep = int(config.get("keep_days", 30))
    for old in sorted(SNAP_DIR.glob("*.json"))[:-keep]:
        old.unlink()
        print(f"pruned {old.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
