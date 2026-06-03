from html import escape


def to_title_case(s):
    if not isinstance(s, str):
        return s
    parts = s.split("_")
    return " ".join(x.capitalize() for x in parts)


def prettify_html(entry):
    if "Category" in entry.columns:
        entry["Category"] = entry["Category"].apply(to_title_case)
    df = entry.map(
        lambda x: (
            escape(x).replace("\r", "").replace("\n", "<br>")
            if isinstance(x, str)
            else x
        )
    )
    df_html = df.to_html(index=False, escape=False)
    return df_html


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
