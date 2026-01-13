"""
besieve - Becky! <-> Sieve ルール変換ツール

Becky! Internet Mail (IFilter.def) の振り分けルールと
Sieve (RFC 5228) スクリプトを相互に変換するツールです。
"""

__version__ = "1.0.0"

from .becky2sieve import (
    parse_becky_content,
    rules_to_sieve_string,
    verify_conversion as verify_becky_conversion,
)

from .sieve2becky import (
    parse_sieve_content,
    generate_becky_string,
    build_folder_map,
    verify_conversion as verify_sieve_conversion,
)

__all__ = [
    "parse_becky_content",
    "rules_to_sieve_string",
    "verify_becky_conversion",
    "parse_sieve_content",
    "generate_becky_string",
    "build_folder_map",
    "verify_sieve_conversion",
]
