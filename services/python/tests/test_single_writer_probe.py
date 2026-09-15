"""P0-7 单写方探针自测（docs/10 §3.1 · docs/19 P0-7）。

- 样例违规（直接构造 / 变量追踪）必须抓到；
- 合规样例（写 Python-owned、读 Java-owned）必须放行；
- seed 豁免（docs/11 Q-A15 ①：初始化器单写豁免）；
- 全量 app 扫描 = 安全网：现有代码必须零违规（有违规即视为双写失守，接入 CI 前必过）。
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_PROBE = _REPO / "scripts" / "check_single_writer.py"


_NAME = "_vocalverse_sw_probe"


def _load():
    """importlib 加载脚本；模块名必须注册进 sys.modules —— Python 3.13 dataclasses
    `_is_type` 依赖 `sys.modules[cls.__module__]`（未注册 → NoneType 错误，2026-09-07 实测）。"""
    import sys

    if _NAME in sys.modules:
        return sys.modules[_NAME]
    spec = importlib.util.spec_from_file_location(_NAME, _PROBE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


probe = _load()


def _tmp_py(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "sample.py"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_direct_constructor_violation(tmp_path) -> None:
    p = _tmp_py(
        tmp_path,
        """
        from app.models import Scenario
        from app.db import get_session_factory

        def f():
            db = get_session_factory()()
            db.add(Scenario(title="x"))
        """,
    )
    vio = probe.find_violations(p)
    assert len(vio) == 1
    assert vio[0].model == "Scenario"
    assert "越权写" in vio[0].message


def test_variable_tracking_violation(tmp_path) -> None:
    p = _tmp_py(
        tmp_path,
        """
        from app.models.content import Song
        from app.db import get_session_factory

        def f():
            db = get_session_factory()()
            s = Song(title="x", bpm=100)
            db.add(s)
        """,
    )
    vio = probe.find_violations(p)
    assert len(vio) == 1
    assert vio[0].model == "Song"


def test_add_all_violation(tmp_path) -> None:
    p = _tmp_py(
        tmp_path,
        """
        from app.models import Ticket
        from app.db import get_session_factory

        def f():
            db = get_session_factory()()
            db.add_all([Ticket(title="t")])
        """,
    )
    vio = probe.find_violations(p)
    assert len(vio) == 1
    assert vio[0].model == "Ticket"


def test_python_owned_write_allowed(tmp_path) -> None:
    p = _tmp_py(
        tmp_path,
        """
        from app.models import Attempt, Placement
        from app.db import get_session_factory

        def f():
            db = get_session_factory()()
            db.add(Attempt(kind="dialog_speech"))
            db.add_all([Placement(overall_score=1)])
        """,
    )
    assert probe.find_violations(p) == []


def test_reading_java_owned_allowed(tmp_path) -> None:
    """读 Java-owned（db.get/select）不违规；实例来自 get 而非构造，不触发实例集。"""
    p = _tmp_py(
        tmp_path,
        """
        from app.models import Placement, User
        from app.db import get_session_factory

        def f():
            db = get_session_factory()()
            u = db.get(User, 1)
            db.add(Placement(user_id=u.id))
        """,
    )
    assert probe.find_violations(p) == []


def test_seed_exempted_by_scan(tmp_path) -> None:
    """seed 单写豁免（docs/11 Q-A15①）：scan 不检查 app/db/seed*.py。"""
    seed = tmp_path / "app" / "db"
    seed.mkdir(parents=True)
    (seed / "seed.py").write_text(
        "from app.models import Scenario\nfrom app.db import get_session_factory\n"
        "def f():\n    db = get_session_factory()()\n    db.add(Scenario(title='seed'))\n",
        encoding="utf-8",
    )
    ok = seed.parent / "ok.py"
    ok.write_text(
        "from app.models import Attempt\nfrom app.db import get_session_factory\n"
        "def f():\n    db = get_session_factory()()\n    db.add(Attempt())\n",
        encoding="utf-8",
    )
    assert probe.scan(tmp_path / "app") == []


def test_existing_app_code_clean() -> None:
    """安全网：当前全部 app 代码必须零违规（探针接入 CI 的前提）。"""
    vio = probe.scan(_REPO / "services" / "python" / "app")
    assert vio == [], f"现有代码存在 {len(vio)} 处疑似双写：{vio}"
