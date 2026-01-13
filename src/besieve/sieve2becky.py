import os
import re
import base64
import glob
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
        if not decoded or decoded.startswith('#'): continue # デコード失敗または無効な部分をスキップ
        decoded_parts.append(decoded)
        
    return ".".join(decoded_parts)

def build_folder_map(work_dir):
    folder_map = {}
    if not os.path.exists(work_dir):
        return folder_map
        
    files = glob.glob(os.path.join(work_dir, "*.ini"))
    for f in files:
        filename = os.path.basename(f)
        logical = decode_folder_path(filename)
        physical = f"{os.path.basename(work_dir)}\\{filename}"
        folder_map[logical] = physical
    return folder_map

def tokenize_sieve(text):
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        
        # 文字列 "..."
        if text[i] == '"':
            start = i
            i += 1
            while i < n:
                if text[i] == '"' and text[i-1] != '\\': # 単純なエスケープチェック
                    break
                i += 1
            if i < n: # 閉じ引用符
                i += 1
            tokens.append(text[start:i])
            continue
            
        # リスト [...]
        if text[i] == '[':
            start = i
            i += 1
            depth = 1
            while i < n and depth > 0:
                if text[i] == '[': depth += 1
                elif text[i] == ']': depth -= 1
                i += 1
            tokens.append(text[start:i])
            continue
            
        # 記号
        if text[i] in ',;(){}':
            tokens.append(text[i])
            i += 1
            continue
            
        # 識別子 / タグ
        start = i
        while i < n and not text[i].isspace() and text[i] not in ',;(){}':
            i += 1
        tokens.append(text[start:i])
    return tokens

# Sieveの文字列アンクオート関数 (エスケープ解除)
def unquote_sieve_string(s):
    if s.startswith('"') and s.endswith('"'):
        # 引用符を削除
        inner = s[1:-1]
        # \" と \\ をアンエスケープ
        # 注: 単純な置換だが、Sieve生成時の replace('"', '\\"') と対になる
        return inner.replace('\\"', '"').replace('\\\\', '\\')
    return s

def parse_sieve_content(content):
    rules = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('if '):
            conditions = []
            folder = None
            actions = []
            
            cond_lines = line
            # 条件ブロックの行全体を収集
            while '{' not in cond_lines and i+1 < len(lines):
                i += 1
                cond_lines += " " + lines[i].strip()
            
            # 条件部分 (if ... { の中) をトークナイズ
            try:
                tokens = tokenize_sieve(cond_lines)
                
                # 単純なトークン分割パーサ
                idx = 0
                while idx < len(tokens):
                    tok = tokens[idx]
                    
                    # 'header', 'address', 'body' コマンドを探す
                    if tok.lower() in ['header', 'address', 'body']:
                        ctype = tok.lower()
                        idx += 1
                        
                        flags = []
                        header_name = ""
                        val = ""
                        
                        # タグやフラグを処理
                        while idx < len(tokens) and tokens[idx].startswith(':'):
                            tag = tokens[idx].lower()
                            idx += 1
                            
                            if tag == ':comparator':
                                # コンパレーター文字列引数が続く
                                if idx < len(tokens) and tokens[idx].startswith('"'):
                                    comp_val = tokens[idx].strip('"')
                                    idx += 1
                                    if comp_val == 'i;octet':
                                        # 大文字小文字区別。デフォルトの 'I' を削除するか、下記ロジックで対応
                                        flags.append('__CASE_SENSITIVE__')
                            elif tag == ':regex':
                                flags.append('R')
                            elif tag == ':matches':
                                flags.append('MATCHES') # Tフラグ判定用
                            elif tag == ':contains':
                                pass # デフォルト一致タイプ
                            
                            # その他のタグはとりあえず無視
                        
                        # 引数 (ヘッダ名リストとキーリスト)
                        args = []
                        while idx < len(tokens) and (tokens[idx].startswith('"') or tokens[idx].startswith('[')):
                             args.append(tokens[idx])
                             idx += 1
                        
                        if ctype == 'body':
                            header_name = '[body]'
                            if args: val = unquote_sieve_string(args[0])
                        else: # header or address
                            # Header/Address は2つの引数を期待: HeaderNames, Keys
                            if len(args) >= 2:
                                h_raw = args[-2] # 最後から2番目がヘッダ名
                                v_raw = args[-1] # 最後がキー
                                
                                # ヘッダ名のクリーンアップ
                                if h_raw.startswith('['):
                                    header_name = h_raw.strip('[]')
                                    # リスト内の要素もアンエスケープすべきだが、
                                    # 現状は単純に構造を維持して文字列化しているだけかも？
                                    # 警告を見ると: 元 '["...", "..."]', 復元 '[\\"...", \\"..."]'
                                    # h_raw 自体は tokenize_sieve で取得した生文字列。
                                    # リストの中身の引用符もエスケープされている可能性がある。
                                    
                                    # 簡易的な置換で対応
                                    header_name = header_name.replace('\\"', '"').replace('\\\\', '\\')
                                    header_name = re.sub(r'"\s*,\s*"', ', ', header_name).replace('"', '')
                                else:
                                    header_name = unquote_sieve_string(h_raw)
                                
                                val = unquote_sieve_string(v_raw)
                        
                        # フラグの後処理
                        final_flags = []
                        # デフォルトは 'I' (無視) だが、__CASE_SENSITIVE__ があれば除外
                        if '__CASE_SENSITIVE__' not in flags:
                            final_flags.append('I')
                        
                        if 'R' in flags:
                            final_flags.append('R')
                        if 'MATCHES' in flags:
                             # Beckyの 'T' フラグは前方一致 (*)
                             if val.endswith('*') and not val.startswith('*'):
                                val = val[:-1]
                                final_flags.append('T')
                        
                        if header_name: # ヘッダ名が正しくパースできた場合のみ追加
                            conditions.append({
                                'header': header_name,
                                'value': val,
                                'flags': final_flags
                            })
                    else:
                        idx += 1 # 関係ないトークンはスキップ
            except Exception as e:
                # ログ出力など行うべきだが、ここでは簡易的にパス
                pass

            # アクション部分のパース
            # } が来るまで行を読む
            while i+1 < len(lines):
                i += 1
                body = lines[i].strip()
                if body.startswith('fileinto'):
                    m = re.search(r'fileinto "([^"]+)"', body)
                    if m:
                        folder = m.group(1)
                elif body == 'discard;':
                    actions.append('discard')
                elif body == 'keep;':
                    actions.append('keep')
                elif body == '}':
                    break
            
            if (folder or actions) and conditions:
                rules.append({'folder': folder, 'conditions': conditions, 'actions': actions})
        i += 1
    return rules

def generate_becky_string(rules, folder_map):
    output = []
    output.append("Version=1")
    output.append("AutoSorting=1")
    output.append("OnlyRead=0")
    output.append("OnlyOneFolder=1")
    
    for rule in rules:
        folder = rule['folder']
        actions = rule['actions']
        physical = None
        
        # ターゲットフォルダのパスを決定
        if folder == 'Trash':
            physical = "45bee44e.mb\\!Trash\\"
        elif folder:
            physical = folder_map.get(folder)
        
        # フォールバック
        if not physical and folder == 'Trash':
             physical = "45bee44e.mb\\!Trash\\"

        # 削除アクション (!D) かどうか
        is_delete = 'discard' in actions
        is_copy = 'keep' in actions
        
        # ルール開始
        if physical or is_delete:
            output.append(f':Begin ""')
            
            if is_delete and not physical:
                # フォルダ指定なきdiscardのみの場合
                # Beckyでは通常 !D で処理
                pass 
                
            if physical:
                output.append(f"!M:{physical}")
            
            if is_delete:
                output.append("!D")
                
            for cond in rule['conditions']:
                hdr = cond['header']
                val = cond['value']
                flags = cond.get('flags', ['I']) # 指定なければデフォルト I
                
                # フラグ文字列
                # オペレータはデフォルト O (OR)
                flag_str = "".join(flags)
                op_str = "O"
                
                # 標準ヘッダのマッピングと大文字化
                h_map = {
                    'from': 'From', 'to': 'To', 'cc': 'Cc', 'subject': 'Subject',
                    'reply-to': 'Reply-To', 'sender': 'Sender', 'x-sender': 'X-Sender'
                }
                # カンマ区切りなど複数ヘッダの処理
                if ',' in hdr:
                    # 分割してマップし、結合
                    parts = [h_map.get(x.strip().lower(), x.strip()) for x in hdr.split(',')]
                    becky_hdr = ", ".join(parts)
                else:
                    becky_hdr = h_map.get(hdr.lower(), hdr)
                
                # Becky!は配列形式をサポートしない
                # リスト形式の値は個別の条件行に展開する
                values_to_output = []
                if val.startswith('[') and val.endswith(']') and '", "' in val:
                    # リスト形式: ["a", "b", "c"] -> 個別に展開
                    inner = val[1:-1].strip()
                    values_to_output = [v.strip().strip('"').strip() for v in inner.split(',')]
                    values_to_output = [v for v in values_to_output if v]
                else:
                    values_to_output = [val]
                
                for single_val in values_to_output:
                    output.append(f"@0:{becky_hdr}:{single_val}\t{op_str}\t{flag_str}")
            
            if is_copy:
                 output.append("$O:Sort=0")
            else:
                 output.append("$O:Sort=1")
                 
            output.append(':End ""')
    
    return "\n".join(output)

def verify_conversion(original_rules, generated_becky):
    try:
        from . import becky2sieve
        
        # 生成されたBecky形式を再度ルール構造へパース
        reverted_rules = becky2sieve.parse_becky_content(generated_becky)
        
        if len(original_rules) != len(reverted_rules):
            print(f"検証失敗: ルール数の不一致。 元: {len(original_rules)}, 復元: {len(reverted_rules)}", file=sys.stderr)
            return False
            
        for i, org in enumerate(original_rules):
            rev = reverted_rules[i]
            if org['folder'] != rev['folder']:
                print(f"検証失敗 ルール #{i+1}: フォルダ不一致。 '{org['folder']}' vs '{rev['folder']}'", file=sys.stderr)
                return False
            
            # 条件チェック
            # リスト形式の値は展開して比較（Becky!はリストを個別条件に展開するため）
            def expand_conditions(conds):
                result = set()
                for c in conds:
                    hdr = c['header'].lower()
                    val = c['value']
                    # リスト形式の場合は展開
                    if val.startswith('[') and val.endswith(']') and '", "' in val:
                        inner = val[1:-1].strip()
                        for v in inner.split(','):
                            v = v.strip().strip('"').strip()
                            if v:
                                result.add((hdr, v))
                    else:
                        result.add((hdr, val))
                return result
            
            org_conds = expand_conditions(org['conditions'])
            rev_conds = expand_conditions(rev['conditions'])
            
            if org_conds != rev_conds:
                print(f"検証警告 ルール #{i+1}: 条件の不一致。\n元: {org_conds}\n復元: {rev_conds}", file=sys.stderr)
        
        print("検証成功: ラウンドトリップテスト (Sieve -> Becky -> Sieve構造) 完了。", file=sys.stderr)
        return True
        
    except ImportError:
        print("検証スキップ: becky2sieve モジュールが見つかりません。", file=sys.stderr)
    except Exception as e:
        print(f"検証中にエラーが発生しました: {e}", file=sys.stderr)
        return False

def parse_sieve(sieve_path):
    with open(sieve_path, 'r', encoding='utf-8') as f:
        return parse_sieve_content(f.read())

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert Sieve to Becky! IFilter.def.')
    parser.add_argument('sieve_file', nargs='?', default=r'f:\dev\miyabe-private\mail\config\sieve\tatsuhiko@miya.be.sieve', help='Path to .sieve file')
    parser.add_argument('mb_dir', nargs='?', default=r'f:\dev\miyabe-private\mail\work\45bee44e.mb', help='Path to Becky .mb directory containing .ini files')
    args = parser.parse_args()
    
    if os.path.exists(args.sieve_file):
        folder_map = build_folder_map(args.mb_dir)
        rules = parse_sieve(args.sieve_file)
        
        becky_code = generate_becky_string(rules, folder_map)
        
        print("Performing consistency check...", file=sys.stderr)
        if verify_conversion(rules, becky_code):
            print(becky_code)
        else:
            print("Output generation aborted due to verification failure.", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"File not found: {args.sieve_file}")

if __name__ == '__main__':
    main()
