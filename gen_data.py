import json, shutil, datetime

src = r"D:\KIMI\项目\JUNQIANG's数据看板\dashboard_seed.json"
data = json.load(open(src, encoding='utf-8'))
data.sort(key=lambda d: str(d.get('sortTime','')), reverse=True)
payload = {
    "updatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    "count": len(data),
    "items": data
}
with open('data.js', 'w', encoding='utf-8') as f:
    f.write('window.DASHBOARD_DATA = ')
    json.dump(payload, f, ensure_ascii=False)
    f.write(';\n')
shutil.copy(r"D:\KIMI\项目\JUNQIANG's数据看板\carnoc_news_dashboard.html", 'board.html')
print('ok, items:', len(data))
