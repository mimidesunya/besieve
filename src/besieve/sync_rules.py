import json
import os
import argparse
import sys

from . import becky2sieve
from . import sieve2becky

def get_sieve_path(account):
    return os.path.join('config', 'sieve', f'{account}.sieve')

def get_becky_filter_path(mb_path):
    return os.path.join(mb_path, 'IFilter.def')

def convert_to_sieve(mappings, skip_verify=False):
    print("Converting Becky! rules to Sieve...")
    for entry in mappings:
        account = entry['account']
        mb_path = entry['path']
        
        becky_filter_path = get_becky_filter_path(mb_path)
        sieve_path = get_sieve_path(account)
        
        if not os.path.exists(becky_filter_path):
            print(f"[SKIP] Becky file not found for {account}: {becky_filter_path}")
            continue
            
        print(f"[PROCESS] {account} (Becky -> Sieve)")
        try:
            with open(becky_filter_path, 'rb') as f:
                content = f.read().decode('cp932', errors='replace')
            
            rules = becky2sieve.parse_becky_content(content)
            sieve_code = becky2sieve.rules_to_sieve_string(rules)
            
            # ラウンドトリップテスト（相互変換でデータ欠損がないか確認）
            if not skip_verify:
                mb_dir = os.path.dirname(becky_filter_path)
                if not becky2sieve.verify_conversion(rules, sieve_code, mb_dir):
                    print(f"[ERROR] ラウンドトリップテスト失敗: {account}. ファイル書き込みをスキップします。")
                    continue

            # Ensure dir exists
            os.makedirs(os.path.dirname(sieve_path), exist_ok=True)
            
            with open(sieve_path, 'w', encoding='utf-8') as f:
                f.write(sieve_code)
            print(f"[OK] Wrote {sieve_path}")
            
        except Exception as e:
            print(f"[ERROR] Failed to convert {account}: {e}")

def convert_to_becky(mappings, skip_verify=False):
    print("Converting Sieve rules to Becky!...")
    for entry in mappings:
        account = entry['account']
        mb_path = entry['path']
        
        becky_filter_path = get_becky_filter_path(mb_path)
        sieve_path = get_sieve_path(account)
        
        if not os.path.exists(sieve_path):
            print(f"[SKIP] Sieve file not found for {account}: {sieve_path}")
            continue

        if not os.path.exists(mb_path):
            print(f"[WARN] Mailbox directory not found: {mb_path}. Mapping might be partial.")
            
        print(f"[PROCESS] {account} (Sieve -> Becky)")
        try:
            with open(sieve_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            folder_map = sieve2becky.build_folder_map(mb_path)
            rules = sieve2becky.parse_sieve_content(content)
            becky_code = sieve2becky.generate_becky_string(rules, folder_map)
            
            # ラウンドトリップテスト（相互変換でデータ欠損がないか確認）
            if not skip_verify:
                if not sieve2becky.verify_conversion(rules, becky_code):
                    print(f"[ERROR] ラウンドトリップテスト失敗: {account}. ファイル書き込みをスキップします。")
                    continue

            with open(becky_filter_path, 'wb') as f:
                f.write(becky_code.encode('cp932', errors='replace'))
                
            print(f"[OK] Wrote {becky_filter_path}")

        except Exception as e:
            print(f"[ERROR] Failed to convert {account}: {e}")

def main():
    parser = argparse.ArgumentParser(description='Batch convert mail rules.')
    parser.add_argument('mode', choices=['to-sieve', 'to-becky'], help='Conversion direction')
    parser.add_argument('--config', default='becky.json', help='Path to becky.json')
    parser.add_argument('--skip-verify', action='store_true', 
                        help='ラウンドトリップテストをスキップする（データ欠損を許容する場合）')
    args = parser.parse_args()
    
    if not os.path.exists(args.config):
        print(f"Config file not found: {args.config}")
        sys.exit(1)
        
    with open(args.config, 'r', encoding='utf-8') as f:
        mappings = json.load(f)
        
    if args.mode == 'to-sieve':
        convert_to_sieve(mappings, skip_verify=args.skip_verify)
    else:
        convert_to_becky(mappings, skip_verify=args.skip_verify)

if __name__ == '__main__':
    main()
