def slugify(text, max_len=50):
    return "-".join(text.lower().split())[:max_len]
