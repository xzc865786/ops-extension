"""Build both homepage outputs from shared source, using Python's standard library."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def logo(name: str, instance: str, css_class: str) -> str:
    svg = (ROOT / 'assets' / name).read_text(encoding='utf-8')
    ids = re.findall(r'\bid="([^"]+)"', svg)
    for identifier in ids:
        svg = svg.replace(f'id="{identifier}"', f'id="{instance}-{identifier}"')
    svg = svg.replace('aria-labelledby="title desc"', f'aria-labelledby="{instance}-title {instance}-desc"')
    return svg.replace('<svg ', f'<svg class="{css_class}" ', 1).strip()


def build() -> None:
    content = (ROOT / 'home.template.html').read_text(encoding='utf-8')
    for token, filename, instance, css_class in (
        ('{{HEADER_LOGO}}', 'huima_horizontal_light.svg', 'hm-header', 'hm-logo'),
        ('{{CENTER_LOGO}}', 'huima_symbol_color.svg', 'hm-center', 'hm-symbol'),
        ('{{FOOTER_LOGO}}', 'huima_horizontal_light.svg', 'hm-footer', 'hm-logo'),
    ):
        content = content.replace(token, logo(filename, instance, css_class))
    css = (ROOT / 'home.css').read_text(encoding='utf-8')
    fragment = content.strip() + '\n\n<style>\n' + css.strip() + '\n</style>\n'
    (ROOT / 'sub2api-home.html').write_text(fragment, encoding='utf-8')
    # Preview uses real destinations; the fragment keeps same-origin relative links.
    preview = fragment.replace('href="/login"', 'href="https://api.tysy.top/login"')
    preview = preview.replace('href="/docs/"', 'href="https://api.tysy.top/docs/"')
    document = '''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="汇码智能，为个人开发者与小团队提供 AI API 接入服务。减少接入负担，专注创造。">
  <title>汇码智能 · 让智能，接入你的创造</title>
  <style>html,body{margin:0;padding:0}body{background:#fff}</style>
</head>
<body>
''' + preview + '</body>\n</html>\n'
    (ROOT / 'preview.html').write_text(document, encoding='utf-8')
    print('Generated preview.html and sub2api-home.html')


if __name__ == '__main__':
    build()
