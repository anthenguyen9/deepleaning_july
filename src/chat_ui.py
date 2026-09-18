"""Safe, minimal formatting for grounded assistant replies."""
import re
from urllib.parse import urlsplit

from markupsafe import Markup, escape


TOKEN = re.compile(r'\[R\d+\]|\*\*[^*\n]+\*\*')
NUMBERED_RESTAURANT = re.compile(r'(?<!\w)(\d{1,2})\.\s+(?=\*\*)')


def review_url(value):
    if not isinstance(value, str): return ''
    try: parsed = urlsplit(value)
    except ValueError: return ''
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        return ''
    return value


def assistant_reply(value, citations=()):
    """Link only cited source URLs; escape all model and review-supplied text."""
    content = NUMBERED_RESTAURANT.sub(r'\n\n\1. ', str(value or '')).strip()
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
            label = f'Đánh giá {token[2:-1]}'
            if url:
                parts.append(Markup('<a class="citation-link" href="{}" target="_blank" '
                                    'rel="noopener noreferrer" aria-label="Mở bình luận gốc cho {}">{}</a>').format(
                                    url, label, label))
            else:
                parts.append(Markup('<span class="citation-unavailable" '
                                    'title="Chưa có liên kết đến bình luận gốc">{}</span>').format(label))
        start = match.end()
    parts.append(escape(content[start:]))
    return Markup('').join(parts)
