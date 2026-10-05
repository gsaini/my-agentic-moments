def parse_csv_line(line):
    fields, field, i, quoted = [], [], 0, False
    while i < len(line):
        ch = line[i]
        if quoted:
            if ch == '"' and i + 1 < len(line) and line[i + 1] == '"':
                field.append('"')
                i += 1
            elif ch == '"':
                quoted = False
            else:
                field.append(ch)
        elif ch == '"':
            quoted = True
        elif ch == ",":
            fields.append("".join(field))
            field = []
        else:
            field.append(ch)
        i += 1
    fields.append("".join(field))
    return fields
