import re
import unicodedata


def slugify(text, max_len=50):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[a-z0-9]+", ascii_text.lower())
    slug = ""
    for word in words:
        candidate = f"{slug}-{word}" if slug else word
        if len(candidate) > max_len:
            break
        slug = candidate
    if not slug and words:
        slug = words[0][:max_len]
    return slug
