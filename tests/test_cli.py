"""Tests for the csvprof CLI and the text/JSON renderers."""

import json
import subprocess
import sys

import pytest

from csvprof.cli import main
from csvprof.profile import profile_csv
from csvprof.report import render_json, render_text


@pytest.fixture
def sample_csv(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("id,name,score\n1,alice,10\n2,bob,20\n3,alice,30\n")
    return str(path)


def test_render_text_contains_key_facts(sample_csv):
    text = render_text(profile_csv(sample_csv))
    assert "Rows: 3" in text
    assert "name" in text
    assert "[integer]" in text
    assert "[string]" in text
    assert "alice" in text


def test_render_json_is_valid(sample_csv):
    data = json.loads(render_json(profile_csv(sample_csv)))
    assert data["rows"] == 3
    assert data["columns"][0]["name"] == "id"
    assert data["columns"][0]["numeric"]["mean"] == 2.0


def test_cli_text_to_stdout(sample_csv, capsys):
    assert main([sample_csv]) == 0
    assert "Rows: 3" in capsys.readouterr().out


def test_cli_json_flag(sample_csv, capsys):
    assert main([sample_csv, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rows"] == 3


def test_cli_output_file(sample_csv, tmp_path):
    out = tmp_path / "report.txt"
    assert main([sample_csv, "-o", str(out)]) == 0
    assert "Rows: 3" in out.read_text()


def test_cli_missing_file_returns_2(capsys):
    assert main(["/nonexistent/file.csv"]) == 2
    assert "no such file" in capsys.readouterr().err


def test_cli_top_flag(sample_csv, capsys):
    assert main([sample_csv, "--top", "1"]) == 0
    assert "alice" in capsys.readouterr().out


def test_console_script_entry_point(sample_csv):
    # Run the real module entry point with the project src on PYTHONPATH.
    import os

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=os.path.join(project_dir, "src"))
    result = subprocess.run(
        [sys.executable, "-m", "csvprof.cli", sample_csv],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0
    assert "Rows: 3" in result.stdout
