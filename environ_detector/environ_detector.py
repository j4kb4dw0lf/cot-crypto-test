import os
import re
import sys
import subprocess

def find_project_files(root_path):
    project_files = []
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            if filename.lower().startswith('makefile') or \
               filename.endswith(('.h', '.hpp', '.c', '.cpp', '.cc', '.in', '.cmake', '.txt', '.am', '.ac', 'CMakeLists.txt')):
                project_files.append(os.path.join(dirpath, filename))
    return project_files

def parse_makefile(filepath):
    libs = set()
    flags = set()
    env_vars = set()
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            libs.update(re.findall(r'-l(\w+)', line))
            flags.update(re.findall(r'(-[IDWmfO][^\s]+)', line))
            flags.update(re.findall(r'(-std=[^\s]+)', line))
            flags.update(re.findall(r'(-Wall|-Wextra|-pedantic|-g|-O\d|-pthread)', line))
            env_vars.update(re.findall(r'\$\((\w+)\)', line))
    return libs, flags, env_vars

def parse_cmake(filepath):
    libs = set()
    flags = set()
    env_vars = set()
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            libs.update(re.findall(r'target_link_libraries\([^\)]*([^\s\)]+)', line))
            flags.update(re.findall(r'(?:add_compile_options|set)\s*\([^\)]*(-[^\s\)]+)', line))
            env_vars.update(re.findall(r'\$ENV\{(\w+)\}', line))
    return libs, flags, env_vars

def parse_header(filepath):
    includes = set()
    macros = set()
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            match = re.match(r'\s*#\s*include\s*[<"]([^">]+)[">]', line)
            if match:
                includes.add(match.group(1))
            macro = re.match(r'\s*#\s*define\s+(\w+)', line)
            if macro:
                macros.add(macro.group(1))
    return includes, macros

def parse_source(filepath):
    functions = set()
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # Simple function call detection
            for match in re.findall(r'(\w+)\s*\(', line):
                if match not in ('if', 'for', 'while', 'switch', 'return', 'sizeof') and match not in functions:
                    functions.add(match)
                if "ml_kem" in match:
                    input("Found ml_kem function call, press Enter to continue...")
                    print(f"Found ml_kem function call: {match}")

    return functions

def detect_compiler(path):
    compilers = set()
    for root, _, files in os.walk(path):
        for file in files:
            if file.lower().startswith('makefile'):
                with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if re.search(r'\b(gcc|g\+\+|clang|clang\+\+|icc|cc|c\+\+)\b', line):
                            compilers.update(re.findall(r'\b(gcc|g\+\+|clang|clang\+\+|icc|cc|c\+\+)\b', line))
    return compilers

def scan_project(path):
    files = find_project_files(path)
    all_libs = set()
    all_flags = set()
    all_includes = set()
    all_macros = set()
    all_env_vars = set()
    all_functions = set()
    all_compilers = set()
    cmake_present = False

    for file in files:
        basename = os.path.basename(file).lower()
        if basename.startswith('makefile'):
            libs, flags, env_vars = parse_makefile(file)
            all_libs.update(libs)
            all_flags.update(flags)
            all_env_vars.update(env_vars)
        elif basename == 'cmakelists.txt' or file.endswith('.cmake'):
            cmake_present = True
            libs, flags, env_vars = parse_cmake(file)
            all_libs.update(libs)
            all_flags.update(flags)
            all_env_vars.update(env_vars)
        elif file.endswith(('.h', '.hpp')):
            includes, macros = parse_header(file)
            all_includes.update(includes)
            all_macros.update(macros)
        elif file.endswith(('.c', '.cpp', '.cc')):
            functions = parse_source(file)
            all_functions.update(functions)

    all_compilers.update(detect_compiler(path))

    # Try to detect compiler version if possible
    compiler_versions = {}
    for compiler in all_compilers:
        try:
            output = subprocess.check_output([compiler, '--version'], stderr=subprocess.STDOUT, universal_newlines=True, timeout=2)
            compiler_versions[compiler] = output.split('\n')[0]
        except Exception:
            compiler_versions[compiler] = 'Unknown or not found'

    return {
        'libraries': sorted(all_libs),
        'flags': sorted(all_flags),
        'includes': sorted(all_includes),
        'macros': sorted(all_macros),
        'env_vars': sorted(all_env_vars),
        'functions': sorted(all_functions),
        'compilers': sorted(all_compilers),
        'compiler_versions': compiler_versions,
        'cmake_present': cmake_present
    }
