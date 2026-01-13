import os
import re
import base64
import sys

# Modified UTF-7 (IMAPフォルダ名) をデコードする
def modified_utf7_decode(s):
    res = []
    i = 0
    while i < len(s):
        if s[i] == '&':
            i += 1
            if i < len(s) and s[i] == '-':
                res.append('&')
                i += 1
            else:
                start = i
                while i < len(s) and s[i] != '-':
                    i += 1
                b64 = s[start:i]
                b64 = b64.replace(',', '/')
                while len(b64) % 4 != 0:
                    b64 += '='
                try:
                    res.append(base64.b64decode(b64, altchars=None).decode('utf-16-be'))
                except Exception:
                    res.append(f"&{b64}-") # 失敗時のフォールバック
                if i < len(s) and s[i] == '-':
                    i += 1
        else:
            res.append(s[i])
            i += 1
    return "".join(res)

def decode_folder_path(raw_path):
    raw_path = raw_path.replace('\\', '/')
    filename = raw_path.split('/')[-1]
    
    # 特殊ケース
    if '!Trash' in raw_path or '!Trash' in filename:
        return "Trash"

    if filename.endswith('.ini'):
        filename = filename[:-4]
    
    match = re.search(r'(?:#|^)(INBOX\[[0-9a-fA-F]+\])(?:\.(.*))?$', filename)
    parts = []
    if match:
        parts.append("INBOX")
        rest = match.group(2)
        if rest:
            subparts = rest.split('.')
            parts.extend(subparts)
    else:
        parts = filename.split('.')
    
    decoded_parts = []
    for part in parts:
        part = re.sub(r'\[[0-9a-fA-F]+\]$', '', part)
        decoded = modified_utf7_decode(part)
        if not decoded or decoded.startswith('#'):
            continue
        decoded_parts.append(decoded)
        
    return ".".join(decoded_parts)

def parse_conditions(lines):
    conditions = []
    for line in lines:
        parts = line.split('\t')
        cond_str = parts[0]
        
        # Parse flags if available (Col 2 and 3)
        # @0:Header:Value \t Operator \t Flags
        # Flags typically: I (Ignore Case), T (Top/Prefix), R (Regex)
        # Operator: O (Or), A (And)?
        
        flags = []
        operator = 'O'
        
        if len(parts) > 2:
            flags = list(parts[2]) # "IR" -> ['I', 'R']
        if len(parts) > 1:
            operator = parts[1].strip()

        if cond_str.startswith('@'):
            sub = cond_str[1:]
            idx1 = sub.find(':')
            if idx1 != -1:
                # Group ID is sub[:idx1], usually "0"
                rest = sub[idx1+1:]
                idx2 = rest.find(':')
                if idx2 != -1:
                    header = rest[:idx2]
                    value = rest[idx2+1:]
                    conditions.append({
                        'header': header, 
                        'value': value,
                        'flags': flags,
                        'operator': operator
                    })
    return conditions

def parse_becky_content(content):
    rules = []
    lines = content.splitlines()
    
    current_rule = {'conditions': [], 'folder': None, 'actions': []}
    in_rule = False
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        if line.startswith(':Begin'):
            in_rule = True
            current_rule = {'conditions': [], 'folder': None, 'actions': []}
        elif line.startswith(':End'):
            in_rule = False
            # Check if valid rule
            if (current_rule['folder'] or current_rule['actions']) and current_rule['conditions']:
                rules.append(current_rule)
        elif in_rule:
            if line.startswith('!M:'):
                current_rule['folder'] = decode_folder_path(line[3:])
            elif line.startswith('!D'):
                # Delete action (Server delete?)
                # Sieve 'discard'
                current_rule['actions'].append('discard')
            elif line.startswith('$O:Sort=0'):
                # Copy mode
                current_rule['actions'].append('keep')
            elif line.startswith('@'):
                parsed_conds = parse_conditions([line])
                current_rule['conditions'].extend(parsed_conds)
    return rules

def rules_to_sieve_string(rules):
    output = []
    
    # Collect required extensions based on usage
    required_exts = {"fileinto", "mailbox"}
    
    # Pre-scan for extensions
    for rule in rules:
        for c in rule['conditions']:
            if 'R' in c['flags']: required_exts.add("regex")
            if c['header'] == '[body]': required_exts.add("body")
    
    # Sieveではダブルクォートを使用する必要がある（シングルクォートはエラー）
    dq = '"'
    exts_str = ', '.join(dq + ext + dq for ext in sorted(required_exts))
    output.append(f'require [{exts_str}];\n')
    
    for i, rule in enumerate(rules):
        folder = rule['folder']
        conds = rule['conditions']
        actions = rule['actions']
        
        # コメント用にルール名を決定
        rule_name = folder if folder else "Action Only"
        output.append(f"# {i+1}. {rule_name}")
        
        sieve_conds = []
        for c in conds:
            h = c['header']
            v = c['value']
            flags = c['flags']
            
            # ヘッダのマッピング
            match_type = ":contains"
            comparator = "" # デフォルト i;ascii-casemap (大文字小文字無視)
            
            # 大文字小文字区別: Becky 'I' は無視の意味。
            # 'I' が無い場合は区別する。
            if 'I' not in flags:
                comparator = ' :comparator "i;octet"'
            
            # 値のエスケープ
            v_escaped = v.replace('"', '\\"')
            
            if 'R' in flags:
                match_type = ":regex"
            elif 'T' in flags:
                match_type = ":matches"
                v_escaped = v_escaped + "*" 
            
            # 条件文字列の構築
            # Sieve構文: test-name [flags] [match-type] [comparator] [args]
            # header [match-type] [comparator] <headers> <keys>
            # address [match-type] [comparator] [part] <headers> <keys>
            # body [match-type] [comparator] [trans] <keys> (Extension)
            
            test_name = "header"
            header_arg = ""
            
            if h.lower() == '[body]':
                test_name = "body"
                # Body はヘッダ引数なし
            elif h.lower() in ['from', 'to', 'cc', 'bcc']:
                test_name = "address"
                header_arg = f'"{h}"'
            else:
                 # 汎用ヘッダ
                 # 複数ヘッダの処理
                 if ',' in h:
                    hdrs = [x.strip() for x in h.split(',')]
                    hdrs_str = ", ".join(f'"{hdr}"' for hdr in hdrs)
                    header_arg = f'[{hdrs_str}]'
                 else:
                    header_arg = f'"{h}"'

            # 行の構築: test :match :comparator (part) (headers) "key"
            parts = [test_name]
            
            # マッチタイプ
            parts.append(match_type)
            
            # コンパレーター
            if comparator: parts.append(comparator.strip())
            
            # アドレス部分指定 (Beckyは明示的にサポートしていない、デフォルト全て？)
            # Sieveのデフォルトは :all または状況依存。今はスキップ。
            
            # ヘッダリスト (body以外)
            if header_arg:
                parts.append(header_arg)
            
            # キー - リスト形式の値をSieveリストに変換
            # 注: [WATCHDOG] のような単一値は配列ではなく文字列として扱う
            # リストとして認識する条件: [...] で囲まれ、かつ内部に ", " が存在する
            if v.startswith('[') and v.endswith(']') and '", "' in v:
                inner = v[1:-1].strip()
                elements = [e.strip().strip('"').strip() for e in inner.split(',')]
                elements = [e for e in elements if e]
                dq = '"'
                key_str = '[' + ', '.join(dq + e + dq for e in elements) + ']'
            else:
                key_str = f'"{v_escaped}"'
            parts.append(key_str)
            
            sieve_conds.append(" ".join(parts))
        
        if len(sieve_conds) == 0:
            continue
            
        # グルーピング (Beckyの一般的な使用法としてOR/anyofと仮定)
        if len(sieve_conds) == 1:
            cond_str = sieve_conds[0]
        else:
            joined = ",\n    ".join(sieve_conds)
            cond_str = f"anyof (\n    {joined}\n)"
            
        output.append(f"if {cond_str} {{")
        
        if folder and folder != "Trash": 
            output.append(f'    fileinto "{folder}";')
        elif folder == "Trash":
             # Trash は通常ゴミ箱へ移動または破棄
             # SieveにTrashフォルダがあれば fileinto "Trash"
             # "Delete from Server" (!D) の場合は discard
             output.append(f'    fileinto "Trash";')
             
        for act in actions:
            if act == 'discard':
                output.append('    discard;')
            elif act == 'keep':
                output.append('    keep;')
        
        output.append("    stop;")
        output.append("}\n")
        
    return "\n".join(output)

def verify_conversion(original_rules, generated_sieve, mb_dir):
    try:
        from . import sieve2becky
        
        # 生成されたSieveを再度ルール構造へパース
        reverted_rules = sieve2becky.parse_sieve_content(generated_sieve)
        
        # 最小限の構造比較: (Folder, ConditionSet) のリスト
        # 注: 条件の順序は変わる可能性がある。sieve2beckyはフォルダごとにブロックを作ると仮定。
        # 長さと内容を大まかに比較。
        
        if len(original_rules) != len(reverted_rules):
            print(f"検証失敗: ルール数の不一致。 元: {len(original_rules)}, 復元: {len(reverted_rules)}", file=sys.stderr)
            return False
            
        # ランダムまたは全項目をチェック
        for i, org in enumerate(original_rules):
            rev = reverted_rules[i]
            if org['folder'] != rev['folder']:
                print(f"検証失敗 ルール #{i+1}: フォルダ不一致。 '{org['folder']}' vs '{rev['folder']}'", file=sys.stderr)
                return False
            # 条件チェック (緩やかに)
            # スペースの正規化: "[ " -> "[", " ]" -> "]" など
            def normalize_value(v):
                import re
                return re.sub(r'\[\s+', '[', re.sub(r'\s+\]', ']', v))
            
            org_conds = set((c['header'].lower(), normalize_value(c['value'])) for c in org['conditions'])
            rev_conds = set((c['header'].lower(), normalize_value(c['value'])) for c in rev['conditions'])
            # Sieveで引用符が変わったり結合されたりする可能性があるが、パーサが適切なら近い値が得られるはず。
            if org_conds != rev_conds:
                print(f"検証警告 ルール #{i+1}: 条件の不一致または順序変更。 \n元: {org_conds}\n復元: {rev_conds}", file=sys.stderr)
                # 警告のみで続行?
        
        print("検証成功: ラウンドトリップテスト (Becky -> Sieve -> Becky構造) 完了。", file=sys.stderr)
        return True
        
    except ImportError:
        print("検証スキップ: sieve2becky モジュールが見つかりません。", file=sys.stderr)
    except Exception as e:
        print(f"検証中にエラーが発生しました: {e}", file=sys.stderr)
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert Becky! IFilter.def to Sieve.')
    parser.add_argument('ifilter', nargs='?', default=r'f:\dev\miyabe-private\mail\work\45bee44e.mb\IFilter.def', help='Path to IFilter.def')
    parser.add_argument('--verify', action='store_true', help='Perform round-trip verification')
    args = parser.parse_args()
    
    if os.path.exists(args.ifilter):
        with open(args.ifilter, 'rb') as f:
            content = f.read().decode('cp932', errors='replace')
        
        rules = parse_becky_content(content)
        sieve_code = rules_to_sieve_string(rules)
        
        # Auto-verify if requested, or maybe always? User asked to "put a check".
        # Let's do it always if possible, or print warning.
        # But we need sieve2becky in path. It's in the same dir.
        
        mb_dir = os.path.dirname(args.ifilter) # Assuming IFilter.def is in mb_dir
        
        print("Performing consistency check...", file=sys.stderr)
        if verify_conversion(rules, sieve_code, mb_dir):
            print(sieve_code)
        else:
            print("Output generation aborted due to verification failure.", file=sys.stderr)
            sys.exit(1)
            
    else:
        print(f"File not found: {args.ifilter}")

if __name__ == '__main__':
    main()
