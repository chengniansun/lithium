# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium interestingness-test tests"""

import logging
import platform
import subprocess
import sys
import time
from pathlib import Path

import pytest

import lithium

if platform.system() != "Windows":
    winreg = None  # pylint: disable=invalid-name
else:
    import winreg


CAT_CMD = [
    sys.executable,
    "-c",
    (
        "import sys;"
        "[sys.stdout.write(f.read())"
        " for f in"
        "     ([open(a) for a in sys.argv[1:]] or"
        "      [sys.stdin])"
        "]"
    ),
]
LS_CMD = [
    sys.executable,
    "-c",
    (
        "import glob,itertools,os,sys;"
        "[sys.stdout.write(p+'\\n')"
        " for p in"
        "     (itertools.chain.from_iterable(glob.glob(d) for d in sys.argv[1:])"
        "      if len(sys.argv) > 1"
        "      else os.listdir('.'))"
        "]"
    ),
]
SLEEP_CMD = [sys.executable, "-c", "import sys,time;time.sleep(int(sys.argv[1]))"]
LOG = logging.getLogger(__name__)
# pylint: disable=invalid-name
pytestmark = pytest.mark.usefixtures("tmp_cwd", "_tempjs")


@pytest.fixture
def _tempjs():
    with open("temp.js", "w"):
        pass


def _compile(in_path, out_path):
    """Try to compile a source file using any available C/C++ compiler.

    Args:
        in_path (str): Source file to compile from
        out_path (str): Executable file to compile to

    Raises:
        RuntimeError: Raises this exception if the compilation fails or if the compiler
                      cannot be found
    """
    if platform.system() == "Windows":
        compilers_to_try = ["cl", "clang", "gcc", "cc"]
    else:
        compilers_to_try = ["clang", "gcc", "cc"]

    assert Path(in_path).is_file()
    for compiler in compilers_to_try:
        out_param = "/Fe" if compiler == "cl" else "-o"
        try:
            out = subprocess.check_output(
                [compiler, out_param + str(out_path), str(in_path)],
                stderr=subprocess.STDOUT,
            )
        except OSError:
            LOG.debug("%s not found", compiler)
        except subprocess.CalledProcessError as exc:
            for line in exc.output.splitlines():
                LOG.debug("%s: %s", compiler, line.decode())
        else:
            for line in out.splitlines():
                LOG.debug("%s: %s", compiler, line.decode())
            return
    # all of compilers we tried have failed :(
    raise RuntimeError("Compile failed")


class DisableWER:
    """Disable Windows Error Reporting for the duration of the context manager.

    ref: https://msdn.microsoft.com/en-us/library/bb513638.aspx
    """

    def __init__(self):
        self.wer_disabled = None
        self.wer_dont_show_ui = None

    def __enter__(self):
        if winreg is not None:
            wer = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Windows Error Reporting",
                0,
                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
            )
            # disable reporting to microsoft
            # this might disable dump generation altogether, which is not what we want
            self.wer_disabled = bool(winreg.QueryValueEx(wer, "Disabled")[0])
            if not self.wer_disabled:
                winreg.SetValueEx(wer, "Disabled", 0, winreg.REG_DWORD, 1)
            # don't show the crash UI (Debug/Close Application)
            self.wer_dont_show_ui = bool(winreg.QueryValueEx(wer, "DontShowUI")[0])
            if not self.wer_dont_show_ui:
                winreg.SetValueEx(wer, "DontShowUI", 0, winreg.REG_DWORD, 1)

    def __exit__(self, *args, **kwds):
        # restore previous settings
        if winreg is not None:
            wer = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Windows Error Reporting",
                0,
                winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
            )
            if not self.wer_disabled:
                winreg.SetValueEx(wer, "Disabled", 0, winreg.REG_DWORD, 0)
            if not self.wer_dont_show_ui:
                winreg.SetValueEx(wer, "DontShowUI", 0, winreg.REG_DWORD, 0)


def test_crashes_0():
    """simple positive test for the 'crashes' interestingness test"""
    lith = lithium.Lithium()

    # check that `ls` doesn't crash
    result = lith.main(["--strategy", "check-only", "crashes"] + LS_CMD + ["temp.js"])
    assert result == 1
    assert lith.test_count == 1


def test_crashes_1():
    """timeout test for the 'crashes' interestingness test"""
    lith = lithium.Lithium()

    # check that --timeout works
    start_time = time.time()
    result = lith.main(
        [
            "--strategy",
            "check-only",
            "--testcase",
            "temp.js",
            "crashes",
            "--timeout",
            "1",
        ]
        + SLEEP_CMD
        + ["3"]
    )
    elapsed = time.time() - start_time
    assert result == 1
    assert elapsed >= 1
    assert lith.test_count == 1


def test_crashes_2(examples_path):
    """crash test for the 'crashes' interestingness test"""
    lith = lithium.Lithium()

    # if a compiler is available, compile a simple crashing test program
    src = examples_path / "crash.c"
    exe = Path.cwd().resolve() / (
        "crash.exe" if platform.system() == "Windows" else "crash"
    )
    try:
        _compile(src, exe)
    except RuntimeError as exc:
        LOG.warning(exc)
        pytest.skip("compile 'crash.c' failed")
    with DisableWER():
        result = lith.main(["--strategy", "check-only", "crashes", str(exe), "temp.js"])
    assert result == 0
    assert lith.test_count == 1


def test_diff_test_0():
    """test for the 'diff_test' interestingness test"""
    lith = lithium.Lithium()

    # test that the parameters "-a" and "-b" of diff_test work
    result = lith.main(
        [
            "--strategy",
            "check-only",
            "diff_test",
            "--timeout",
            "99",
            "-a",
            "flags_one",
            "-b",
            "flags_two_a flags_two_b",
        ]
        + LS_CMD
        + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_diff_test_1():
    """test for the 'diff_test' interestingness test"""
    lith = lithium.Lithium()

    # test that the parameters "-a" and "-b" of diff_test work
    result = lith.main(
        [
            "--strategy",
            "check-only",
            "diff_test",
            "--a-args",
            "flags_one_a flags_one_b",
            "--b-args",
            "flags_two",
        ]
        + LS_CMD
        + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_hangs_0():
    """test for the 'hangs' interestingness test"""
    lith = lithium.Lithium()

    # test that `sleep 3` hangs over 1s
    result = lith.main(
        ["--strategy", "check-only", "--testcase", "temp.js", "hangs", "--timeout", "1"]
        + SLEEP_CMD
        + ["3"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_hangs_1():
    """test for the 'hangs' interestingness test"""
    lith = lithium.Lithium()

    # test that `ls temp.js` does not hang over 1s
    result = lith.main(
        ["--strategy", "check-only", "hangs", "--timeout", "1"] + LS_CMD + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_outputs_true():
    """interestingness 'outputs' positive test"""
    lith = lithium.Lithium()

    # test that `ls temp.js` contains "temp.js"
    result = lith.main(
        ["--strategy", "check-only", "outputs", "temp.js"] + LS_CMD + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_outputs_false():
    """interestingness 'outputs' negative test"""
    lith = lithium.Lithium()

    # test that `ls temp.js` does not contain "blah"
    result = lith.main(
        ["--strategy", "check-only", "outputs", "blah"] + LS_CMD + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_outputs_timeout():
    """interestingness 'outputs' --timeout test"""
    lith = lithium.Lithium()

    # check that --timeout works
    start_time = time.time()
    result = lith.main(
        [
            "--strategy",
            "check-only",
            "--testcase",
            "temp.js",
            "outputs",
            "--timeout",
            "1",
            "blah",
        ]
        + SLEEP_CMD
        + ["3"]
    )
    elapsed = time.time() - start_time
    assert result == 1
    assert elapsed >= 1
    assert lith.test_count == 1


def test_outputs_regex():
    """interestingness 'outputs' --regex test"""
    lith = lithium.Lithium()

    # test that regex matches work too
    result = lith.main(
        ["--strategy", "check-only", "outputs", "--regex", r"^.*js\s?$"]
        + LS_CMD
        + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_repeat_0():
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()
    with open("temp.js", "w") as tempf:
        tempf.write("hello")

    # Check for a known string
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "5", "outputs", "hello"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 0
    assert lith.test_count == 1


def test_repeat_1(caplog):
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()
    with open("temp.js", "w") as tempf:
        tempf.write("hello")

    # Look for a non-existent string, so the "repeat" test tries looping the maximum
    # number of iterations (5x)
    caplog.clear()
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "5", "outputs", "notfound"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1

    # scan the log output to see how many tests were performed
    found_count = 0
    last_count = 0
    for rec in caplog.records:
        message = rec.getMessage()
        if "Repeat number " in message:
            found_count += 1
            last_count = rec.args[0]
    assert found_count == 5  # Should have run 5x
    assert found_count == last_count  # We should have identical count outputs


def test_repeat_2():
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()

    # Check that replacements on the CLI work properly
    # Lower boundary - check that 0 (just outside [1]) is not found
    with open("temp.js", "w") as tempf1a:
        tempf1a.write("num0")
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "1", "outputs", "--timeout=9", "numREPEATNUM"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_repeat_3():
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()

    # Upper boundary - check that 2 (just outside [1]) is not found
    with open("temp.js", "w") as tempf1b:
        tempf1b.write("num2")
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "1", "outputs", "--timeout=9", "numREPEATNUM"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_repeat_4():
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()

    # Lower boundary - check that 0 (just outside [1,2]) is not found
    with open("temp.js", "w") as tempf2a:
        tempf2a.write("num0")
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "2", "outputs", "--timeout=9", "numREPEATNUM"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


def test_repeat_5():
    """test for the 'repeat' interestingness test"""
    lith = lithium.Lithium()

    # Upper boundary - check that 3 (just outside [1,2]) is not found
    with open("temp.js", "w") as tempf2b:
        tempf2b.write("num3")
    result = lith.main(
        ["--strategy", "check-only"]
        + ["repeat", "2", "outputs", "--timeout=9", "numREPEATNUM"]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 1
    assert lith.test_count == 1


@pytest.mark.parametrize(
    "pattern, expected",
    [
        ("B\nline C", "line B\nline C"),
        ("line B\nline C\n", "line B\nline C\n"),
        ("line A\nline", "line A\nline B"),
        ("\nline E\n", "\nline E\n"),
        ("line A", "line A"),
        ("line E", "line E"),
        ("line B", "line B"),
    ],
)
def test_interestingness_outputs_multiline(capsys, pattern, expected):
    """Tests for the 'outputs' interestingness test with multiline pattern"""
    lith = lithium.Lithium()

    with open("temp.js", "wb") as tmp_f:
        tmp_f.write(b"line A\nline B\nline C\nline D\nline E\n")

    capsys.readouterr()  # clear captured output buffers
    result = lith.main(
        [
            #       "--strategy", "check-only",
            "outputs",
            pattern,
        ]
        + CAT_CMD
        + ["temp.js"]
    )
    assert result == 0, "%r not found in %r" % (pattern, open("temp.js").read())
    #    assert lith.test_count == 1
    captured = capsys.readouterr()
    assert "[Found string in: %r]" % (expected,) in captured.out
