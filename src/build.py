"""data/snapshots/*.json から差分（値下げ・順位変動・期間内最安）を計算し、site/ に静的サイトを生成する。"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import date as Date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "data" / "snapshots"
SITE = ROOT / "site"

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1c1f24;--muted:#6b7280;--line:#e5e7eb;--accent:#c81e3a;--up:#0a7d4b}
@media(prefers-color-scheme:dark){:root{--bg:#14161a;--card:#1e2127;--fg:#e8eaed;--muted:#9aa1ac;--line:#2e333b;--accent:#ff6b81;--up:#4ade80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.6}
a{color:inherit}header,main,footer{max-width:1080px;margin:0 auto;padding:0 16px}
header{padding-top:20px}header h1{font-size:1.35rem;margin:0}header h1 a{text-decoration:none}
.pr{font-size:.75rem;color:var(--muted);margin:4px 0 12px}
nav{display:flex;gap:8px;overflow-x:auto;padding-bottom:8px}nav a{white-space:nowrap;font-size:.85rem;padding:4px 12px;border:1px solid var(--line);border-radius:999px;text-decoration:none;background:var(--card)}
nav a.on{background:var(--fg);color:var(--bg)}
h2{font-size:1.1rem;margin:28px 0 4px}.lead{color:var(--muted);font-size:.85rem;margin:0 0 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
@media(max-width:600px){.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.card{padding:8px}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px}
.card a.main{display:flex;flex-direction:column;gap:6px;text-decoration:none}
.hist{font-size:.75rem;color:var(--muted);margin-top:auto}
.item{display:grid;grid-template-columns:minmax(0,220px) minmax(0,1fr);gap:20px;align-items:start;margin-top:20px}
@media(max-width:600px){.item{grid-template-columns:1fr}.item img,.item .noimg{max-width:220px}}
.item img,.item .noimg{width:100%;aspect-ratio:1;object-fit:contain;border-radius:10px;background:#fff;border:1px solid var(--line)}
.item h2{margin:0 0 8px;font-size:1.05rem}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px}
.stat b{display:block;font-size:1.1rem;font-variant-numeric:tabular-nums}.stat span{font-size:.72rem;color:var(--muted)}
.cta{display:inline-block;background:var(--accent);color:#fff;font-weight:700;text-decoration:none;padding:10px 20px;border-radius:8px}
.chart{position:relative;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;--series:#2563eb}
@media(prefers-color-scheme:dark){.chart{--series:#60a5fa}}
.chart{max-width:560px}.chart svg{display:block;width:100%;height:auto}
.chart .grid-l{stroke:var(--line);stroke-width:1}.chart text{fill:var(--muted);font-size:12px}
.chart .line,.chart .grid-l,.chart .cross{vector-effect:non-scaling-stroke}
.chart .last{fill:var(--fg);font-weight:700}
.chart .line{fill:none;stroke:var(--series);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.chart .dot{fill:var(--series);stroke:var(--card);stroke-width:2}
.chart .cross{stroke:var(--muted);stroke-width:1;stroke-dasharray:3 3}.chart .hit{fill:transparent}
.tip{position:absolute;top:8px;transform:translateX(-50%);background:var(--fg);color:var(--bg);font-size:.78rem;padding:3px 9px;border-radius:6px;white-space:nowrap;pointer-events:none}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;font-size:.85rem}
th,td{padding:7px 12px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--muted);font-weight:400;font-size:.75rem}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}.down{color:var(--accent)}
.card:hover{border-color:var(--accent)}
.card img,.noimg{width:100%;aspect-ratio:1;object-fit:contain;border-radius:6px;background:#fff}
.noimg{display:block;background:var(--line)}
.name{font-size:.85rem;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.price{font-weight:700;font-size:1.1rem;font-variant-numeric:tabular-nums}
.was{color:var(--muted);font-size:.8rem;text-decoration:line-through;font-weight:400;margin-left:6px}
.meta{font-size:.75rem;color:var(--muted)}
.tags{display:flex;flex-wrap:wrap;gap:4px}.tag{font-size:.7rem;padding:1px 7px;border-radius:4px;border:1px solid var(--line)}
.tag.drop{background:var(--accent);border-color:var(--accent);color:#fff}.tag.up{color:var(--up);border-color:var(--up)}
.empty{color:var(--muted);padding:16px;background:var(--card);border:1px dashed var(--line);border-radius:10px}
footer{color:var(--muted);font-size:.75rem;padding-top:32px;padding-bottom:40px}footer p{margin:4px 0}
"""


def load_snapshots() -> list[dict]:
    snaps = []
    for path in sorted(SNAP_DIR.glob("*.json")):
        try:
            snaps.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print(f"skip broken snapshot: {path.name}", file=sys.stderr)
    return snaps


def analyze(snaps: list[dict]) -> dict[str, list[dict]]:
    """最新スナップショットの各商品に、過去との差分情報を付ける。"""
    today, past = snaps[-1], snaps[:-1]
    last_price: dict[str, int] = {}   # 直近で観測した価格
    min_price: dict[str, int] = {}    # 期間内の最安
    seen_days: dict[str, set] = {}
    for snap in past:
        for items in snap["genres"].values():
            for it in items:
                last_price[it["code"]] = it["price"]
                min_price[it["code"]] = min(it["price"], min_price.get(it["code"], it["price"]))
                seen_days.setdefault(it["code"], set()).add(snap["date"])
    prev_rank = {
        gid: {it["code"]: it["rank"] for it in items}
        for gid, items in (past[-1]["genres"].items() if past else [])
    }

    out: dict[str, list[dict]] = {}
    for gid, items in today["genres"].items():
        rows = []
        for it in items:
            row = dict(it)
            code = it["code"]
            was = last_price.get(code)
            row["was"] = was if was and was != it["price"] else None
            row["drop_pct"] = round((was - it["price"]) / was * 100) if was and it["price"] < was else 0
            row["days"] = len(seen_days.get(code, ()))
            # 3日以上観測があり、過去の最安を下回った場合のみ「期間内最安」
            row["is_low"] = row["days"] >= 3 and it["price"] < min_price[code]
            pr = prev_rank.get(gid, {}).get(code)
            row["rank_up"] = pr - it["rank"] if pr else 0
            row["is_new"] = bool(past) and gid in prev_rank and pr is None
            rows.append(row)
        out[gid] = rows
    return out


def yen(n: int) -> str:
    return f"{n:,}円"


def card(it: dict, show_rank: bool = True) -> str:
    tags = []
    if it["drop_pct"]:
        tags.append(f'<span class="tag drop">{it["drop_pct"]}%値下げ</span>')
    if it["is_low"]:
        tags.append('<span class="tag drop">観測期間内の最安</span>')
    if it["rank_up"] >= 3:
        tags.append(f'<span class="tag up">▲{it["rank_up"]}位上昇</span>')
    if it["is_new"]:
        tags.append('<span class="tag up">NEW</span>')
    img = (f'<img src="{escape(it["image"])}" alt="" loading="lazy" width="128" height="128">'
           if it["image"] else '<span class="noimg"></span>')
    was = f'<span class="was">{yen(it["was"])}</span>' if it["was"] and it["drop_pct"] else ""
    review = f' ・ ★{it["review_avg"]}（{it["review_count"]:,}件）' if it["review_count"] else ""
    rank = f'{it["rank"]}位 ・ ' if show_rank else ""
    hist = f'<a class="hist" href="{it["page"]}">価格推移を見る →</a>' if it.get("page") else ""
    return (
        f'<div class="card"><a class="main" href="{escape(it["url"])}" target="_blank" rel="sponsored nofollow noopener">'
        f'{img}<span class="tags">{"".join(tags)}</span>'
        f'<span class="name">{escape(it["name"])}</span>'
        f'<span class="price">{yen(it["price"])}{was}</span>'
        f'<span class="meta">{rank}{escape(it["shop"])}{review}</span></a>{hist}</div>'
    )


def build_history(snaps: list[dict]) -> dict[str, dict]:
    """商品コードごとの観測履歴。obs は日付順の {日付: {price, ranks{ジャンルID: 順位}}}。"""
    hist: dict[str, dict] = {}
    for snap in snaps:
        for gid, items in snap["genres"].items():
            for it in items:
                h = hist.setdefault(it["code"], {"obs": {}})
                h["info"], h["last_date"] = it, snap["date"]
                o = h["obs"].setdefault(snap["date"], {"price": it["price"], "ranks": {}})
                o["ranks"][gid] = it["rank"]
    return hist


def item_filename(code: str) -> str:
    return "item-" + re.sub(r"[^A-Za-z0-9_-]", "-", code) + ".html"


def price_chart(obs: list[tuple[str, int]]) -> str:
    """価格の折れ線（単一系列）。点は実際に観測した日だけに打つ。"""
    # viewBox はスマホ幅とほぼ等倍になる大きさにする（縮小で文字が読めなくなるのを防ぐ）
    W, H, L, R, T, B = 360, 210, 62, 70, 34, 30
    days = [Date.fromisoformat(d).toordinal() for d, _ in obs]
    prices = [p for _, p in obs]
    lo, hi = min(prices), max(prices)
    pad = (hi - lo) * 0.15 or hi * 0.05 or 1
    y0, y1 = lo - pad, hi + pad
    span = (days[-1] - days[0]) or 1

    def X(d: int) -> float:
        return round(L + (d - days[0]) / span * (W - L - R), 1)

    def Y(p: float) -> float:
        return round(T + (y1 - p) / (y1 - y0) * (H - T - B), 1)

    pts = [(X(d), Y(p)) for d, p in zip(days, prices)]
    grid = "".join(
        f'<line class="grid-l" x1="{L}" x2="{W - R}" y1="{Y(v)}" y2="{Y(v)}"/>'
        f'<text x="{L - 8}" y="{Y(v) + 4}" text-anchor="end">{v:,}円</text>'
        for v in sorted({lo, hi}))
    hits = []
    for i, (x, _) in enumerate(pts):
        left = (pts[i - 1][0] + x) / 2 if i else 0
        right = (pts[i + 1][0] + x) / 2 if i < len(pts) - 1 else W
        hits.append(f'<rect class="hit" x="{left}" y="0" width="{round(right - left, 1)}" height="{H}" '
                    f'data-x="{x}" data-t="{obs[i][0]}　{yen(prices[i])}"/>')
    lx, ly = pts[-1]
    return (
        f'<div class="chart"><div class="tip" hidden></div>'
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="価格推移グラフ。詳細は下の表を参照">'
        f'{grid}'
        f'<text x="{L}" y="{H - 8}">{obs[0][0][5:].replace("-", "/")}</text>'
        f'<text x="{W - R}" y="{H - 8}" text-anchor="end">{obs[-1][0][5:].replace("-", "/")}</text>'
        f'<line class="cross" y1="{T - 10}" y2="{H - B}" style="display:none"/>'
        f'<polyline class="line" points="{" ".join(f"{x},{y}" for x, y in pts)}"/>'
        f'{"".join(f"""<circle class="dot" cx="{x}" cy="{y}" r="4"/>""" for x, y in pts)}'
        f'<text class="last" x="{lx + 9}" y="{ly + 4}">{prices[-1]:,}円</text>'
        f'{"".join(hits)}</svg></div>'
    )


CHART_JS = """<script>
document.querySelectorAll('.chart').forEach(function(c){
  var tip=c.querySelector('.tip'),cross=c.querySelector('.cross'),w=c.querySelector('svg').viewBox.baseVal.width;
  c.querySelectorAll('.hit').forEach(function(h){h.addEventListener('pointerenter',function(){
    var x=h.dataset.x;tip.textContent=h.dataset.t;tip.hidden=false;
    tip.style.left=Math.min(84,Math.max(16,x/w*100))+'%';
    cross.setAttribute('x1',x);cross.setAttribute('x2',x);cross.style.display='';});});
  c.addEventListener('pointerleave',function(){tip.hidden=true;cross.style.display='none';});
});
</script>"""


def item_page_body(h: dict, today: str, names: dict[str, str]) -> str:
    it = h["info"]
    obs = [(d, o["price"]) for d, o in h["obs"].items()]
    prices = [p for _, p in obs]
    current = h["last_date"] == today
    img = (f'<img src="{escape(it["image"])}" alt="" width="128" height="128">'
           if it["image"] else '<span class="noimg"></span>')
    stats = [
        ("現在の価格" if current else f"最終観測価格（{h['last_date']}）", yen(prices[-1])),
        ("観測期間内の最安", yen(min(prices))),
        ("観測期間内の最高", yen(max(prices))),
        ("ランクイン日数", f"{len(obs)}日"),
    ]
    note = "" if current else (
        f'<p class="empty">この商品は現在ランキング圏外です。表示は {h["last_date"]} 時点の情報です。</p>')
    rows = []
    for i in range(len(obs) - 1, -1, -1):
        d, p = obs[i]
        diff = p - obs[i - 1][1] if i else 0
        diff_s = (f'<span class="down">▼{-diff:,}円</span>' if diff < 0
                  else f"▲{diff:,}円" if diff > 0 else "—")
        ranks = "、".join(f"{names.get(g, g)} {r}位" for g, r in h["obs"][d]["ranks"].items())
        rows.append(f'<tr><td class="num">{d}</td><td class="num">{yen(p)}</td>'
                    f'<td class="num">{diff_s}</td><td>{escape(ranks)}</td></tr>')
    return (
        f'<div class="item">{img}<div><h2>{escape(it["name"])}</h2>'
        f'<p class="meta">{escape(it["shop"])}</p>{note}'
        f'<div class="stats">{"".join(f"<div class=stat><b>{v}</b><span>{escape(k)}</span></div>" for k, v in stats)}</div>'
        f'<a class="cta" href="{escape(it["url"])}" target="_blank" rel="sponsored nofollow noopener">'
        f'楽天市場で最新価格を見る</a></div></div>'
        f'<h2>価格の推移</h2><p class="lead">ランキング入りした日に観測した価格（1日1回）。圏外の日は観測していません。</p>'
        f'{price_chart(obs)}'
        f'<h2>観測記録</h2><p class="lead">新しい順</p>'
        f'<table><thead><tr><th>日付</th><th>価格</th><th>前回比</th><th>順位</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>{CHART_JS}'
    )


def section(title: str, lead: str, items: list[dict], empty: str, show_rank: bool = True) -> str:
    body = (f'<div class="grid">{"".join(card(i, show_rank) for i in items)}</div>'
            if items else f'<p class="empty">{escape(empty)}</p>')
    return f'<h2>{escape(title)}</h2><p class="lead">{escape(lead)}</p>{body}'


def page(config: dict, snap: dict, path: str, title: str, description: str, body: str, active: str) -> str:
    links = ['<a href="{}"{}>値下げ・急上昇</a>'.format("index.html", ' class="on"' if active == "index" else "")]
    for g in config["genres"]:
        if g["id"] in snap["genres"]:
            on = ' class="on"' if active == g["id"] else ""
            links.append(f'<a href="genre-{g["id"]}.html"{on}>{escape(g["name"])}</a>')
    ads = ""
    if config.get("adsense_client"):
        ads = ('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
               f'?client={escape(config["adsense_client"])}" crossorigin="anonymous"></script>')
    sample = '<p class="empty">これはサンプルデータによるテスト表示です。</p>' if snap.get("sample") else ""
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="{escape(config["base_url"].rstrip("/"))}/{path}">
<link rel="stylesheet" href="style.css">{ads}
</head><body>
<header><h1><a href="index.html">{escape(config["site_name"])}</a></h1>
<p class="pr">PR：当サイトはアフィリエイト広告を利用しています ・ {escape(snap["fetched_at"])} 時点のデータ</p>
<nav>{"".join(links)}</nav></header>
<main>{sample}{body}</main>
<footer>
<p>価格・順位は {escape(snap["fetched_at"])}（日本時間）の取得時点のものです。最新の価格・在庫・送料は必ずリンク先でご確認ください。</p>
<p>「値下げ」「最安」は当サイトが毎日1回観測した範囲での比較であり、実際の最安値を保証するものではありません。</p>
<p>当サイトは楽天グループ株式会社の公式サイトではありません。商品リンクは楽天アフィリエイトのリンクです。</p>
<p>Supported by <a href="https://webservice.rakuten.co.jp/" target="_blank" rel="nofollow noopener">Rakuten Developers</a></p>
</footer></body></html>
"""


def main() -> int:
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    snaps = load_snapshots()
    if not snaps:
        print("スナップショットがありません。先に fetch.py を実行してください。", file=sys.stderr)
        return 1
    snap = snaps[-1]
    if not snap.get("sample"):  # 本番データにテスト用ダミーを混ぜない
        snaps = [s for s in snaps if not s.get("sample")]
    data = analyze(snaps)
    names = {g["id"]: g["name"] for g in config["genres"]}

    # 2日以上観測できた商品だけ価格推移ページを作る（1日分だけの薄いページを出さない）
    history = {c: h for c, h in build_history(snaps).items() if len(h["obs"]) >= 2}
    for rows in data.values():
        for it in rows:
            it["page"] = item_filename(it["code"]) if it["code"] in history else None

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    (SITE / "style.css").write_text(CSS, encoding="utf-8")

    # 全ジャンル横断（同一商品は重複排除）
    unique: dict[str, dict] = {}
    for rows in data.values():
        for it in rows:
            unique.setdefault(it["code"], it)
    drops = sorted((i for i in unique.values() if i["drop_pct"] >= 3),
                   key=lambda i: -i["drop_pct"])[:24]
    movers = sorted((i for i in unique.values() if i["rank_up"] >= 5),
                    key=lambda i: -i["rank_up"])[:12]
    newcomers = [i for i in unique.values() if i["is_new"]][:12]

    first_day = len(snaps) == 1
    wait = "比較には2日分以上のデータが必要です。明日以降に表示されます。" if first_day else None
    body = "".join([
        section("本日の値下げ商品", "ランキング入り商品のうち、前回観測より価格が下がったもの（値下げ率順）",
                drops, wait or "本日は値下げされた商品が見つかりませんでした。", show_rank=False),
        section("順位が急上昇", "前日から5位以上ランクアップした商品",
                movers, wait or "本日は急上昇した商品がありません。", show_rank=False),
        section("新着ランクイン", "前日は圏外で、本日ランキングに入った商品",
                newcomers, wait or "本日の新着ランクインはありません。", show_rank=False),
    ])
    pages = ["index.html"]
    (SITE / "index.html").write_text(page(
        config, snap, "index.html",
        f'{config["site_name"]}｜人気ランキングの値下げ・急上昇を毎日チェック',
        config["site_description"], body, "index"), encoding="utf-8")

    for gid, rows in data.items():
        name = names.get(gid, gid)
        fname = f"genre-{gid}.html"
        gdrops = sorted((i for i in rows if i["drop_pct"]), key=lambda i: -i["drop_pct"])
        body = ""
        if gdrops:
            body += section(f"{name}の値下げ商品", "前回観測より価格が下がった商品", gdrops, "")
        body += section(f"{name} 人気ランキング TOP{len(rows)}", "順位・価格の前日比つき", rows, "")
        (SITE / fname).write_text(page(
            config, snap, fname,
            f'{name}の人気ランキングと値下げ情報（{snap["date"]}）｜{config["site_name"]}',
            f'{name}ジャンルの人気ランキングTOP{len(rows)}と、値下げ・順位変動を毎日更新。',
            body, gid), encoding="utf-8")
        pages.append(fname)

    for code, h in history.items():
        fname = item_filename(code)
        short = h["info"]["name"][:40]
        prices = [o["price"] for o in h["obs"].values()]
        (SITE / fname).write_text(page(
            config, snap, fname,
            f'{short} の価格推移｜{config["site_name"]}',
            f'{short} の価格推移。観測{len(prices)}日間の最安は{yen(min(prices))}、最高は{yen(max(prices))}。',
            item_page_body(h, snap["date"], names), ""), encoding="utf-8")
        pages.append(fname)

    base = config["base_url"].rstrip("/")
    urls = "".join(f"<url><loc>{base}/{p}</loc><lastmod>{snap['date']}</lastmod></url>" for p in pages)
    (SITE / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
        encoding="utf-8")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")

    print(f"built {len(pages)} pages from {len(snaps)} snapshot(s): "
          f"{len(drops)} drops, {len(movers)} movers, {len(newcomers)} new")
    return 0


if __name__ == "__main__":
    sys.exit(main())
