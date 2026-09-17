"""Safe, minimal formatting for grounded assistant replies."""
import re
from urllib.parse import urlsplit

from markupsafe import Markup, escape


TOKEN = re.compile(r'\[R\d+\]|\*\*[^*\n]+\*\*')


def review_url(value):
    if not isinstance(value, str): return ''
    try: parsed = urlsplit(value)
    except ValueError: return ''
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        return ''
    return value


def assistant_reply(value, citations=()):
    """Link only cited source URLs; escape all model and review-supplied text."""
    content = str(value or '')
    sources = {c.get('citation_id'): c for c in citations if isinstance(c, dict)}
    parts = []
    start = 0
    for match in TOKEN.finditer(content):
        parts.append(escape(content[start:match.start()]))
        token = match.group()
        if token.startswith('**'):
            parts.append(Markup('<strong>{}</strong>').format(token[2:-2]))
        else:
            source = sources.get(token[1:-1], {})
            url = review_url(source.get('source_url'))
            if url:
                parts.append(Markup('<a class="citation-link" href="{}" target="_blank" '
                                    'rel="noopener noreferrer" aria-label="Mở review gốc {}">{}</a>').format(
                                    url, token, token))
            else:
                parts.append(escape(token))
        start = match.end()
    parts.append(escape(content[start:]))
    return Markup('').join(parts)
