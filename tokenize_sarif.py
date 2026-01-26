#!/usr/bin/env python3
"""
Tokenize Concatenated Algorithms in SARIF
Automatically called by ui.py after CodeQL analysis to enrich SARIF results
"""
import json
import re
import sys
import os

def load_alternatives_db(json_path):
    """Load and build token-to-alternative mapping from cats_alts.json"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Tokenizer] WARNING: Could not load {json_path}: {e}")
        return {}
    
    token_to_info = {}
    
    # 1. Process ALGOS (algorithms) - Higher priority
    for category, algorithms in data.get('ALGOS', {}).items():
        if isinstance(algorithms, dict):
            for algo_name, tokens in algorithms.items():
                if isinstance(tokens, list):
                    # Find alternative for this algorithm
                    alt = "Review recommended"
                    
                    if category in data.get('ALTS', {}):
                        if isinstance(data['ALTS'][category], dict):
                            if algo_name in data['ALTS'][category]:
                                alt = data['ALTS'][category][algo_name]
                    
                    # Add each token
                    for token in tokens:
                        token_to_info[token.lower()] = {
                            'type': 'algorithm',
                            'category': category,
                            'name': algo_name,
                            'alternative': alt
                        }
    
    # 2. Process OPS (operations/modes) - Only if not already mapped
    for category, operations in data.get('OPS', {}).items():
        if isinstance(operations, dict):
            for op_name, tokens in operations.items():
                if isinstance(tokens, list):
                    # Specific alternatives for modes
                    alt = "Use authenticated modes (GCM, CCM)"
                    
                    if op_name in ['CBC', 'ECB', 'CFB', 'OFB']:
                        alt = "GCM (Authenticated Encryption)"
                    elif op_name == 'XTS-AES':
                        alt = "SAFE (for disk encryption)"
                    elif op_name == 'CTR':
                        alt = "GCM (adds authentication)"
                    
                    for token in tokens:
                        # Only add if not already mapped (algorithms have priority)
                        if token.lower() not in token_to_info:
                            token_to_info[token.lower()] = {
                                'type': 'operation',
                                'category': category,
                                'name': op_name,
                                'alternative': alt
                            }
    
    return token_to_info

def tokenize_crypto(text):
    """Extract all cryptographic tokens from a string"""
    tokens = r"crystals-dilithium|xchacha20poly1305|chacha20poly1305|xsalsa20poly1305|salsa20poly1305|crystals-kyber|hmacsha512256|chachapoly|curve25519|hmacsha256|hmacsha512|dilithium|ecdsap256|ecdsap384|ecdsap521|ripemd160|sosemanuk|whirlpool|xchacha20|blowfish|camellia|chacha20|curve448|frodokem|gosthash|mceliece|poly1305|shake128|shake256|sphincs\+|streebog|xsalsa20|blake2b|blake2s|ed25519|hmacsha|newhope|rainbow|salsa20|sc25519|serpent|sphincs|twofish|aes128|aes192|aes256|blake3|chacha|falcon|keccak|picnic|rabbit|ripemd|sha224|sha256|sha384|sha512|x25519|cast5|des-x|ecdsa|ecies|ed448|eddsa|frodo|hc128|hc256|kyber|tiger|3des|aria|bike|cmac|des3|desx|ecdh|hmac|idea|mars|pmac|seed|sha1|sha2|sha3|sidh|sike|tdes|x448|xmss|aes|blf|ccm|des|dsa|eax|gcm|hqc|lms|md2|md4|md5|ocb|rc2|rc4|rc5|rc6|rsa|sha|sm2|sm3|sm4|twf|dh|cbc|cfb|ctr|ecb|ofb|xts"
    pattern = re.compile(rf"({tokens})", re.IGNORECASE)
    matches = pattern.findall(text.lower())
    return list(dict.fromkeys(matches))

def format_alternatives(tokens, token_db):
    """Generate formatted alternative suggestions for detected tokens"""
    suggestions = []
    
    for token in tokens:
        if token in token_db:
            info = token_db[token]
            algo_name = info['name']
            alt = info['alternative']
            
            # Format: "TOKEN (Algorithm) → Alternative"
            suggestions.append(f"{token.upper()} ({algo_name}) → {alt}")
        else:
            # Fallback for unmapped tokens
            suggestions.append(f"{token.upper()} → Review manually")
    
    return suggestions

def process_sarif_inplace(sarif_path, token_db):
    """
    Process a SARIF file, tokenizing Concatenated results in-place
    Overwrites the original file with enriched version
    """
    print(f"[Tokenizer] Loading SARIF: {sarif_path}")
    
    try:
        with open(sarif_path, 'r', encoding='utf-8') as f:
            sarif = json.load(f)
    except Exception as e:
        print(f"[Tokenizer] ERROR: Failed to load SARIF: {e}")
        return False
    
    processed_count = 0
    total_concatenated = 0
    
    for run in sarif.get('runs', []):
        for result in run.get('results', []):
            msg = result.get('message', {}).get('text', '')
            
            # Check if it's a "Concatenated" result
            if 'Algorithm:Concatenated' not in msg:
                continue
            
            total_concatenated += 1
            
            # Extract snippet after "Vuln content:"
            match = re.search(r'Vuln content:(.+?)(?:\n|$)', msg)
            if not match:
                continue
            
            snippet = match.group(1).strip()
            
            # Tokenize
            tokens = tokenize_crypto(snippet)
            
            if not tokens:
                # No tokens found, keep original
                continue
            
            # Get alternatives for each token
            alternatives = format_alternatives(tokens, token_db)
            
            # Create enriched message with specific alternatives
            new_message = (
                f"Vuln content:{snippet}\n"
                f"Algorithm:Concatenated (Tokenized)\n"
                f"Detected Components: {', '.join([t.upper() for t in tokens])}\n"
                f"\n"
                f"Post-Quantum Migration Recommendations:\n" +
                "\n".join([f"  • {alt}" for alt in alternatives])
            )
            
            result['message']['text'] = new_message
            processed_count += 1
    
    # Save enriched SARIF (overwrite original)
    try:
        with open(sarif_path, 'w', encoding='utf-8') as f:
            json.dump(sarif, f, indent=2)
        
        print(f"[Tokenizer] Processed {processed_count}/{total_concatenated} Concatenated results")
        print(f"[Tokenizer] Enriched SARIF saved: {sarif_path}")
        return True
        
    except Exception as e:
        print(f"[Tokenizer] ERROR: Failed to save SARIF: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tokenize_sarif.py <sarif_file>")
        sys.exit(1)
    
    sarif_file = sys.argv[1]
    
    # Load alternatives database (cats_alts.json in same directory as script)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    alts_db_path = os.path.join(script_dir, "cli_tool", "utils", "cats_alts.json")
    
    print(f"[Tokenizer] Loading alternatives database: {alts_db_path}")
    token_db = load_alternatives_db(alts_db_path)
    
    if token_db:
        print(f"[Tokenizer] Loaded {len(token_db)} token mappings")
    else:
        print("[Tokenizer] WARNING: No token mappings loaded, using fallback")
    
    success = process_sarif_inplace(sarif_file, token_db)
    sys.exit(0 if success else 1)
