import json

def parse_sarif_file(sarif_path):
    with open(sarif_path, 'r') as f:
        data = json.load(f)
    queries = []
    runs = data.get('runs', [])
    for run in runs:
        rules = {rule['id']: rule for rule in run.get('tool', {}).get('driver', {}).get('rules', [])}
        for result in run.get('results', []):
            rule_id = result.get('ruleId', 'Unknown Rule')
            rule = rules.get(rule_id, {})
            query = {
                'name': rule.get('name', rule_id),
                'description': rule.get('fullDescription', {}).get('text', ''),
                'results': []
            }
            message = result.get('message', {}).get('text', '')
            locations = result.get('locations', [])
            for loc in locations:
                physical = loc.get('physicalLocation', {})
                artifact = physical.get('artifactLocation', {})
                region = physical.get('region', {})
                file_path = artifact.get('uri', '')
                start_line = region.get('startLine', '')
                query['results'].append(f"{file_path}:{start_line} - {message}")
            queries.append(query)
    return queries

def prettify_query_result(query):
    title = query.get('name', 'Unnamed Query')
    description = query.get('description', '')
    results = query.get('results', [])
    pretty = f"Query: {title}\nDescription: {description}\nResults:\n"
    for idx, result in enumerate(results, 1):
        pretty += f"  {idx}. {result}\n"
    return pretty

def make_pdf_report(sarif_path, output_pdf):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    queries = parse_sarif_file(sarif_path)
    for query in queries:
        pretty_query = prettify_query_result(query)
        pdf.multi_cell(0, 10, pretty_query)
        pdf.ln()

    pdf.output(output_pdf)
    print(f"PDF report generated: {output_pdf}")
    return output_pdf

