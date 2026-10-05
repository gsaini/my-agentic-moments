Write `slugify(text: str, max_len: int = 50) -> str`. Lower-case the text, remove accents (`é` → `e`), and join the
runs of ASCII letters and digits with single hyphens — every other character separates words and never appears in the
result. If the result is longer than `max_len`, cut it at a hyphen so that it is at most `max_len` characters and no
word is cut; if even the first word is too long, cut that word at `max_len`. No leading or trailing hyphens.
