def parse_csv_line(line):
    fields, field, quoted = [], "", False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            fields.append(field.strip())
            field = ""
        else:
            field += ch
    if field:
        fields.append(field.strip())
    return fields
