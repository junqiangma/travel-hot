#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
旅行热点 · 云端兜底数据更新脚本（GitHub Actions 用，也可本地运行）

只抓取无需浏览器、可直连的数据源：
  - CARNOC 民航新闻（JSON API）
  - LoyaltyLobby（首页 HTML，标题保持英文，不打乱本地任务的翻译版）
  - USGS 地震（>= M5.0）
  - 12306 铁路动态（静态页，海外 runner 可能被拦，失败则保留旧数据）

合并策略：以仓库现有 data.js 为基础，按 id 去重（已有条目优先），
追加新条目后按 sortTime 倒序；对云端抓取的来源做条数上限与 21 天老化裁剪。
CMB / BOCOM / CITIC / 小红书 / 驻泰使馆 等缓存源原样保留，由本地定时任务刷新。
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_JS = ROOT / "data.js"
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST)
TODAY = NOW.strftime("%Y-%m-%d")
TODAY_ID = NOW.strftime("%Y%m%d")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
TIMEOUT = 25

CAPS = {"CARNOC": 40, "LOYALTYLOBBY": 40, "CEIC": 15, "12306": 20}
MAX_AGE_DAYS = 21

report = {"added": {}, "failed": []}


def log(tag, msg):
    print(f"[{NOW.strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)


# ---------------------------------------------------------------- CARNOC
def fetch_carnoc():
    url = "https://service.carnoc.com/api/web/index.php/carnoc/news/index-news-merge-v21"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    raw = r.json()
    items = (raw.get("list") or {}).get("grade1", {}).get("list") or []
    banned = ['会见', '局长', '副部长', '总经理', '座谈', '会谈', '致辞', '出席', '签署', '大使', '领导',
              '征集', '征文', '征集令', '有奖', '数字化', '智慧', '智能', '数字', '信息化', '大数据',
              '云计算', '人工智能', '5G', '6G', '区块链', '马拉松', '生产计划', '产量计划']
    out = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        drop = False
        for k in banned:
            if k in ("智能", "数字"):
                if k in title and "AIR" not in title.upper():
                    drop = True
                    break
            elif k in title:
                drop = True
                break
        if drop:
            continue
        out.append({
            "id": f"carnoc_{it.get('id')}",
            "title": title,
            "href": (it.get("news-url") or "").replace("https://", "http://", 1),
            "source": "CARNOC",
            "sourceLabel": "✈️ 民航资源网",
            "category": "民航新闻",
            "sortTime": TODAY,
            "author": "",
        })
    log("CARNOC", f"API 返回 {len(items)} 条，过滤后 {len(out)} 条")
    return out


# ---------------------------------------------------------------- LoyaltyLobby
BRAND_MAP = [
    ('IHG', 'IHG'), ('Hyatt', '凯悦'), ('Marriott', '万豪'), ('Hilton', '希尔顿'),
    ('American Airlines', '美航'), ('United Airlines', '美联航'), ('Delta Airlines', '达美'),
    ('Air France', '法航'), ('Lufthansa', '汉莎'), ('Emirates', '阿联酋航空'),
    ('Turkish Airlines', '土耳其航空'), ('Accor', '雅高'), ('Qatar', '卡塔尔'),
    ('Finnair', '芬航'), ('Iberia', '伊比利亚'), ('LATAM', 'LATAM'),
    ('Japan Airlines', '日航'), ('Wyndham', '温德姆'), ('Chase', 'Chase'),
    ('Flying Blue', '法航-荷航'), ('KLM', '荷航'), ('SAS', '北欧航空'), ('Cathay', '国泰'),
    ('Singapore Airlines', '新加坡航空'), ('Star Alliance', '星空联盟'),
    ('Asiana', '韩亚航空'), ('AAdvantage', '美航'), ('Miles&Smiles', '土耳其航空'),
    ('Skywards', '阿联酋航空'), ('One Rewards', 'IHG'), ('EuroBonus', '北欧航空'),
    ('Amex', '美国运通'), ('American Express', '美国运通'), ('Platinum', '美国运通白金'),
    ('Reader Question', '读者提问'), ('Award', '里程票'), ('Compensation', '赔偿'),
    ('Fabulous Fridays', '周五精选'), ('Fairmont', '费尔蒙'),
]


def detect_brand(title):
    t = title.lower()
    for en, cn in BRAND_MAP:
        if en.lower() in t:
            return cn
    return "海外航旅资讯"


def fetch_loyaltylobby():
    # 首页被 Cloudflare 拦截（403），改用 RSS：含真实文章链接与发布时间
    import xml.etree.ElementTree as ET
    r = requests.get("https://loyaltylobby.com/feed/", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    root_el = ET.fromstring(r.content)
    items = root_el.findall(".//channel/item")[:30]
    out, day_counters = [], {}
    for it in items:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "https://loyaltylobby.com/").strip()
        pub = (it.findtext("pubDate") or "").strip()
        if not title:
            continue
        sort_date = TODAY
        try:
            from email.utils import parsedate_to_datetime
            sort_date = parsedate_to_datetime(pub).astimezone(CST).strftime("%Y-%m-%d")
        except Exception:
            pass
        dk = sort_date.replace("-", "")
        day_counters[dk] = day_counters.get(dk, 0) + 1
        brand = detect_brand(title)
        out.append({
            "id": f"ll_{dk}_{day_counters[dk]:02d}",
            "title": title,  # 云端版保持英文；本地任务运行后会整体替换为中文翻译版
            "originalTitle": title,
            "href": link,
            "source": "LOYALTYLOBBY",
            "sourceLabel": "🌐 LoyaltyLobby",
            "category": brand,
            "brandTag": brand,
            "sortTime": sort_date,
            "author": "John Ollila",
        })
    log("LL", f"RSS 提取 {len(out)} 篇（英文原标题）")
    return out


# ---------------------------------------------------------------- USGS 地震
def fetch_quakes():
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    feats = r.json().get("features", [])
    out = []
    i = 0
    for f in feats:
        p = f.get("properties") or {}
        if (p.get("mag") or 0) < 5.0:
            continue
        ts = datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        lon, lat = (f.get("geometry") or {}).get("coordinates", [0, 0])[:2]
        out.append({
            "id": f"eq_{re.sub(r'[-: ]', '', ts)}_{i}",
            "title": f"{ts} {p.get('place','')} M{p['mag']}",
            "href": f"https://earthquake.usgs.gov/earthquakes/map/?latitude={lat}&longitude={lon}&zoom=8",
            "source": "CEIC",
            "sourceLabel": "🌏 CEIC地震",
            "category": "地震快讯",
            "sortTime": TODAY,
            "author": "",
        })
        i += 1
        if i >= 8:
            break
    log("CEIC", f"M5.0+ 地震 {len(out)} 条")
    return out


# ---------------------------------------------------------------- 12306
def fetch_rail():
    from bs4 import BeautifulSoup
    url = "https://www.12306.cn/mormhweb/zxdt/index_zxdt.html"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    keywords = ['加开', '增开', '调整', '恢复', '停运', '公告', '通知', '铁路', '改签', '发票', '列车']
    out, seen = [], set()
    for a in soup.find_all("a"):
        t = a.get_text(strip=True)
        if t and 10 < len(t) < 80 and any(k in t for k in keywords) and t not in seen:
            seen.add(t)
            out.append({
                "id": f"rail_{TODAY_ID}_{len(out)+1:02d}",
                "title": t,
                "href": "https://www.12306.cn/",
                "source": "12306",
                "sourceLabel": "🚄 12306",
                "category": "铁路动态",
                "sortTime": TODAY,
                "author": "",
            })
        if len(out) >= 20:
            break
    log("RAIL", f"提取 {len(out)} 条")
    return out


FETCHERS = [
    ("CARNOC", fetch_carnoc),
    ("LOYALTYLOBBY", fetch_loyaltylobby),
    ("CEIC", fetch_quakes),
    ("12306", fetch_rail),
]


def load_existing():
    if not DATA_JS.exists():
        return []
    text = DATA_JS.read_text(encoding="utf-8")
    m = re.search(r"window\.DASHBOARD_DATA\s*=\s*(\{.*\})\s*;?\s*$", text, re.S)
    if not m:
        return []
    return (json.loads(m.group(1))).get("items", [])


def main():
    existing = load_existing()
    log("MAIN", f"现有条目 {len(existing)} 条（今日: {TODAY} CST）")

    by_id = {d.get("id"): d for d in existing if d.get("id")}

    for name, fn in FETCHERS:
        try:
            items = fn()
        except Exception as e:
            log(name, f"抓取失败: {e}")
            report["failed"].append(name)
            continue
        added = 0
        for it in items:
            if it["id"] not in by_id:  # 已有条目优先（保留本地任务的真实日期/中文翻译）
                by_id[it["id"]] = it
                added += 1
        report["added"][name] = added
        log(name, f"新增 {added} 条（重复 {len(items)-added} 条已跳过）")

    merged = list(by_id.values())

    # 老化裁剪：云端抓取来源仅保留近 21 天 + 条数上限
    cutoff = (NOW - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    final, counters = [], {}
    for d in sorted(merged, key=lambda x: str(x.get("sortTime", "")), reverse=True):
        src = d.get("source", "")
        st = str(d.get("sortTime", ""))[:10]
        if src in CAPS:
            if st < cutoff:
                continue
            counters[src] = counters.get(src, 0) + 1
            if counters[src] > CAPS[src]:
                continue
        final.append(d)

    payload = {
        "updatedAt": NOW.strftime("%Y-%m-%d %H:%M"),
        "count": len(final),
        "items": final,
    }
    DATA_JS.write_text(
        "window.DASHBOARD_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    log("MAIN", f"写入 data.js，共 {len(final)} 条；新增: {report['added']}；失败源: {report['failed'] or '无'}")


if __name__ == "__main__":
    sys.exit(main())
