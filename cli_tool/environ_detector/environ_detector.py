import os
import re
import subprocess

def find_project_files(root_path):
    project_files = []
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            lower = filename.lower()
            full = os.path.join(dirpath, filename)
            if lower.startswith('makefile') or filename == 'CMakeLists.txt' or lower.endswith('.cmake'):
                project_files.append(full)
            elif lower.endswith(('.ac', '.in')) and any(tok in lower for tok in ('configure', 'ac', 'in')):
                project_files.append(full)
    return project_files

def parse_makefile(filepath):
    libs = set()
    flags = set()
    env_vars = set()
    pattern_lib = re.compile(r"-l\s*([A-Za-z][A-Za-z0-9_\-]+)\b")
    raw = open(filepath, 'r', encoding='utf-8', errors='ignore').read()
    content = raw.replace('\\\n', ' ')
    lines = [l for l in content.split('\n') if any(tok in l for tok in ('LDFLAGS', 'LDLIBS', 'LIBS', '-l'))]
    text = '\n'.join(lines)
    libs.update(pattern_lib.findall(text))
    flags.update(re.findall(r'(-I[^\s]+|-D[^\s]+|-std=[^\s]+|-W[^\s]+|-O[0-3])', text))
    env_vars.update(re.findall(r'\$\((\w+)\)', content))
    return libs, flags, env_vars

def parse_autoconf(filepath):
    libs = set()
    flags = set()
    env_vars = set()
    raw = open(filepath, 'r', encoding='utf-8', errors='ignore').read()
    for lib in re.findall(r'AC_CHECK_LIB\s*\(\s*\[?"?([A-Za-z0-9_\-]+)"?\]?', raw):
        libs.add(lib)
    for mods in re.findall(r'PKG_CHECK_MODULES\s*\(\s*\[?\w+\]?\s*,\s*\[?"?([^\]]+)"?\]?', raw):
        for m in re.split(r'[\s,]+', mods):
            if m:
                libs.add(m)
    for flagvar in ('CPPFLAGS', 'LDFLAGS'):
        for val in re.findall(rf'{flagvar}\s*=\s*(.+)', raw):
            flags.update(re.findall(r'(-I[^\s]+|-L[^\s]+|-l[^\s]+)', val))
    return libs, flags, env_vars

def parse_cmake(filepath):
    libs = set()
    flags = set()
    env_vars = set()
    content = open(filepath, 'r', encoding='utf-8', errors='ignore').read()
    for block in re.findall(r'target_link_libraries\s*\(([^)]+)\)', content, flags=re.DOTALL):
        parts = re.split(r'[\s\n]+', block.strip())
        for token in parts[1:]:
            t = token.strip()
            if not t or t.upper() in ('PUBLIC', 'PRIVATE', 'INTERFACE'):
                continue
            if t.startswith('$') or os.path.sep in t or '/' in t or t.endswith('.lib'):
                continue
            libs.add(re.sub(r'\$<[^>]+>', '', t))
    flags.update(re.findall(r'(?:add_compile_options|set\s*\(.*CMAKE_CXX_FLAGS[^\)]*)(-[^\s\)]+)', content, flags=re.DOTALL))
    env_vars.update(re.findall(r'\$ENV\{(\w+)\}', content))
    return libs, flags, env_vars

def scan_project(path):
    files = find_project_files(path)
    all_libs = set()
    all_flags = set()
    all_env_vars = set()
    all_compilers = set()
    cmake_present = False

    for filepath in files:
        lower = os.path.basename(filepath).lower()
        if lower.startswith('makefile'):
            libs, flags, env = parse_makefile(filepath)
        elif lower.endswith(('.ac', '.in')):
            libs, flags, env = parse_autoconf(filepath)
        elif filepath.endswith('CMakeLists.txt') or lower.endswith('.cmake'):
            cmake_present = True
            libs, flags, env = parse_cmake(filepath)
        else:
            continue
        all_libs.update(libs)
        all_flags.update(flags)
        all_env_vars.update(env)

    for filepath in files:
        if os.path.basename(filepath).lower().startswith('makefile'):
            text = open(filepath, 'r', encoding='utf-8', errors='ignore').read()
            all_compilers.update(re.findall(r'\b(gcc|g\+\+|clang|clang\+\+|icc|cc|c\+\+)\b', text))

    compiler_versions = {}
    for comp in all_compilers:
        try:
            out = subprocess.check_output([comp, '--version'], stderr=subprocess.STDOUT, universal_newlines=True, timeout=2)
            compiler_versions[comp] = out.split('\n')[0]
        except Exception:
            compiler_versions[comp] = 'Unknown'

    return {
        'libraries': sorted(all_libs),
        'flags': sorted(all_flags),
        'env_vars': sorted(all_env_vars),
        'compilers': sorted(all_compilers),
        'compiler_versions': compiler_versions,
        'cmake_present': cmake_present
    }

if __name__ == '__main__':
    import json, sys
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    print(json.dumps(scan_project(root), indent=2))
