from pathlib import Path

from tracekit.cli import main


def test_cli_diagnoses_python_script_with_typo(tmp_path, capsys):
    script = tmp_path / "crash.py"
    script.write_text(
        "data = {'Name': 'Ada'}\n"
        "print(data['Nmae'])\n"
    )
    exit_code = main(["diagnose", str(script)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "KEY001" in out
    assert "Name" in out
    # Regression check: this exact case (a module-level, not
    # function-scoped, typo) originally failed to fire at all because
    # __builtins__ leaked into the candidate pool via runpy's
    # module-level frame.f_locals — see context.py's dunder filtering
    # and tests/test_property_based.py's dedicated regression test.
    assert "No rule matched" not in out


def test_cli_diagnoses_python_script_with_case_mismatch(tmp_path, capsys):
    script = tmp_path / "crash.py"
    script.write_text(
        "data = {'Username': 'ada'}\n"
        "print(data['username'])\n"
    )
    exit_code = main(["diagnose", str(script)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "KEY002" in out


def test_cli_reports_no_exception_when_script_succeeds(tmp_path, capsys):
    script = tmp_path / "clean.py"
    script.write_text("x = 1 + 1\n")
    exit_code = main(["diagnose", str(script)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "nothing to diagnose" in out


def test_cli_returns_error_for_missing_file(tmp_path, capsys):
    missing = tmp_path / "nope.py"
    exit_code = main(["diagnose", str(missing)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "no such file" in err


def test_cli_parses_traceback_text_and_shows_original_verbatim(tmp_path, capsys):
    tb_file = tmp_path / "traceback.txt"
    original_text = (
        "Traceback (most recent call last):\n"
        '  File "app.py", line 12, in <module>\n'
        '    print(data["username"])\n'
        "KeyError: 'username'\n"
    )
    tb_file.write_text(original_text)

    exit_code = main(["diagnose", str(tb_file)])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "No rule matched" in out
    # The user's original pasted text must appear verbatim — not a
    # synthesized one-line reconstruction — per the project's "never
    # hide the traceback" principle.
    assert original_text.strip() in out


def test_cli_unrecognized_text_file_reports_error(tmp_path, capsys):
    junk = tmp_path / "notes.txt"
    junk.write_text("just some notes, no exception here\n")
    exit_code = main(["diagnose", str(junk)])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "could not find a recognizable exception line" in err
