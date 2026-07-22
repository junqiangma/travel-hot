# 旅行热点 · Travel Hot

每日旅行情报聚合网页，托管于 GitHub Pages。

## 页面

- `index.html` — 时间线视图（按日期分组，支持来源筛选 / 搜索 / 未读标记 / 深浅色）
- `board.html` — 经典看板视图（原始数据看板）
- `data.js` — 数据文件（`window.DASHBOARD_DATA`），每日由更新流程重新生成

## 数据来源

民航资源网（CARNOC）、LoyaltyLobby、招行/中信/交行信用卡公告、12306、CEIC 地震、驻泰使馆、小红书达人（酒旅情报局、葱头的旅游羊毛、老鸭唐纳德、一只酒店旅行兔、嬉游小助理）。

## 更新方式

本地运行旅游资讯看板更新流程（travel-news-dashboard skill），重新生成 `dashboard_seed.json` 后：

```bash
python - <<'EOF'
import json, datetime
data = json.load(open(r"D:\KIMI\项目\JUNQIANG's数据看板\dashboard_seed.json", encoding='utf-8'))
data.sort(key=lambda d: str(d.get('sortTime','')), reverse=True)
payload = {"updatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "count": len(data), "items": data}
with open('data.js', 'w', encoding='utf-8') as f:
    f.write('window.DASHBOARD_DATA = ')
    json.dump(payload, f, ensure_ascii=False)
    f.write(';\n')
EOF
git add data.js board.html && git commit -m "update data" && git push
```
