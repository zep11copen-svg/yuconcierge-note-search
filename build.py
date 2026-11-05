#!/usr/bin/env python3
"""noteの全記事を取得し、検索ページ用のファイルを docs/ に作る。

  docs/note-index.json … 全記事データ(検索ページが読み込む)
  docs/widget.html     … ユーコンシェルジュに貼り付ける検索ページ(軽量版)
  docs/index.html      … 動作確認用の単体ページ(GitHub PagesのURLを開くと見られる)

使い方:  python3 build.py
設定は環境変数で変更可:  NOTE_USER(noteのID) / BODY_LEN(検索に使う本文の長さ)
GitHub Actions上では GITHUB_REPOSITORY から公開URLを自動で決める。"""
import html, json, os, re, sys, time, urllib.request

USER = os.environ.get("NOTE_USER", "kuwaman_88")
BODY_LEN = int(os.environ.get("BODY_LEN", "1500"))
UA = {"User-Agent": "Mozilla/5.0"}
ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")

def fetch(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)["data"]
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))

def plain(h):
    h = re.sub(r"<(br|/p|/h\d|/li)[^>]*>", " ", h)
    h = re.sub(r"<[^>]+>", "", h)
    return " ".join(html.unescape(h).split())

def small_image(u):
    return (re.sub(r"\?.*$", "", u) + "?width=320") if u else ""

# 前回のデータ(本文の再取得を減らす & 取得失敗時の保険)
old = {}
try:
    for it in json.load(open(os.path.join(DOCS, "note-index.json"), encoding="utf-8")):
        old[it["u"]] = it
except Exception:
    pass

# 1) 記事一覧(全ページ)
notes, page = [], 1
while True:
    d = fetch(f"https://note.com/api/v2/creators/{USER}/contents?kind=note&page={page}&per_page=50")
    notes += d["contents"]
    print(f"list page {page}: {len(notes)}/{d['totalCount']}", file=sys.stderr)
    if d["isLastPage"] or not d["contents"]:
        break
    page += 1
    time.sleep(0.3)
if not notes:
    sys.exit("記事を1件も取得できませんでした。既存データを守るため中止します。")

# 2) 各記事の本文・ハッシュタグ(すでに取得済みの記事は使い回す)
items, fresh = [], 0
for c in notes:
    url = c.get("noteUrl", "")
    if url in old and old[url].get("b"):
        prev = old[url]
        prev["t"] = c.get("name", prev["t"])       # タイトル修正は反映
        prev["i"] = small_image(c.get("eyecatch")) or prev["i"]
        items.append(prev)
        continue
    try:
        v = fetch(f"https://note.com/api/v3/notes/{c['key']}")
        body = plain(v.get("body") or "")
        tags = [h["hashtag"]["name"].lstrip("#") for h in (v.get("hashtag_notes") or []) if h.get("hashtag")]
    except Exception as e:
        print(f"  ! {c['key']} 本文取得失敗: {e}", file=sys.stderr)
        body, tags = " ".join((c.get("body") or "").split()), []
    items.append({"t": c.get("name", ""), "u": url, "d": (c.get("publishAt") or "")[:10],
                  "i": small_image(c.get("eyecatch")), "b": body[:BODY_LEN], "h": tags})
    fresh += 1
    time.sleep(0.25)

# 新しい順に並べておく
items.sort(key=lambda x: x["d"], reverse=True)
os.makedirs(DOCS, exist_ok=True)
data = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
open(os.path.join(DOCS, "note-index.json"), "w", encoding="utf-8").write(data)

# 3) 検索ページ
tpl = open(os.path.join(ROOT, "src", "widget.template.html"), encoding="utf-8").read()
repo = os.environ.get("GITHUB_REPOSITORY", "")
if "/" in repo:
    owner, name = repo.split("/", 1)
    abs_url = f"https://{owner}.github.io/{name}/note-index.json"
else:
    abs_url = "note-index.json"
widget = tpl.replace('/*__DATA_URL__*/""', json.dumps(abs_url))
open(os.path.join(DOCS, "widget.html"), "w", encoding="utf-8").write(widget)

page = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>ユーコンシェルジュ トピックス検索(動作確認用)</title></head><body style="margin:0">'
        + tpl.replace('/*__DATA_URL__*/""', '"note-index.json"') + "</body></html>")
open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(page)

print(f"done: {len(items)} articles ({fresh} new/refetched). data url: {abs_url}", file=sys.stderr)
