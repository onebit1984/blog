import re

linkblock_re = r'(?s)<div class="pl">\n<code>((?:www|http).*?)</code>\n</div>'

def nicelink(url):
    if not url.startswith('http://'):
        url = 'http://' + url
    return '<tt><a href="{}">{}</a></tt>'.format(url, url)

def linkblock_fix(match):
    text = match.group(1).strip()
    links = text.split('<br />\n')
    return '<ul>{}</ul>'.format('<br>'.join(nicelink(link) for link in links))

codeblock_re = r'(?s)<div class="pl">\n<code>(.*?)</code>\n</div>'

def codeblock_fix(match):
    text = match.group(1).strip()
    text = text.replace('<br />', '')
    lang = ('html' if text.startswith(('<', '&lt;'))
            else 'bash' if text.startswith('$')
            else 'python')
    return '<pre>\n#!{}\n{}</pre>'.format(lang, text)

listing_re = (
    r'(?s)(<div id="list_[\d_]+" class="listing">\n'
    r'<p class="normal">.*?</p>\n)'
    r'(.*?)'
    r'</div>'
    )
listing_filename_re = r'Chapter (\d+) - (.*?)<br />'

def listing_fix(match):
    body = match.group(2)
    match2 = re.search(listing_filename_re, body)
    if match2:
        chapter = match2.group(1)
        filename = match2.group(2)
        path = '_listings_fopnp/python2/{}/{}'.format(chapter, filename)
        with open(path) as f:
            text = f.read()
        lang = 'python'
    else:
        text = body.replace('<code>', '').replace('</code>', '').replace(
            '<br />', '')
        lang = ('html' if text.startswith(('<', '&lt;'))
                else 'bash' if text.startswith('$')
                else 'python')
    return '{}</div><pre>\n#!{}\n{}</pre>'.format(match.group(1), lang, text)

def run(content):
    content = re.sub(r'<a id="page_\d+" />', '', content)
    content = re.sub(linkblock_re, linkblock_fix, content)
    content = re.sub(codeblock_re, codeblock_fix, content)
    content = re.sub(listing_re, listing_fix, content)
    return content
