from html import escape


def to_title_case(s):
    if not isinstance(s, str):
        return s
    parts = s.split("_")
    return " ".join(x.capitalize() for x in parts)


def ordered_rows(result, order):
    return [{"Category": key, "Details": result.get(key, "")} for key in order]


def details_by_category(rows):
    return {row["Category"]: row["Details"] for row in rows}


def _html_cell(value):
    return escape(str(value)).replace("\r", "").replace("\n", "<br>")


def prettify_html(rows):
    table_body = "\n".join(
        "<tr>"
        f"<td>{_html_cell(to_title_case(row['Category']))}</td>"
        f"<td>{_html_cell(row['Details'])}</td>"
        "</tr>"
        for row in rows
    )
    return (
        '<table class="analysis-result-table">\n'
        "<thead><tr><th>Category</th><th>Details</th></tr></thead>\n"
        f"<tbody>\n{table_body}\n</tbody>\n"
        "</table>"
    )


def simplify_description(schema):
    schema_description = {
        "tables": {
            table["originalName"]: {
                "description": table["description"],
                "columns": {
                    column["originalName"]: {
                        "description": column["description"],
                        "type": column["type"],
                    }
                    for column in table["columns"]
                },
                "foreign_keys": [
                    rel for (k, v) in table["relations"].items() for rel in v
                ],
            }
            for table in schema["tables"]
        },
        "application_description": schema["description"],
    }

    return schema_description
