# Becky! <-> Sieve ルール変換ツール

このツールセットは、Becky! Internet Mail (IFilter.def) の振り分けルールと Sieve (RFC 5228) スクリプトを相互に変換します。

## 主な機能

- **フォルダー名の相互変換**: Becky! の Modified UTF-7 エンコードされた内部フォルダー名と、Sieve の論理フォルダー名 (例: `INBOX.Work`) を相互に変換します。
- **条件の変換**:
    - ヘッダー条件 (`Header: ...`)
    - 本文検索 (`[body]`)
    - **正規表現**: Becky! の `R` フラグ ⇔ Sieve の `:regex` (RFC 3894)
    - **前方一致**: Becky! の `T` フラグ ⇔ Sieve の `:matches "value*"`
    - **大文字小文字区別**: Becky! の `I` フラグなし ⇔ Sieve の `:comparator "i;octet"`
- **アクションの変換**:
    - 移動 (`!M`) ⇔ `fileinto`
    - 削除 (`!D`) ⇔ `discard`
    - コピー (`$O:Sort=0` + `!M`) ⇔ `fileinto` + `keep` (または複数の `fileinto`)

## インストール

### pip でインストール（推奨）

```powershell
# パッケージとしてインストール
pip install -e .

# CLIコマンドが使えるようになります
becky2sieve --help
sieve2becky --help
sync-rules --help
```

### 開発用

```powershell
# 開発用依存関係と共にインストール
pip install -e ".[dev]"
```

## スクリプトの使い方

### becky2sieve (Becky! → Sieve)

Becky! の `IFilter.def` ファイルを Sieve スクリプト形式に変換して標準出力に出力します。

```powershell
# インストール後のコマンドライン
becky2sieve "path/to/IFilter.def" > rules.sieve

# または python -m で実行
python -m besieve.becky2sieve "path/to/IFilter.def" > rules.sieve

# 検証モード（再変換して整合性をチェック）
becky2sieve "path/to/IFilter.def" --verify
```

### sieve2becky (Sieve → Becky!)

Sieve スクリプトを Becky! の `IFilter.def` 形式に変換して標準出力に出力します。
フォルダーのマッピングを解決するため、Becky! のメールボックスディレクトリ（`.mb`）へのパスが必要です。

```powershell
sieve2becky "path/to/rules.sieve" "path/to/mailbox.mb" > IFilter.def
```

### sync-rules (一括変換)

`becky.json` に定義された設定に基づき、複数のアカウントのルールを一括で同期・変換します。
設定ファイルの例は `examples/becky.json.sample` を参照してください。

```powershell
# Becky! のルールを Sieve に変換 (Becky -> Sieve)
sync-rules to-sieve

# Sieve のルールを Becky! に変換 (Sieve -> Becky)
sync-rules to-becky

# ラウンドトリップテストをスキップする場合
sync-rules to-sieve --skip-verify
```

**`becky.json` の形式:**
```json
[
    {"account": "user1@example.com", "path": "I:\\path\\to\\user1.mb"},
    {"account": "user2@example.com", "path": "I:\\path\\to\\user2.mb"}
]
```

## ラウンドトリップテスト

変換処理には**ラウンドトリップテスト**が含まれています。これは、相互変換でデータの欠損が起きないことを確認するための仕組みです。

例: `Becky → Sieve → Becky` の変換を行い、元のルール構造と復元されたルール構造を比較します。

- **テスト成功**: 元のデータと復元データが一致する場合、ファイルが書き出されます。
- **テスト失敗**: 不一致がある場合、警告またはエラーが表示され、ファイルの書き込みがスキップされます。

### テストをスキップする場合

一部のデータ欠損を許容する場合（例: 未サポート機能を含むルールを変換する場合）は、`--skip-verify` オプションを使用してテストをスキップできます：

```powershell
python sync_rules.py to-sieve --skip-verify
```

## 単体テストの実行

変換ロジックの単体テストを実行します。

```powershell
# unittest を使用
python -m unittest tests.test_conversion -v

# pytest を使用（開発用依存をインストールした場合）
pytest tests/ -v
```

## 注意点と制限事項 (Limitations)

Sieve と Becky! の機能差により、完全な相互変換ができない場合があります。以下の点に注意してください。

### 未サポートまたは制限のある機能

1.  **AND/OR の複雑な組み合わせ**:
    *   Becky! の条件は基本的に「いずれかの条件に一致 (`O`)」や「すべての条件に一致 (`A`)」ですが、複雑なグループ化（括弧を使ったネスト）は単純に表現できません。
    *   本ツールでは、**Sieve の `anyof (...)` (OR)** を Becky! の `O` フラグ付き条件の列挙として扱います。
    *   `allof` (AND) や、ネストされた `if` 構造は正しく変換されないか、意図しない挙動になる可能性があります。

2.  **Sieve の拡張アクション**:
    *   `redirect` (転送), `vacation` (自動応答), `reject` (拒否) などの Sieve アクションは、Becky! の単純な `IFilter.def` では表現できないため、**無視されるか、コメントとして扱われます**（現状は未実装）。

3.  **アドレス部分指定**:
    *   Sieve の `:localpart` (ユーザ名のみ), `:domain` (ドメインのみ) などの指定は、Becky! に直接対応する機能がないため無視され、フルアドレス (`:all`) として扱われます。

4.  **Becky! 固有のアクション**:
    *   「返信」「転送」「音を鳴らす」「色を変える」などの Becky! 固有のアクションは、Sieve に変換されません（移動、コピー、削除のみサポート）。

5.  **「受信しない」(!D) アクション**:
    *   Becky! の `!D` (サーバーから削除/受信しない) は Sieve の `discard` に変換されますが、誤って設定するとメールが消失する可能性があるため注意してください。

6.  **コメント**:
    *   変換の過程でスクリプト内のコメントは維持されません（ルール名としてフォルダ名が付与されるのみです）。
