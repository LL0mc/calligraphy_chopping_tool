with open('D:/notebooks/handwriting/annotate_flask.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    '{{page}}': '{PAGE}',
    '{{img_b64}}': '{IMG_B64}',
    '{{boxes_json}}': '{BOXES_JSON}',
    '{{selected}}': '{SELECTED}',
    '{{total}}': '{TOTAL}',
}

start = content.find('HTML_TPL = """')
assert start >= 0, f'Not found at {start}'
start_content = start + len('HTML_TPL = """')
end = content.find('"""', start_content)
assert end >= 0, 'End not found'
tpl = content[start_content:end]
for old, new in replacements.items():
    tpl = tpl.replace(old, new)
content = content[:start_content] + tpl + content[end:]

with open('D:/notebooks/handwriting/annotate_flask.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
