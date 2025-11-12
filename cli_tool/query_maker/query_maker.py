import sqlite3
import os
import sys
import json
import io
import re
import textwrap
from collections import defaultdict


# --- Configuration and Data Structures ---

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'DB', 'crypto_primitives.db')
OUTPUT_DIR = 'generated_ql_queries'
os.makedirs(OUTPUT_DIR, exist_ok=True)

json_path = os.path.join(os.path.dirname(__file__),"..", "utils", "cats_alts.json")
with open(json_path, "r", encoding="utf-8") as f:
    cts_data = json.load(f)

ALGOS = cts_data.get("ALGOS", {})
OPS =  cts_data.get("OPS", {})
ALTS = cts_data.get("ALTS", {})
ALTS_CATS = cts_data.get("ALTS_CATS", {})


# --- Utility Functions ---

def flatten_categorized_data(categorized_dict):
    flat_set = set()
    for _, sub_dict_or_list in categorized_dict.items():
        if isinstance(sub_dict_or_list, dict):
            flat_set.update(flatten_categorized_data(sub_dict_or_list))
        elif isinstance(sub_dict_or_list, list):
            for item in sub_dict_or_list:
                flat_set.add(item)
    return flat_set

ALL_ALGOS_FLAT = flatten_categorized_data(ALGOS)
ALL_OPS_FLAT = flatten_categorized_data(OPS)


ALL_ALGORITHMS = flatten_categorized_data(ALGOS)
ALGO_TOKEN_TO_INFO = {}

def build_algo_token_info_map(data, path, info_map):
    if isinstance(data, dict):
        for key, value in data.items():
            build_algo_token_info_map(value, path + [key], info_map)
    elif isinstance(data, list):
        for token in data:
            info_map.setdefault(token, set()).add(tuple(path))

build_algo_token_info_map(ALGOS, [], ALGO_TOKEN_TO_INFO)

def get_alternative(path, alts_dict, alts_cats_dict):
    """Gets the best alternative based on a specific path."""
    current_level = alts_dict
    for key in path:
        if key in current_level:
            current_level = current_level[key]
        else:
            # If path not in specific alts, fallback to category alt
            return alts_cats_dict.get(path[0], "No specific alternative found.")
    return current_level if isinstance(current_level, str) else alts_cats_dict.get(path[0], "No specific alternative found.")


# Return CodeQl query to detect primitives that don't require further analysis on arguments.
# If necessary specify a list of primitive ids or categories ids to exclude from the query
def generate_query_no_args(conn, library_ids, excl_categories=None, excl_primitives=None):

    cursor = conn.cursor()

    # SQL query
    placeholders_libraries = ','.join('?' * len(library_ids))
    placeholders_excl_categories = ','.join('?' * (len(excl_categories) if excl_categories is not None else 0))
    placeholders_excl_primitives = ','.join('?' * (len(excl_primitives) if excl_primitives is not None else 0))
    query = f"""
    SELECT
        p.name as PrimitiveName,
        c.name as CategoryName,
        COALESCE(p.comment_alternative, c.comment_alternative_general) AS Alternative
    FROM Primitives p
    JOIN Primitive_categories pc ON p.primitive_id = pc.primitive_id
    JOIN Categories c ON pc.category_id = c.category_id
    WHERE p.library_id IN ({placeholders_libraries}) AND p.need_arg IS NULL AND
    p.primitive_id NOT IN ({placeholders_excl_primitives}) AND c.category_id NOT IN ({placeholders_excl_categories});
    """

    cursor.execute(query,library_ids)

    # Fetch all results
    rows = cursor.fetchall()

    # Start building the CodeQL content

    codeql_lines = [
        "/**",
        "* @id cpp/primitives-noargs-analysis",
        "* @kind problem",
        "* @problem.severity warning",
        "* @name Crypto primitive",
        "* @description Find cryptographic primitives",
        "*",
        "*/",
        "\nimport cpp\n",
        "predicate getCategory(string name, string category, string alternative) {"
    ]

    # Generate the OR-ed predicate clauses
    # Group primitives by name, collecting all their categories and alternatives

    primitive_groups = defaultdict(list)
    for primitive, category, alternative in rows:
        primitive_groups[primitive].append((category, alternative))

    for i, (primitive, cat_alt_list) in enumerate(primitive_groups.items()):
        alt_to_cats = defaultdict(list)
        for cat, alt in cat_alt_list:
            alt_to_cats[alt].append(cat)
        for j, (alt, cats) in enumerate(alt_to_cats.items()):
            cats_str = ", ".join(cats)
            line = f'(name = "{primitive}" and category = "{cats_str}" and alternative = "{alt}")'
            # Add "or" if not the last clause
            if not (i == len(primitive_groups) - 1 and j == len(alt_to_cats) - 1):
                line += " or"
            codeql_lines.append("  " + line)
    codeql_lines.append("}\n")


    # Add the main query block
    codeql_lines.extend([
        "from Function f, string name, string category, string alternative",
        'where name = f.getName() and getCategory(name, category, alternative) and not f.getLocation().getFile().getAbsolutePath().matches("%include%")',
        'select f,  "\\nFunction name: "+ name + "\\n" + "Category: " +  category + "\\n" + "Alternative: " + alternative'
    ])

    codeql_query = "\n".join(codeql_lines)

    cursor.close()
    conn.close()

    return codeql_query

# Return string for isKnownAlgorithm query
def returnQueryisKnownAlgorithm():
    query_builder = io.StringIO()

    query_builder.write('predicate isKnownAlgorithm(string category, string subCategory, string token, string alternative) {\n')

    category_clauses = []

    # Itera su ogni categoria in ALGOS
    for category, subcategories in ALGOS.items():

        subcategory_clauses = []
        # Itera su ogni sottocategoria
        for subcategory, tokens in subcategories.items():
            # 1. Determina l'alternativa corretta
            # Prova a ottenere l'alternativa specifica per la sottocategoria
            specific_alt = ALTS.get(category, {}).get(subcategory)

            # Se l'alternativa specifica non esiste o è "...", usa quella generale
            if not specific_alt or specific_alt == "...":
                alternative = ALTS_CATS.get(category, "...")
            else:
                alternative = specific_alt

            # 2. Costruisce la condizione per i token
            if len(tokens) == 1:
                token_condition = f'token = "{tokens[0]}"'
            else:
                token_parts = [f'token = "{t}"' for t in tokens]
                token_condition = f'({" or ".join(token_parts)})'

            # 3. Costruisce la clausola completa per la sottocategoria
            subcategory_clause = f'(subCategory = "{subcategory}" and {token_condition} and alternative = "{alternative}")'
            subcategory_clauses.append(subcategory_clause)

        # 4. Unisce le clausole delle sottocategorie con "or"
        full_subcategory_block = " or ".join(subcategory_clauses)

        # 5. Costruisce il blocco completo per la categoria
        category_clause = f'    (category = "{category}" and\n        ( {full_subcategory_block}\n        )\n    )'
        category_clauses.append(category_clause)

    # 6. Unisce i blocchi delle categorie con "or"
    query_builder.write(" or ".join(category_clauses))
    query_builder.write("\n}\n")
    res = query_builder.getvalue()
    query_builder.close()
    return res

def generate_query_macros():
    predicate = returnQueryisKnownAlgorithm()

    codeql_lines = [
        "/**",
        " * @id cpp/primitives-macro-analysis",
        " * @kind problem",
        " * @problem.severity warning",
        " * @name Insecure cryptographic algorithm specified by macro",
        " * @description Finds an insecure cryptographic algorithm specified as a macro. This query prioritizes the longest matching token to provide the most specific result.",
        " * @tags security",
        " * cryptography",
        " */",
        "\nimport cpp\n",
        "",
    ]
    codeql_lines.append(predicate)


    # Replace the old longestMatchAlgo + query builder with this:
    codeql_lines.append("""
    /** Does the macro name contain a known token (from any category)? */
    predicate containsKnownToken(MacroInvocation mi, string token) {
      exists(string c, string s, string alt |
        isKnownAlgorithm(c, s, token, alt) and
        mi.getMacro().getName().toLowerCase().matches("%" + token + "%")
      )
    }

    /** The globally-longest token from the macro name */
    predicate longestTokenInMacro(MacroInvocation mi, string token) {
      containsKnownToken(mi, token) and
      not exists(string t2 |
        containsKnownToken(mi, t2) and t2.length() > token.length()
      )
    }

    """)

    codeql_lines.extend([
      "from MacroInvocation mi, string token, string category, string subCategory, string alternative",
      "where",
      "  longestTokenInMacro(mi, token) and",
      "  isKnownAlgorithm(category, subCategory, token, alternative)",
      "select mi,",
      "  \"\\n Macro '\" + mi.getMacro().getName() + \"' used for an insecure algorithm.\" +",
      "  \"\\n Category: \" + category +",
      "  \"\\n Subcategory: \" + subCategory +",
      "  \"\\n Recommended alternative: \" + alternative + \".\""
    ])


    return "\n".join(codeql_lines)




def generate_query_with_args(conn, library_ids):
    cursor = conn.cursor()
    placeholders_libraries = ','.join('?' * len(library_ids))
    query = f"""
    SELECT
        p.name as FunctionName,
        p.need_arg as ArgumentIndex
    FROM Primitives p
    WHERE p.library_id IN ({placeholders_libraries}) AND p.need_arg IS NOT NULL
    """
    cursor.execute(query, library_ids)
    functions_with_args = cursor.fetchall()

    if not functions_with_args:
        return "" # Return empty if no functions need arg analysis


    predicate = returnQueryisKnownAlgorithm()

    codeql_lines = [
        "/**",
        " * @id cpp/primitives-withargs-analysis",
        " * @kind problem",
        " * @problem.severity warning",
        " * @name Insecure cryptographic algorithm specified by argument",
        " * @description Finds function calls that use an insecure cryptographic algorithm specified as an argument. This can be a string, a macro, or a call to a function whose name indicates the algorithm (e.g., OpenSSL's EVP_aes_256_cbc()). This query prioritizes the longest matching token to provide the most specific result.",
        " * @tags security",
        " * cryptography",
        " */",
        "\nimport cpp\n",
        "",
    ]
    codeql_lines.append(predicate)

    codeql_lines.append("""
    predicate containsKnownToken(Expr argValue, string token) {
      exists(string c, string s, string alt |
        isKnownAlgorithm(c, s, token, alt) and
        (
          (argValue instanceof StringLiteral and argValue.(StringLiteral).getValue().toLowerCase().matches("%" + token + "%")) or
          (argValue instanceof FunctionCall and argValue.(FunctionCall).getTarget().getName().toLowerCase().matches("%" + token + "%")) or
          (argValue instanceof VariableAccess and argValue.(VariableAccess).getTarget().getName().toLowerCase().matches("%" + token + "%"))
        )
      )
    }

    /** The globally-longest token from the macro name */
    predicate longestTokenInArg(Expr argValue, string token) {
      containsKnownToken(argValue, token) and
      not exists(string t2 |
        containsKnownToken(argValue, t2) and t2.length() > token.length()
      )
    }
    boolean isKnownFunction(string functionName) {"""
    )


    for primitive, index in functions_with_args:
        line = f'(functionName = "{primitive}" and result = true)'
        line += " or"
        codeql_lines.append("  " + line)
    # Remove the last "or" and close the predicate
    if codeql_lines[-1].endswith(" or"):
        codeql_lines[-1] = codeql_lines[-1][:-3]
    codeql_lines.append("}\n")


    codeql_lines.extend([
        "from FunctionCall call, Expr argValue, string functionName, string token, string category, string subCategory, string alternative, int n",
        "where",
        "  functionName = call.getTarget().getName() and",
        "  isKnownFunction(functionName) = true and",
        "  argValue = call.getArgument(n) and",
        "  longestTokenInArg(argValue, token) and",
        "  isKnownAlgorithm(category, subCategory, token, alternative)",
        "select call,",
        "  \"Call to '\" + functionName + \"' uses an insecure algorithm via argument '\" + argValue.toString() + \"'.  at postion \" + n.toString() + \". Detected token: '\" + token + \"'. \" +",
        "  \"Category: \" + category + \". Subcategory: \" + subCategory + \". Recommended alternative: \" + alternative + \".\""
    ])


    return "\n".join(codeql_lines)

# ======== Added features (family-grouped + sha[-_]?N + digit-relaxed where needed) ========

# Capitalizes only the first character of a string while keeping the rest unchanged.
def cap_form(t: str) -> str:
    return t[:1].upper() + t[1:] if t else t

def with_sep_variants(tokens):
    """
    For tokens that end with digits (e.g. sha1, sha256, ed25519) also produces 'base[-_]?digits'.
    Also adds 'base[-_]?[0-9]+' if there are numeric variants for that base.
    """
    out = []
    bases_with_digits = {}
    for t in tokens:
        # Detect if the token ends with a digit
        # ([a-z]+) First capture group: one or more lowercase letters (the "base")
        # (\d+)  Second capture group: one or more digits (the "digits")
        t = t.lower()
        m = re.fullmatch(r'([a-z]+)(\d+)', t)

        # If the match succeeds, the token ends with digits
        if m:
            base, digits = m.group(1), m.group(2)
            bases_with_digits.setdefault(base, set()).add(digits)
            out.append(t)
            out.append(f"{base}[-_]?{digits}")
        else:
            out.append(t)
    for base in bases_with_digits.keys():
        out.append(f"{base}[-_]?[0-9]+")
    # dedup
    seen, dedup = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            dedup.append(v)
    return dedup


def flatten_algos_families():
    """
    Returns tuples with this pattern: (cat, sub, tokens, alt)
    Where
        cat: category name
        sub: subcategory name
        tokens: list of token strings for this algorithm
        alt: the alternative classification
    Example:
    From the JSON categorization we can have a structure like
    ALGOS["BlockCiphers"]["DES"] = ["des", "3des", "tdes", "des-x", "des3", "desx"]
    ALTS["BlockCiphers"]["DES"] = "AES-256"
    BlockCiphers is the categorizaton
    DES is the subcategorization
    des, 3des, tdes, des-x, des3, desx are the tokens
    AES-256 is the alternative
    """
    for cat, subs in ALGOS.items():
        for sub, tokens in subs.items():
            specific = ALTS.get(cat, {}).get(sub)
            alt = specific if specific and specific != "..." else ALTS_CATS.get(cat, "...")
            yield (cat, sub, tokens, alt or "...")

def collect_mode_tokens():
    """
    Extracts all operation modes from the JSON data.
    Example return value ['ecb', 'ctr', 'cbc', 'cfb', 'ofb', 'xts']
    """
    modes = OPS.get("ModesofOperation", {})
    return sorted({tok.lower() for toks in modes.values() for tok in toks}, key=lambda s: (-len(s), s))

# Creates a regex group containing all algorithm tokens and modes, separated by |.
def conact_group():
    toks = sorted({t.lower() for _c,_s,toks,_a in flatten_algos_families() for t in toks}, key=lambda s: (-len(s), s))
    modes = collect_mode_tokens()
    groups = ["|".join(toks)]
    if modes:
        groups.append("|".join(modes))
    return "|".join([g for g in groups if g])

def family_clause_function_name(subcategory: str, tokens, alt: str):
    toks_lower = [t.lower() for t in tokens] # Convert all tokens to lowercase
    expanded = with_sep_variants(toks_lower)  # include sha[-_]?N e sha[-_]?[0-9]+
    lower_group = "|".join(expanded) # group with all lowercase variants
    uppers = "|".join((t.upper()) for t in toks_lower) # upper case variants
    caps   = "|".join((cap_form(t)) for t in toks_lower) # first letter capitalized

    # before the token/algorithm the following are acceptable for detection:
    #   No char i.e beginning of the string
    #   No letter or digits
    #   Digit followed by dash or underscore
    left_boundary = '(^|[^a-zA-Z0-9]|[0-9][-_])'

    # after the token/algorithm the following are acceptable for detection:
    #   No char i.e ending of the string
    #   No letters
    right_boundary = '([^a-zA-Z]|$)'

    # Patterns
    p1 = f'.*{left_boundary}({lower_group}){right_boundary}.*'
    p2 = f'.*{left_boundary}({lower_group})(?=[A-Z]).*'
    p3 = f'.*{left_boundary}({uppers})(?=[a-z]).*'
    p4 = f'.*{left_boundary}({caps})(?=[A-Z]).*'
    p5 = f'.*(?<=[a-z])({uppers}).*'
    p6 = f'.*(?<=[A-Z])({lower_group}).*'
    p7 = f'.*(?<=[a-z])({caps})(?=[A-Z]|[0-9]|[^a-zA-Z]|$).*'

    return (
        f'(not matchesConcatenated(funcName) and ('
        f' funcName.regexpMatch("{p1}")'
        f' or originalFuncName.regexpMatch("{p2}")'
        f' or originalFuncName.regexpMatch("{p3}")'
        f' or originalFuncName.regexpMatch("{p4}")'
        f' or originalFuncName.regexpMatch("{p5}")'
        f' or originalFuncName.regexpMatch("{p6}")'
        f' or originalFuncName.regexpMatch("{p7}")'
        f') and algorithm = "{subcategory}" and alternative = "{alt}" and source = "function_name" and argValue = "" )'
    )

def family_clause_argument(subcategory: str, tokens, alt: str):
    toks_lower = [t.lower() for t in tokens]
    expanded = with_sep_variants(toks_lower)
    lower_group = "|".join(expanded)
    left_boundary = '(^|[^a-zA-Z0-9]|[0-9][-_])'
    right_boundary = '([^a-zA-Z]|$)'
    p1 = f'.*{left_boundary}({lower_group}){right_boundary}.*'
    return (
        f'(not matchesConcatenated(localArgValue) and localArgValue.regexpMatch("{p1}") '
        f'and algorithm = "{subcategory}" and alternative = "{alt}" and source = "function_name" and argValue = "" )'
    )

def generate_query_regexp_calls_and_args():
    """
    Versione family-grouped con varianti sha[-_]?N e camelCase come nel primo messaggio.
    """
    mode_tokens = collect_mode_tokens()
    concat_group = conact_group()

    matches_conc = textwrap.dedent(f"""
        // Helper predicate per concatenazioni di token
        bindingset[s]
        predicate matchesConcatenated(string s) {{
          s.regexpMatch(".*(({concat_group})([-_/0-9]*[a-zA-Z]*)*([^a-zA-Z0-9]|[-_/0-9])+({concat_group})([-_/0-9]*[a-zA-Z]*)*).*")
        }}
    """).rstrip()

    fn_clauses = []
    arg_clauses = []
    for _cat, sub, tokens, alt in flatten_algos_families():
        fn_clauses.append(family_clause_function_name(sub, tokens, alt))
        arg_clauses.append(family_clause_argument(sub, tokens, alt))

    # SAFE's
    for m in mode_tokens:
        p = f'.*((^|[^a-zA-Z0-9]|[0-9][-_])({m})([^a-zA-Z]|$)).*'
        fn_clauses.append(f'(not matchesConcatenated(funcName) and funcName.regexpMatch("{p}") and algorithm = "{m.upper()}" and alternative = "SAFE" and source = "function_name" and argValue = "")')
        arg_clauses.append(f'(not matchesConcatenated(localArgValue) and localArgValue.regexpMatch("{p}") and algorithm = "{m.upper()}" and alternative = "SAFE")')

    header = textwrap.dedent("""
        /**
 * @id cpp/primitives-functions-regexp-analysis
 * @kind problem
 * @problem.severity warning
 * @name Insecure cryptographic algorithm specified by macro
 * @description Finds an insecure cryptographic algorithm specified as a macro. This query prioritizes the longest matching token to provide the most specific result.
 * @tags security
 * cryptography
         */
        import cpp
    """).lstrip()

    body_start = textwrap.dedent("""
        from FunctionCall call, Function f, string algorithm, string alternative, string source, string argValue
        where
        call.getLocation().getFile().getAbsolutePath().matches("%/home%") and
          f = call.getTarget() and
          (
            (
              exists(string funcName, string originalFuncName |
                funcName = f.getName().toLowerCase() and
                originalFuncName = f.getName() |
                (matchesConcatenated(funcName) and algorithm = "Concatenated" and alternative = "Separate algorithms recommended" and source = "function_name" and argValue = "") or
    """)

    body_mid = textwrap.dedent("""
              )
            ) or
            (
              exists(Expr arg, string localArgValue |
                arg = call.getAnArgument() and
                (
                  (arg instanceof StringLiteral and localArgValue = arg.(StringLiteral).getValue().toLowerCase()) or
                  (arg instanceof FunctionCall and localArgValue = arg.(FunctionCall).getTarget().getName().toLowerCase()) or
                  (arg instanceof VariableAccess and localArgValue = arg.(VariableAccess).getTarget().getName().toLowerCase())
                ) and
                argValue = localArgValue and
                source = "argument" and
                (
                  (matchesConcatenated(localArgValue) and algorithm = "Concatenated" and alternative = "Separate algorithms recommended") or
    """)

    tail = textwrap.dedent("""
                )
              )
            )
          )
select call,
  "Call to '" + call.getTarget().getName() + "' uses an insecure algorithm via argument '" + argValue.toString() + "Category: " + algorithm  + ". Recommended alternative: " + alternative + "."

    """)

    return (
        header + "\n" + matches_conc + "\n\n" +
        body_start + "\n                or ".join(fn_clauses) + "\n" +
        body_mid + "\n                  or ".join(arg_clauses) + "\n" +
        tail
    )

def generate_query_regexp_macro():
    """
    Macro: stessa logica di famiglia, su macName in minuscolo, con sha[-_]?N.
    """
    mode_tokens = collect_mode_tokens()
    concat_group = conact_group()

    matches_conc = textwrap.dedent(f"""
        bindingset[s]
        predicate matchesConcatenated(string s) {{
          s.regexpMatch(".*(({concat_group})([-_/0-9]*[a-zA-Z]*)*([^a-zA-Z0-9]|[-_/0-9])+({concat_group})([-_/0-9]*[a-zA-Z]*)*).*")
        }}
    """).rstrip()

    macro_clauses = []
    for _cat, sub, tokens, alt in flatten_algos_families():
        toks_lower = [t.lower() for t in tokens]
        expanded = with_sep_variants(toks_lower)
        lower_group = "|".join(expanded)
        p = f'.*((^|[^a-zA-Z0-9]|[0-9][-_])({lower_group})([^a-zA-Z]|$)).*'
        macro_clauses.append(f'(not matchesConcatenated(macName) and macName.regexpMatch("{p}") and algorithm = "{sub}" and alternative = "{alt}")')
    for m in mode_tokens:
        p = f'.*((^|[^a-zA-Z0-9]|[0-9][-_])({m})([^a-zA-Z]|$)).*'
        macro_clauses.append(f'(not matchesConcatenated(macName) and macName.regexpMatch("{p}") and algorithm = "{m.upper()}" and alternative = "SAFE")')

    header = textwrap.dedent("""
        /**
 * @id cpp/primitives-macro-regexp-analysis
 * @kind problem
 * @problem.severity warning
 * @name Insecure cryptographic algorithm specified by macro
 * @description Finds an insecure cryptographic algorithm specified as a macro. This query prioritizes the longest matching token to provide the most specific result.
 * @tags security
 * cryptography
         */
        import cpp
    """).lstrip()

    body = textwrap.dedent("""
        from MacroInvocation mi, string macName, string algorithm, string alternative
        where
        mi.getLocation().getFile().getAbsolutePath().matches("%/home%") and
        macName = mi.getMacro().getName().toLowerCase() and
          (
            (matchesConcatenated(macName) and algorithm = "Concatenated" and alternative = "Separate algorithms recommended")
            or
    """)

    tail = textwrap.dedent("""
          )
select mi,
\n  " Macro '" + mi.getMacro().getName() + "' used for an insecure algorithm." + "Algorithm: " + algorithm + " Recommended alternative: " + alternative + "."

    """)

    return header + "\n" + matches_conc + "\n\n" + body + "\n            or ".join(macro_clauses) + "\n" + tail
# ======== Fine added features ========

def main():
    if len(sys.argv) < 2:
        print("Usage: python query_maker.py <library_id_1> [<library_id_2> ...]")
        print("Example: python query_maker.py 1 3")
        sys.exit(1)
    try:
        library_ids = [int(arg) for arg in sys.argv[1:]]
    except ValueError:
        print("Error: All provided library IDs must be valid integers.")
        sys.exit(1)

    # --- Generate Query for Primitives WITHOUT Arguments ---
    conn_no_args = None
    try:
        conn_no_args = sqlite3.connect(DB_PATH)
        conn_no_args.row_factory = sqlite3.Row
        query_noargs = generate_query_no_args(conn_no_args, library_ids)
        print("-" * 60)
        if not query_noargs:
            print("No primitives found for the 'no-args' query or failed to generate.")
        else:
            filename = os.path.join(OUTPUT_DIR, "query_noargs.ql")
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(query_noargs)
            print(f"Generated: {filename}")
    except sqlite3.Error as e:
        print(f"Database error occurred during 'no-args' query generation: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn_no_args:
            conn_no_args.close()

    # --- Generate Query for Primitives WITH Arguments ---
    conn_with_args = None
    try:
        conn_with_args = sqlite3.connect(DB_PATH)
        conn_with_args.row_factory = sqlite3.Row
        query_with_args = generate_query_with_args(conn_with_args, library_ids)
        print("-" * 60)
        if not query_with_args:
             print("No primitives found for the 'with-args' query or failed to generate.")
        else:
            filename_args = os.path.join(OUTPUT_DIR, "query_with_args.ql")
            with open(filename_args, 'w', encoding='utf-8') as f:
                f.write(query_with_args)
            print(f"Generated: {filename_args}")
    except sqlite3.Error as e:
        print(f"Database error occurred during 'with-args' query generation: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn_with_args:
            conn_with_args.close()

    print("-" * 60)

    # --- Generate Query for Macro ---
    query_macro = generate_query_macros()
    filename_macro = os.path.join(OUTPUT_DIR, "query_macro.ql")
    with open(filename_macro, 'w', encoding='utf-8') as f:
        f.write(query_macro)
    print(f"Generated: {filename_macro}")
    print("-" * 60)

    # --- Generate Query REGEXP Calls+Args (family grouped, sha[-_]?N, camelCase) ---
    q_calls_args = generate_query_regexp_calls_and_args()
    file_calls_args = os.path.join(OUTPUT_DIR, "query_regexp_calls_and_args.ql")
    with open(file_calls_args, "w", encoding="utf-8") as f:
        f.write(q_calls_args)
    print(f"Generated: {file_calls_args}")

    # --- Generate Query REGEXP Macro (family grouped, sha[-_]?N) ---
    q_macro_regexp = generate_query_regexp_macro()
    file_macro_regexp = os.path.join(OUTPUT_DIR, "query_regexp_macro.ql")
    with open(file_macro_regexp, "w", encoding="utf-8") as f:
        f.write(q_macro_regexp)
    print(f"Generated: {file_macro_regexp}")

if __name__ == "__main__":
    main()
