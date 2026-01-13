import unittest
import os
import sys

# Add src directory to path for package import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from besieve import becky2sieve
from besieve import sieve2becky

class TestConversion(unittest.TestCase):

    def test_utf7_decode(self):
        # "INBOX.印刷" -> INBOX.&U3BSNw- -> INBOX.印刷
        self.assertEqual(becky2sieve.modified_utf7_decode('&U3BSNw-'), '印刷')
        # "メイズ" -> &MOEwpDC6-
        self.assertEqual(becky2sieve.modified_utf7_decode('&MOEwpDC6-'), 'メイズ')
        
    def test_decode_folder_path_becky2sieve(self):
        # Test complex nested path from Becky filename
        raw = r'45bee44e.mb\#account#INBOX[1f].&U3BSNw-[3a].ini'
        decoded = becky2sieve.decode_folder_path(raw)
        self.assertEqual(decoded, 'INBOX.印刷')

    def test_decode_folder_path_sieve2becky(self):
        # Test similar logic in sieve2becky
        raw = r'#account#INBOX[1f].&U3BSNw-[3a].ini'
        decoded = sieve2becky.decode_folder_path(raw)
        self.assertEqual(decoded, 'INBOX.印刷')
        
        # Test Trash
        self.assertEqual(sieve2becky.decode_folder_path('!Trash'), 'Trash')
        self.assertEqual(sieve2becky.decode_folder_path('directory/!Trash'), 'Trash')

    def test_becky_flags_parsing(self):
        lines = ["@0:From:example.com\tO\tI"]
        conds = becky2sieve.parse_conditions(lines)
        self.assertEqual(len(conds), 1)
        self.assertEqual(conds[0]['header'], 'From')
        self.assertEqual(conds[0]['value'], 'example.com')

    def test_round_trip_becky_dummy(self):
        dummy_becky = os.path.join(os.path.dirname(__file__), 'data', 'dummy_IFilter.def')
        if not os.path.exists(dummy_becky):
            self.skipTest("Dummy Becky file not found")
            
        with open(dummy_becky, 'rb') as f:
            content = f.read().decode('utf-8', errors='replace') # Using utf-8 for created dummy
            
        rules = becky2sieve.parse_becky_content(content)
        sieve_code = becky2sieve.rules_to_sieve_string(rules)
        
        # Verify content
        print(f"DEBUG: sieve_code={sieve_code}")
        self.assertIn('INBOX.Print', sieve_code)
        self.assertIn('Trash', sieve_code)
        
        # Round trip check locally
        reverted_rules = sieve2becky.parse_sieve_content(sieve_code)
        self.assertEqual(len(rules), len(reverted_rules))
        self.assertEqual(rules[0]['folder'], reverted_rules[0]['folder'])

    def test_round_trip_sieve_dummy(self):
        dummy_sieve = os.path.join(os.path.dirname(__file__), 'data', 'dummy.sieve')
        if not os.path.exists(dummy_sieve):
            self.skipTest("Dummy Sieve file not found")
            
        with open(dummy_sieve, 'r', encoding='utf-8') as f:
            content = f.read()
            
        rules = sieve2becky.parse_sieve_content(content)
        # We need a folder map for non-trash folders to be generated
        dummy_map = {'INBOX.Print': '45bee44e.mb\\#account#INBOX[1f].Print[1].ini'}
        becky_code = sieve2becky.generate_becky_string(rules, dummy_map)
        
        self.assertIn(':Begin ""', becky_code)
        # Verify Trash mapping happens even without map
        self.assertIn('!Trash', becky_code) 
        
        # Round trip verify
        reverted_rules = becky2sieve.parse_becky_content(becky_code)
        self.assertEqual(len(rules), len(reverted_rules))
        self.assertEqual(reverted_rules[0]['folder'], 'INBOX.Print') # Should decode back correctly

    def test_round_trip_becky_complex(self):
        dummy_becky = os.path.join(os.path.dirname(__file__), 'data', 'dummy_IFilter_complex.def')
        if not os.path.exists(dummy_becky):
            self.skipTest("Complex Dummy Becky file not found")
            
        with open(dummy_becky, 'rb') as f:
            content = f.read().decode('utf-8', errors='replace') 
            
        rules = becky2sieve.parse_becky_content(content)
        sieve_code = becky2sieve.rules_to_sieve_string(rules)
        
        # Sieveコードの内容検証
        self.assertIn(':regex', sieve_code)          # 正規表現
        self.assertIn('^[0-9]+$', sieve_code)
        self.assertIn(':matches', sieve_code)        # 前方一致 (Tフラグ -> matches + *)
        self.assertIn('"Pre*"', sieve_code)
        self.assertIn('body :contains "Keyword"', sieve_code) # [body]
        self.assertIn(':comparator "i;octet"', sieve_code)    # 大文字小文字区別 (Iなし)
        self.assertIn('discard;', sieve_code)        # !D -> discard
        self.assertIn('keep;', sieve_code)           # $O:Sort=0 -> keep

        # ラウンドトリップ検証
        reverted_rules = sieve2becky.parse_sieve_content(sieve_code)
        self.assertEqual(len(rules), len(reverted_rules))

    def test_round_trip_sieve_complex(self):
        dummy_sieve = os.path.join(os.path.dirname(__file__), 'data', 'dummy_complex.sieve')
        if not os.path.exists(dummy_sieve):
            self.skipTest("Complex Dummy Sieve file not found")
            
        with open(dummy_sieve, 'r', encoding='utf-8') as f:
            content = f.read()
            
        rules = sieve2becky.parse_sieve_content(content)
        
        # ダミーマップでINBOX.RegExなどを解決
        dummy_map = {
            'INBOX.RegEx': '45bee44e.mb\\Regex.ini', 
            'INBOX.Prefix': '45bee44e.mb\\Prefix.ini',
            'INBOX.Body': '45bee44e.mb\\Body.ini',
            'INBOX.Case': '45bee44e.mb\\Case.ini',
            'INBOX.Copy': '45bee44e.mb\\Copy.ini'
        }
        becky_code = sieve2becky.generate_becky_string(rules, dummy_map)
        
        # Beckyの内容検証
        # Regex: R フラグ
        print(f"\nDEBUG Sieve->Becky Output:\n{becky_code}\n")
        
        # Note: Header might be parsed as lowercase 'subject' by sieve parser if not careful, 
        # but our parser generates title case headers in generate_becky_string if in map, otherwise uses mapped map.
        # Let's be flexible with case in regex
        self.assertRegex(becky_code, r'(?i)@0:Subject.*:\^\[0-9\]\+\$\s+O\s+.*R') 
        # Prefix: T フラグ
        self.assertRegex(becky_code, r'(?i)@0:Subject:Pre\s+O\s+.*T') 
        # Body: [body]
        self.assertIn('@0:[body]:Keyword', becky_code)
        
        print(f"DEBUG: Checking regex against:\n{becky_code}")
        # Case Sensitive: Iフラグ無し
        # generate_becky_string outputs flags joined. If empty, it's just \tO\t
        # So we expect \tO\t at end of line
        # Add (?m) for multiline mode so $ matches end of line
        self.assertRegex(becky_code, r'(?im)@0:Subject:Sensitive\s+O\s*\t*$')
        
        # Action !D
        self.assertIn('!D', becky_code)
        # Copy $O:Sort=0
        self.assertIn('$O:Sort=0', becky_code)

        # ラウンドトリップ
        reverted_rules = becky2sieve.parse_becky_content(becky_code)
        self.assertEqual(len(rules), len(reverted_rules))

    def test_string_escaping(self):
        """
        文字列のエスケープ処理（" や \\）が正しく行われるかテスト
        """
        # " を含む値
        becky_rule = ':Begin ""\n!M:TestFolder\n@0:Subject:Say "Hello"\tO\tI\n$O:Sort=1\n:End ""'
        rules = becky2sieve.parse_becky_content(becky_rule)
        sieve_code = becky2sieve.rules_to_sieve_string(rules)
        
        # Sieveコードにはエスケープされた " が含まれるはず
        # header :contains "Subject" "Say \"Hello\""
        self.assertIn('"Say \\"Hello\\""', sieve_code)
        
        # 復元
        reverted_rules = sieve2becky.parse_sieve_content(sieve_code)
        self.assertEqual(len(reverted_rules), 1)
        # 復元された値はエスケープ無しの元の値であるべき
        self.assertEqual(reverted_rules[0]['conditions'][0]['value'], 'Say "Hello"')

    def test_sieve_list_to_becky_expansion(self):
        """
        Sieveのリスト形式がBecky!の個別条件に展開されるかテスト
        Sieve: address :contains "From" ["a@x.com", "b@x.com"]
        Becky!:
          @0:From:a@x.com    O    I
          @0:From:b@x.com    O    I
        """
        sieve_code = '''require ["fileinto", "mailbox"];

# 1. INBOX.Test
if address :contains "From" ["user1@example.com", "user2@example.com", "user3@example.com"] {
    fileinto "INBOX.Test";
    stop;
}
'''
        rules = sieve2becky.parse_sieve_content(sieve_code)
        self.assertEqual(len(rules), 1)
        
        # 条件は1つ（リスト形式）
        self.assertEqual(len(rules[0]['conditions']), 1)
        self.assertIn('user1@example.com', rules[0]['conditions'][0]['value'])
        
        # Becky!コード生成（フォルダマップはダミー）
        dummy_map = {'INBOX.Test': '45bee44e.mb\\\\Test.ini'}
        becky_code = sieve2becky.generate_becky_string(rules, dummy_map)
        
        # 3つの個別条件に展開されているか確認
        self.assertIn('@0:From:user1@example.com', becky_code)
        self.assertIn('@0:From:user2@example.com', becky_code)
        self.assertIn('@0:From:user3@example.com', becky_code)
        
        # 配列形式で出力されていないことを確認
        self.assertNotIn('["user1', becky_code)
        
        # ラウンドトリップ: Beckyに戻してSieveに変換
        reverted_becky_rules = becky2sieve.parse_becky_content(becky_code)
        # 3つの条件として認識される
        self.assertEqual(len(reverted_becky_rules[0]['conditions']), 3)
        
        # 再度Sieveに変換
        sieve_code_2 = becky2sieve.rules_to_sieve_string(reverted_becky_rules)
        # 3つの条件がanyofで結合される
        self.assertIn('anyof', sieve_code_2)
        self.assertIn('user1@example.com', sieve_code_2)
        self.assertIn('user2@example.com', sieve_code_2)
        self.assertIn('user3@example.com', sieve_code_2)

if __name__ == '__main__':
    unittest.main()
