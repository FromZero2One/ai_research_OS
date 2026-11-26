"""Unit tests for akshare subprocess safety (code-injection guard).

These tests verify that user-supplied tickers are passed to the akshare
subprocess as *data* (environment variables), never interpolated into the
child's Python source.
"""

from __future__ import annotations

import os

import pytest

from market import akshare_executor
from market.service import price_service

MALICIOUS_TICKERS = [
    '600519"; print("PWNED") #',
    "600519' + __import__('os').system('id') + '",
    "600519\\nimport os",
    "600519; rm -rf /",
    "x" * 21,
    "",
    'sh600519"; import os #',
]


class TestBuildAkshareEnv:
    def test_normal_a_stock(self) -> None:
        # Bare key — run_akshare prefixes it to AKSHARE_TICKER in the child.
        assert akshare_executor.build_akshare_env("600519") == {"TICKER": "600519"}

    def test_us_ticker_with_dot(self) -> None:
        assert akshare_executor.build_akshare_env("BRK.B") == {"TICKER": "BRK.B"}

    @pytest.mark.parametrize("ticker", MALICIOUS_TICKERS)
    def test_malicious_ticker_rejected(self, ticker: str) -> None:
        with pytest.raises(ValueError):
            akshare_executor.build_akshare_env(ticker)


class TestCodeTemplatesUseEnv:
    """The subprocess code must read the ticker from the environment only."""

    ENV_LOOKUP = 'os.environ["AKSHARE_TICKER"]'

    @pytest.mark.parametrize(
        "code",
        [
            price_service._AKSHARE_PRICE_CODE_HK,
            price_service._AKSHARE_PRICE_CODE_A,
        ],
    )
    def test_reads_ticker_from_env(self, code: str) -> None:
        assert self.ENV_LOOKUP in code

    @pytest.mark.parametrize(
        "code",
        [
            price_service._AKSHARE_PRICE_CODE_HK,
            price_service._AKSHARE_PRICE_CODE_A,
        ],
    )
    def test_no_symbol_interpolation_in_source(self, code: str) -> None:
        # The old bug: symbol="{ticker}" / symbol='{ticker}' embedded input in code.
        assert 'symbol="{ticker}"' not in code
        assert "symbol='{ticker}'" not in code
        assert "{ticker}" not in code


@pytest.mark.skipif(
    not os.path.isdir(os.getenv("AKSHARE_MCP_DIR", "/home/wsm/codes/akshare_mcp")),
    reason="akshare_mcp venv not present",
)
class TestRunAkshareEnvIsolation:
    def test_hostile_value_passed_as_data_not_code(self) -> None:
        """A hostile value in env_args reaches the child verbatim as data."""
        hostile = '600519"; print("PWNED") #'
        code = 'import os\nprint(os.environ.get("AKSHARE_TICKER", "MISSING"))'
        out = akshare_executor.run_akshare(code, env_args={"TICKER": hostile})

        assert out is not None
        # The literal value comes through intact; if it had been interpreted
        # as code, this exact string would never appear in the output.
        assert hostile in out
        assert out.strip() == hostile

    def test_build_akshare_env_roundtrip(self) -> None:
        """Regression: build_akshare_env output must reach the child as AKSHARE_TICKER.

        Previously build_akshare_env returned the already-prefixed key, and
        run_akshare added a second prefix — the child saw AKSHARE_AKSHARE_TICKER
        and the whole local akshare layer silently fell back to cloud sources.
        """
        code = 'import os\nprint(os.environ.get("AKSHARE_TICKER", "MISSING"))'
        out = akshare_executor.run_akshare(
            code, env_args=akshare_executor.build_akshare_env("600519")
        )
        assert out is not None
        assert out.strip() == "600519"
