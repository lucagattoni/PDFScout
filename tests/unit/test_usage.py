from unittest.mock import MagicMock

from src.utils.usage import summarize_usage, usage_entry


def _resp(inp=100, out=50, read=0, write=0, stop="end_turn"):
    r = MagicMock()
    r.usage.input_tokens = inp
    r.usage.output_tokens = out
    r.usage.cache_read_input_tokens = read
    r.usage.cache_creation_input_tokens = write
    r.stop_reason = stop
    return r


class TestUsageEntry:
    def test_entry_fields(self):
        e = usage_entry("classifier", _resp(10, 5, 100, 200, "tool_use"))
        assert e == {
            "context": "classifier",
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 200,
            "stop_reason": "tool_use",
        }

    def test_flag_off_no_print(self, capsys, monkeypatch):
        monkeypatch.delenv("PDFSCOUT_LOG_USAGE", raising=False)
        usage_entry("x", _resp())
        assert capsys.readouterr().err == ""

    def test_flag_on_prints_stderr(self, capsys, monkeypatch):
        monkeypatch.setenv("PDFSCOUT_LOG_USAGE", "1")
        usage_entry("burst page 2 attempt 1", _resp(read=6653))
        err = capsys.readouterr().err
        assert "[USAGE] burst page 2 attempt 1" in err
        assert "cache_read=6653" in err


class TestSummarizeUsage:
    def test_empty(self):
        t = summarize_usage([])
        assert t["api_calls"] == 0
        assert t["input_tokens"] == 0

    def test_totals(self):
        entries = [
            usage_entry("a", _resp(10, 5, 100, 0)),
            usage_entry("b", _resp(20, 15, 0, 200)),
        ]
        t = summarize_usage(entries)
        assert t["api_calls"] == 2
        assert t["input_tokens"] == 30
        assert t["output_tokens"] == 20
        assert t["cache_read_input_tokens"] == 100
        assert t["cache_creation_input_tokens"] == 200

    def test_tolerates_missing_keys(self):
        assert summarize_usage([{}])["input_tokens"] == 0
