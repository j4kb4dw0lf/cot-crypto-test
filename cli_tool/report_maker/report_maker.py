import json
import os
import subprocess
from fpdf import FPDF

def parse_sarif_file(sarif_path):
    try:
        with open(sarif_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: SARIF file not found at {sarif_path}")
        return []
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from SARIF file at {sarif_path}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while reading SARIF file: {e}")
        return []

    queries = []
    runs = data.get('runs', [])
    for run in runs:
        rules = {rule['id']: rule for rule in run.get('tool', {}).get('driver', {}).get('rules', [])}
        for result in run.get('results', []):
            rule_id = result.get('ruleId', 'Unknown Rule')
            rule = rules.get(rule_id, {})
            query = {
                'name': rule.get('name', rule_id),
                'description': rule.get('fullDescription', {}).get('text', 'No description available.'),
                'results': []
            }
            message = result.get('message', {}).get('text', 'No message provided.')
            locations = result.get('locations', [])
            for loc in locations:
                physical = loc.get('physicalLocation', {})
                artifact = physical.get('artifactLocation', {})
                region = physical.get('region', {})
                file_path = artifact.get('uri', 'Unknown File')
                if file_path.startswith('file://'):
                    file_path = file_path[len('file://'):]
                start_line = region.get('startLine', 'Unknown Line')
                query['results'].append(f"{file_path}:{start_line} - {message}")
            if query['results'] or query['name'] != rule_id or query['description'] != 'No description available.':
                queries.append(query)
    return queries

def prettify_query_result(query):
    title = query.get('name', 'Unnamed Query')
    description = query.get('description', 'No description.')
    results = query.get('results', [])
    pretty = f"Query: {title}\n"
    if description:
        pretty += f"Description: {description}\n"
    pretty += "Results:\n"
    if not results:
        pretty += "  No results found for this query.\n"
    else:
        for idx, result in enumerate(results, 1):
            pretty += f"  {idx}. {result}\n"
    return pretty

def bqrs_to_sarif(bqrs_path, sarif_output_path):
    print(f"Attempting to convert BQRS '{bqrs_path}' to SARIF '{sarif_output_path}' using CodeQL CLI...")
    command = [
        "codeql", "bqrs", "interpret",
        "--format=sarif-latest",
        f"-t=<{(os.path.basename(bqrs_path)).split('_')[0]}={(os.path.basename(bqrs_path)).split('_')[0]}>",
        f"-t=<cpp/{(os.path.basename(bqrs_path)).split('_')[1]}=cpp/{(os.path.basename(bqrs_path)).split('_')[1]}>",
        f"--output={sarif_output_path}",
        bqrs_path
    ]
    try:
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        print("CodeQL CLI output (stdout):\n", process.stdout)
        if process.stderr:
            print("CodeQL CLI output (stderr):\n", process.stderr)
        print(f"Successfully converted BQRS to SARIF: {sarif_output_path}")
        return sarif_output_path
    except FileNotFoundError:
        print(f"Error: CodeQL CLI not found. Please ensure 'codeql' is in your system's PATH.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error during CodeQL BQRS interpretation:")
        print(f"Command: {' '.join(e.cmd)}")
        print(f"Return Code: {e.returncode}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during BQRS to SARIF conversion: {e}")
        return None

def make_pdf_report(bqrs_path, output_pdf):
    sarif_path = os.path.splitext(bqrs_path)[0] + ".sarif"
    converted_sarif_path = bqrs_to_sarif(bqrs_path, sarif_path)
    if not converted_sarif_path:
        print("BQRS to SARIF conversion failed. Cannot proceed with PDF generation.")
        return None
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    queries = parse_sarif_file(converted_sarif_path)
    if not queries:
        pdf.multi_cell(0, 10, "No query results found or SARIF file was empty/invalid.")
        print("No query results found to generate PDF.")
    else:
        for query in queries:
            pretty_query = prettify_query_result(query)
            pdf.multi_cell(0, 7, pretty_query)
            pdf.ln(5)
    try:
        pdf.output(output_pdf)
        print(f"PDF report generated: {output_pdf}")
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return None
    return output_pdf
