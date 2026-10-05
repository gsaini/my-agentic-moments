Write `parse_csv_line(line: str) -> list[str]` that splits one CSV line (RFC 4180 rules) into fields, without using
the `csv` module. Fields are separated by commas. A field may be wrapped in double quotes, in which case it can contain
commas, and a doubled quote (`""`) inside it stands for one quote character. Whitespace is part of the field. An empty
line is one empty field.
