import os
import sys
from itertools import chain, combinations
from textwrap import dedent
from typing import List, Sequence

import pytest
from pytest_mock import MockerFixture

from tox import __version__
from tox.pytest import MonkeyPatch, ToxProjectCreator, check_os_environ
from tox.report import HandledError


def test_init_base(tox_project: ToxProjectCreator) -> None:
    project = tox_project(
        {
            "tox.ini": "[tox]",
            "src": {"__init__.py": "pass", "a": "out", "b": {"c": "out"}, "e": {"f": ""}},
        },
    )
    assert str(project.path) in repr(project)
    assert project.path.exists()
    assert project.structure == {
        "tox.ini": "[tox]",
        "src": {"__init__.py": "pass", "a": "out", "e": {"f": ""}, "b": {"c": "out"}},
    }


COMB = list(chain.from_iterable(combinations(["DIFF", "MISS", "EXTRA"], i) for i in range(4)))


@pytest.mark.parametrize("ops", COMB, ids=["-".join(i) for i in COMB])
def test_env_var(monkeypatch: MonkeyPatch, ops: List[str]) -> None:
    with monkeypatch.context() as m:
        if "DIFF" in ops:
            m.setenv("DIFF", "B")
        if "MISS" in ops:
            m.setenv("MISS", "1")
        m.setenv("NO_CHANGE", "yes")
        m.setenv("PYTHONPATH", "yes")  # values to clean before run

        with check_os_environ():
            assert "PYTHONPATH" not in os.environ
            if "EXTRA" in ops:
                m.setenv("EXTRA", "A")
            if "DIFF" in ops:
                m.setenv("DIFF", "D")
            if "MISS" in ops:
                m.delenv("MISS")

            from tox.pytest import pytest as tox_pytest  # type: ignore[attr-defined]

            exp = "test changed environ"
            if "EXTRA" in ops:
                exp += " extra {'EXTRA': 'A'}"
            if "MISS" in ops:
                exp += " miss {'MISS': '1'}"
            if "DIFF" in ops:
                exp += " diff {'DIFF = B vs D'}"

            def fail(msg: str) -> None:
                assert msg == exp

            m.setattr(tox_pytest, "fail", fail)
        assert "PYTHONPATH" in os.environ


def test_tox_run_does_not_return_exit_code(tox_project: ToxProjectCreator, mocker: MockerFixture) -> None:
    project = tox_project({"tox.ini": ""})
    mocker.patch("tox.run.main", return_value=None)
    with pytest.raises(RuntimeError, match="exit code not set"):
        project.run("c")


def test_tox_run_fails_before_state_setup(tox_project: ToxProjectCreator, mocker: MockerFixture) -> None:
    project = tox_project({"tox.ini": ""})
    mocker.patch("tox.run.main", side_effect=HandledError("something went bad"))
    outcome = project.run("c")
    with pytest.raises(RuntimeError, match="no state"):
        assert outcome.state


def test_tox_run_outcome_repr(tox_project: ToxProjectCreator) -> None:
    project = tox_project({"tox.ini": ""})
    outcome = project.run("c")
    exp = dedent(
        f"""
    code: 0
    cmd: {sys.executable} -m tox c
    cwd: {project.path}
    standard output
    [tox]
    tox_root = {project.path}
    work_dir = {project.path / '.tox4'}
    temp_dir = {project.path / '.temp'}
    env_list =
    min_version = {__version__}
    provision_tox_env = .tox
    requires = tox>={__version__}
    no_package = False
    """
    ).lstrip()
    assert repr(outcome) == exp
    assert outcome.shell_cmd == f"{sys.executable} -m tox c"


def test_tox_run_assert_out_err_no_dedent(tox_project: ToxProjectCreator, mocker: MockerFixture) -> None:
    project = tox_project({"tox.ini": ""})

    def _main(args: Sequence[str]) -> int:  # noqa
        print(" goes on out", file=sys.stdout)
        print(" goes on err", file=sys.stderr)
        return 0

    mocker.patch("tox.run.main", side_effect=_main)
    outcome = project.run("c")
    outcome.assert_out_err(" goes on out\n", " goes on err\n", dedent=False)
