import re

with open(r'C:\Users\yanzichen\Documents\ad_mp_top - 副本.drawio', 'r', encoding='utf-8') as f:
    content = f.read()

names = re.findall(r'<diagram[^>]*name="([^"]*)"', content)
print('页面数量:', len(names))
for i, name in enumerate(names, 1):
    print(f'第 {i} 页: {name}')
