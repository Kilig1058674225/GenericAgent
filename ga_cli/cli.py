"""
ga_cli/cli.py - GenericAgent 命令行分发系统

通过 python -m ga_cli <命令> 或 ga <命令> 调用
"""
import os, sys, subprocess, argparse, textwrap, json
from pathlib import Path


def _configure_output_encoding():
    """Prefer UTF-8 for Chinese/English mixed CLI output on Windows terminals."""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if sys.platform != "win32":
        return
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


_configure_output_encoding()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)


def _frontends():
    return os.path.join(PROJECT_DIR, "frontends")

def _reflect():
    return os.path.join(PROJECT_DIR, "reflect")


def launch_frontend(cmd_parts, args=None):
    """启动前端/工具进程"""
    full_cmd = []
    for part in cmd_parts:
        part = part.replace("{PROJECT_DIR}", PROJECT_DIR)
        part = part.replace("{FRONTENDS}", _frontends())
        part = part.replace("{REFLECT}", _reflect())
        full_cmd.append(part)

    # 插入额外参数
    if args:
        full_cmd.extend(args)

    print(f"🚀 {' '.join(full_cmd)}")
    sys.stdout.flush()
    os.chdir(PROJECT_DIR)
    proc = subprocess.Popen(full_cmd)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        sys.exit(0)


COMMANDS = {
    "gui": {
        "help": "启动桌面GUI (qtapp)",
        "desc": "启动基于 PyQt5 的完整桌面聊天界面（气泡代码高亮、文件拖拽、历史搜索）",
        "cmd": ["python", "{FRONTENDS}/qtapp.py"],
    },
    "configure": {
        "help": "运行初始配置向导 (configure_mykey.py)",
        "desc": "首次安装后配置 API Key、模型参数等基础设置",
        "cmd": ["python", "{PROJECT_DIR}/assets/configure_mykey.py"],
    },
    "hub": {
        "help": "启动 Hub 管理器 (launcher)",
        "desc": "启动 hub 前端管理面板（系统托盘 + 浏览器界面）",
        "cmd": ["python", "{PROJECT_DIR}/hub.pyw"],
    },
    "tui": {
        "help": "启动终端 TUI (tuiapp)",
        "desc": "启动终端图形界面（Textual），适合纯终端环境或 SSH",
        "cmd": ["python", "{FRONTENDS}/tuiapp.py"],
    },
    "tui2": {
        "help": "启动终端 TUI v2 (tuiapp_v2)",
        "desc": "启动增强版终端图形界面（Textual v2），更多功能更好的体验",
        "cmd": ["python", "{FRONTENDS}/tuiapp_v2.py"],
    },
    "cli": {
        "help": "启动 CLI 对话 (agentmain)",
        "desc": "启动命令行交互对话模式，最轻量的使用方式",
        "cmd": ["python", "{PROJECT_DIR}/agentmain.py"],
    },
    "launch": {
        "help": "启动 webview 桌面壳 (launch.pyw)",
        "desc": "以原生窗口形式包装 stapp Web 界面（基于 pywebview）",
        "cmd": ["python", "{PROJECT_DIR}/launch.pyw"],
    },
    "status": {
        "help": "检查运行状态",
        "desc": "检查当前是否已有 GenericAgent 进程在运行",
        "cmd": None,
        "internal": True,
    },
    "update": {
        "help": "更新项目 (git pull + pip install)",
        "desc": "从 Git 拉取最新代码并更新依赖",
        "cmd": None,
        "internal": True,
    },
    "list": {
        "help": "列出所有可用前端/服务",
        "desc": "显示所有注册的命令",
        "cmd": None,
        "internal": True,
    },
    "doctor": {
        "help": "运行本地环境自诊断",
        "desc": "检查 Python、依赖、模型配置、Git 远端、忽略规则和 Streamlit 端口",
        "cmd": None,
        "internal": True,
    },
    "audit": {
        "help": "查看最近审计事件",
        "desc": "读取 temp/runs 下的 JSONL 审计日志，可按事件名过滤",
        "cmd": None,
        "internal": True,
    },
    "policy": {
        "help": "干跑安全策略判断",
        "desc": "检查某个工具调用会被允许、确认还是阻断，不执行工具",
        "cmd": None,
        "internal": True,
    },
    "skills": {
        "help": "管理本地技能注册表",
        "desc": "发现、列出、启用、禁用和验证 memory/skill_registry.json",
        "cmd": None,
        "internal": True,
    },
    "snapshots": {
        "help": "查看/恢复文件快照",
        "desc": "管理 file_write/file_patch 写入前自动创建的本地快照",
        "cmd": None,
        "internal": True,
    },
    "verify": {
        "help": "运行提交前验证套件",
        "desc": "运行单测、doctor、导入 smoke、diff 检查和已配置密钥扫描",
        "cmd": None,
        "internal": True,
    },
}


def cmd_list():
    """展示所有可用命令"""
    print()
    frontend_cmds = [(k, v) for k, v in sorted(COMMANDS.items()) if v["cmd"] is not None]
    internal_cmds = [(k, v) for k, v in sorted(COMMANDS.items()) if v["cmd"] is None]

    print(f"  {'命令':20s}  {'说明'}")
    print(f"  {'━'*20}  {'━'*40}")
    for name, info in frontend_cmds:
        print(f"  {name:20s}  {info.get('help', info['desc'][:40])}")
    print()
    for name, info in internal_cmds:
        print(f"  {name:20s}  {info.get('help', info['desc'][:40])}")
    print()


def cmd_status():
    """检查进程状态"""
    import psutil
    running = [p for p in psutil.process_iter(['pid', 'name', 'cmdline'])
               if p.info['cmdline'] and any('agentmain' in c for c in p.info['cmdline'])]
    if running:
        print(f"🟢 运行中: {len(running)} 个进程")
        for p in running:
            print(f"   PID {p.info['pid']} — {' '.join(p.info['cmdline'][:3])}")
    else:
        print("⚫ GenericAgent 进程未运行")


def cmd_update():
    """git pull + pip install"""
    os.chdir(PROJECT_DIR)
    print("🔄 git pull...")
    r = subprocess.run(["git", "pull"], capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr)
    print("📦 pip install...")
    r2 = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."],
                        capture_output=True, text=True)
    print(r2.stdout[-500:] if r2.stdout else "")
    if r2.returncode != 0:
        print(r2.stderr[-500:])


def _doctor_item(status, name, detail):
    print(f"[{status:4s}] {name:26s} {detail}")
    return status


def _run_git(args):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()
    except Exception as exc:
        return 1, "", str(exc)


def _port_is_open(host, port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _probe_http_title(host, port):
    from html.parser import HTMLParser
    from urllib.request import urlopen

    class TitleParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self._in_title = False
            self.title = ""

        def handle_starttag(self, tag, attrs):
            if tag.lower() == "title":
                self._in_title = True

        def handle_endtag(self, tag):
            if tag.lower() == "title":
                self._in_title = False

        def handle_data(self, data):
            if self._in_title:
                self.title += data

    try:
        with urlopen(f"http://{host}:{port}", timeout=2) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
    except Exception:
        return ""
    parser = TitleParser()
    parser.feed(body)
    return parser.title.strip()


def cmd_doctor():
    """Run a local health check without printing secrets."""
    import importlib
    import json

    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)

    print("\nGenericAgent doctor\n")
    statuses = []

    version = sys.version_info
    version_text = f"{version.major}.{version.minor}.{version.micro} ({sys.executable})"
    if (3, 10) <= version[:2] < (3, 14):
        status = "PASS" if version[:2] in ((3, 11), (3, 12)) else "WARN"
        detail = version_text if status == "PASS" else f"{version_text}; recommended 3.11 or 3.12"
    else:
        status, detail = "FAIL", f"{version_text}; requires >=3.10,<3.14"
    statuses.append(_doctor_item(status, "Python", detail))

    for module_name in ("agent_loop", "agentmain", "llmcore", "requests", "bs4", "bottle", "aiohttp"):
        try:
            importlib.import_module(module_name)
            statuses.append(_doctor_item("PASS", f"import {module_name}", "ok"))
        except Exception as exc:
            statuses.append(_doctor_item("FAIL", f"import {module_name}", str(exc)))

    try:
        importlib.import_module("streamlit")
        statuses.append(_doctor_item("PASS", "import streamlit", "ok"))
    except Exception as exc:
        statuses.append(_doctor_item("WARN", "import streamlit", f"UI extra missing or broken: {exc}"))

    try:
        from skill_registry import discover_skills, sync_registry, validate_registry
        probe = Path(PROJECT_DIR) / "temp" / "runs" / ".doctor_skill_registry.json"
        data = sync_registry(path=probe)
        validation = validate_registry(path=probe)
        try:
            probe.unlink()
        except OSError:
            pass
        status = "PASS" if validation.get("ok") else "WARN"
        detail = f"{len(discover_skills())} discovered, probe {len(data.get('skills', []))} indexed"
        if validation.get("errors"):
            detail += f"; {len(validation['errors'])} validation error(s)"
        statuses.append(_doctor_item(status, "skill registry", detail))
    except Exception as exc:
        statuses.append(_doctor_item("WARN", "skill registry", f"check failed: {exc}"))

    mykey_py = os.path.join(PROJECT_DIR, "mykey.py")
    mykey_json = os.path.join(PROJECT_DIR, "mykey.json")
    env_ready = bool(os.environ.get("GENERICAGENT_API_KEY")) and bool(os.environ.get("GENERICAGENT_MODEL"))
    config_sources = []
    if os.path.exists(mykey_py):
        config_sources.append("mykey.py")
    if os.path.exists(mykey_json):
        config_sources.append("mykey.json")
    if env_ready:
        config_sources.append("env")
    if config_sources:
        statuses.append(_doctor_item("PASS", "model config", "found " + ", ".join(config_sources) + " (secrets hidden)"))
    else:
        statuses.append(_doctor_item("WARN", "model config", "no mykey.py/mykey.json or GENERICAGENT_API_KEY+GENERICAGENT_MODEL env"))

    policy_mode = os.environ.get("GA_POLICY_MODE", "observe").strip().lower()
    if policy_mode in {"off", "observe", "enforce"}:
        detail = policy_mode
        if policy_mode == "observe":
            detail += " (critical blocks still enforced)"
        statuses.append(_doctor_item("PASS", "policy mode", detail))
    else:
        statuses.append(_doctor_item("WARN", "policy mode", f"invalid {policy_mode!r}; will fall back to observe"))

    try:
        from llmcore import reload_mykeys
        from model_profiles import format_model_profile_summary, summarize_model_profiles
        mykeys, _changed = reload_mykeys()
        profiles = summarize_model_profiles(mykeys)
        detail = f"{len(profiles)} profile(s) loaded; secrets hidden"
        statuses.append(_doctor_item("PASS", "model profiles", detail))
        for idx, profile in enumerate(profiles[:5], start=1):
            statuses.append(_doctor_item("PASS", f"profile {idx}", format_model_profile_summary(profile)))
        if len(profiles) > 5:
            statuses.append(_doctor_item("PASS", "profile more", f"{len(profiles) - 5} additional profile(s) hidden"))
    except Exception as exc:
        statuses.append(_doctor_item("WARN", "model profiles", f"could not load config: {exc}"))

    for remote, expected in (
        ("origin", "github.com/Kilig1058674225/GenericAgent"),
        ("upstream", "github.com/lsdefine/GenericAgent"),
    ):
        code, out, err = _run_git(["remote", "get-url", remote])
        if code != 0:
            statuses.append(_doctor_item("WARN", f"git remote {remote}", err or "missing"))
        else:
            compact = out.replace("https://", "").replace("git@", "").replace(":", "/")
            status = "PASS" if expected in compact else "WARN"
            statuses.append(_doctor_item(status, f"git remote {remote}", out))

    for path in ("mykey.py", ".venv/", "temp/"):
        code, _out, _err = _run_git(["check-ignore", "-q", path])
        statuses.append(_doctor_item("PASS" if code == 0 else "FAIL", f"gitignore {path}", "ignored" if code == 0 else "not ignored"))

    port = int(os.environ.get("GA_STREAMLIT_PORT", "18510"))
    if _port_is_open("127.0.0.1", port):
        title = _probe_http_title("127.0.0.1", port)
        if title:
            statuses.append(_doctor_item("PASS", "Streamlit port", f"127.0.0.1:{port} is in use by HTTP app ({title})"))
        else:
            statuses.append(_doctor_item("WARN", "Streamlit port", f"127.0.0.1:{port} is already in use by a non-HTTP app"))
    else:
        statuses.append(_doctor_item("PASS", "Streamlit port", f"127.0.0.1:{port} is available"))

    audit_dir = os.path.join(PROJECT_DIR, "temp", "runs")
    try:
        os.makedirs(audit_dir, exist_ok=True)
        probe = os.path.join(audit_dir, ".doctor_probe")
        with open(probe, "w", encoding="utf-8") as f:
            json.dump({"ok": True}, f)
        os.remove(probe)
        statuses.append(_doctor_item("PASS", "audit log dir", audit_dir))
    except Exception as exc:
        statuses.append(_doctor_item("FAIL", "audit log dir", str(exc)))

    print()
    if "FAIL" in statuses:
        print("Doctor result: FAIL - fix the failed checks above.")
        sys.exit(1)
    if "WARN" in statuses:
        print("Doctor result: WARN - usable, with action items above.")
        return
    print("Doctor result: PASS - local environment looks healthy.")


def cmd_audit(argv=None):
    import json

    parser = argparse.ArgumentParser(
        prog="ga audit",
        description="查看本地 JSONL 审计日志",
    )
    parser.add_argument("-n", "--limit", type=int, default=20, help="显示最近 N 条事件")
    parser.add_argument("--event", help="只显示指定事件名，例如 policy_decision")
    parser.add_argument("--json", action="store_true", help="输出 JSON 数组")
    parsed = parser.parse_args(argv or [])

    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
    from audit_view import summarize_audit_event
    from safety_policy import iter_audit_events

    events = iter_audit_events(limit=parsed.limit, event=parsed.event)
    if parsed.json:
        print(json.dumps(events, ensure_ascii=True, indent=2))
        return
    if not events:
        print("No audit events found.")
        return

    print()
    print(f"  {'时间':25s}  {'事件':20s}  {'摘要'}")
    print(f"  {'━'*25}  {'━'*20}  {'━'*45}")
    for item in events:
        ts = str(item.get("timestamp", ""))[:25]
        event_name = str(item.get("event", ""))[:20]
        summary = summarize_audit_event(item)
        print(f"  {ts:25s}  {event_name:20s}  {summary}")
    print()


def _parse_json_object(raw, label="args"):
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} must be a JSON object: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{label} must be a JSON object")
    return data


def cmd_policy(argv=None):
    from types import SimpleNamespace

    parser = argparse.ArgumentParser(
        prog="ga policy",
        description="干跑本地安全策略，不执行工具",
    )
    sub = parser.add_subparsers(dest="action")

    p_check = sub.add_parser("check", help="检查工具调用的策略结果")
    p_check.add_argument("tool_name", help="工具名，例如 code_run、file_read、web_execute_js")
    p_check.add_argument("args_json", nargs="?", default="{}", help="工具参数 JSON 对象")
    p_check.add_argument("--mode", choices=("off", "observe", "enforce"), help="临时策略模式")
    p_check.add_argument("--cwd", help="用于相对路径判断的工作目录")
    p_check.add_argument("--json", action="store_true", help="输出 JSON")

    parsed = parser.parse_args(argv or [])
    if not parsed.action:
        parser.print_help()
        return

    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
    from safety_policy import classify_tool_call, redact_data

    args = _parse_json_object(parsed.args_json)
    old_mode = os.environ.get("GA_POLICY_MODE")
    if parsed.mode:
        os.environ["GA_POLICY_MODE"] = parsed.mode
    try:
        handler = SimpleNamespace(cwd=parsed.cwd) if parsed.cwd else None
        decision = classify_tool_call(parsed.tool_name, args, handler=handler)
    finally:
        if parsed.mode:
            if old_mode is None:
                os.environ.pop("GA_POLICY_MODE", None)
            else:
                os.environ["GA_POLICY_MODE"] = old_mode

    result = {
        "tool_name": parsed.tool_name,
        "args": redact_data(args),
        "policy": decision.public_dict(),
        "blocks_execution": decision.blocks_execution,
        "needs_confirmation": decision.needs_confirmation,
    }
    if parsed.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return

    print("\nPolicy check\n")
    print(f"tool:              {parsed.tool_name}")
    print(f"decision:          {decision.decision}")
    print(f"risk:              {decision.risk}")
    print(f"category:          {decision.category}")
    print(f"mode:              {decision.mode}")
    print(f"blocks_execution:  {'yes' if decision.blocks_execution else 'no'}")
    print(f"needs_confirmation:{' yes' if decision.needs_confirmation else ' no'}")
    print(f"reason:            {decision.reason}")
    print(f"args:              {json.dumps(result['args'], ensure_ascii=False, default=str)}")


def cmd_skills(argv=None):
    import json

    parser = argparse.ArgumentParser(
        prog="ga skills",
        description="管理本地技能注册表",
    )
    sub = parser.add_subparsers(dest="action")

    p_list = sub.add_parser("list", help="列出技能")
    p_list.add_argument("--all", action="store_true", help="包含已禁用技能")
    p_list.add_argument("--json", action="store_true", help="输出 JSON")

    sub.add_parser("sync", help="发现 memory/ 下的技能并更新注册表")
    sub.add_parser("validate", help="验证注册表中的技能源文件")

    p_enable = sub.add_parser("enable", help="启用技能")
    p_enable.add_argument("skill_id")

    p_disable = sub.add_parser("disable", help="禁用技能")
    p_disable.add_argument("skill_id")

    parsed = parser.parse_args(argv or ["list"])
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
    from skill_registry import list_skills, set_skill_enabled, sync_registry, validate_registry

    action = parsed.action or "list"
    if action == "sync":
        data = sync_registry()
        print(f"Synced {len(data.get('skills', []))} skill(s).")
        return
    if action == "validate":
        result = validate_registry()
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if not result.get("ok"):
            sys.exit(1)
        return
    if action in {"enable", "disable"}:
        item = set_skill_enabled(parsed.skill_id, action == "enable")
        state = "enabled" if item.get("enabled", True) else "disabled"
        print(f"{item['id']} {state}.")
        return

    skills = list_skills(include_disabled=parsed.all)
    if parsed.json:
        print(json.dumps(skills, ensure_ascii=True, indent=2))
        return
    if not skills:
        print("No skills in registry. Run `ga skills sync` first.")
        return
    print()
    print(f"  {'状态':6s}  {'ID':34s}  {'类型':8s}  {'标题'}")
    print(f"  {'━'*6}  {'━'*34}  {'━'*8}  {'━'*40}")
    for item in skills:
        state = "on" if item.get("enabled", True) else "off"
        print(f"  {state:6s}  {str(item.get('id', ''))[:34]:34s}  {str(item.get('kind', ''))[:8]:8s}  {item.get('title', '')}")
    print()


def cmd_snapshots(argv=None):
    import json

    parser = argparse.ArgumentParser(
        prog="ga snapshots",
        description="查看/恢复 file_write/file_patch 自动快照",
    )
    sub = parser.add_subparsers(dest="action")

    p_list = sub.add_parser("list", help="列出最近快照")
    p_list.add_argument("-n", "--limit", type=int, default=20, help="显示最近 N 条")
    p_list.add_argument("--target", help="只显示某个目标文件的快照")
    p_list.add_argument("--json", action="store_true", help="输出 JSON")

    p_restore = sub.add_parser("restore", help="按快照 id 恢复文件")
    p_restore.add_argument("snapshot_id")
    p_restore.add_argument("--no-pre-snapshot", action="store_true", help="恢复前不再给当前文件创建保护快照")
    p_restore.add_argument("--json", action="store_true", help="输出 JSON")

    parsed = parser.parse_args(argv or ["list"])
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
    from workspace_guard import list_snapshots, restore_snapshot

    action = parsed.action or "list"
    if action == "restore":
        result = restore_snapshot(parsed.snapshot_id, create_pre_restore_snapshot=not parsed.no_pre_snapshot)
        if parsed.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print(f"{result.get('status')}: {result.get('action') or result.get('msg')} {result.get('target_path', '')}")
        if result.get("status") != "success":
            sys.exit(1)
        return

    snapshots = list_snapshots(limit=parsed.limit, target_path=parsed.target)
    if parsed.json:
        print(json.dumps(snapshots, ensure_ascii=True, indent=2))
        return
    if not snapshots:
        print("No snapshots found.")
        return
    print()
    print(f"  {'时间':25s}  {'ID':32s}  {'存在':4s}  {'目标'}")
    print(f"  {'━'*25}  {'━'*32}  {'━'*4}  {'━'*50}")
    for item in snapshots:
        ts = str(item.get("timestamp", ""))[:25]
        sid = str(item.get("id", ""))[:32]
        existed = "yes" if item.get("existed") else "no"
        target = item.get("target_rel") or item.get("target_path", "")
        print(f"  {ts:25s}  {sid:32s}  {existed:4s}  {target}")
    print()


def _verify_tail(text, limit=1200):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _run_verify_step(name, cmd, timeout=120):
    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return {
            "name": name,
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
        }
    except Exception as exc:
        return {"name": name, "ok": False, "returncode": 1, "stdout": "", "stderr": str(exc)}


def cmd_verify(argv=None):
    import json

    parser = argparse.ArgumentParser(
        prog="ga verify",
        description="运行提交前验证套件",
    )
    parser.add_argument("--quick", action="store_true", help="跳过完整单元测试")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    parsed = parser.parse_args(argv or [])

    python = sys.executable
    steps = [
        (
            "py_compile",
            [
                python,
                "-m",
                "py_compile",
                "agent_loop.py",
                "llmcore.py",
                "ga_cli/cli.py",
                "safety_policy.py",
                "audit_view.py",
                "model_profiles.py",
                "verify_checks.py",
                "workspace_guard.py",
                "skill_registry.py",
            ],
            60,
        ),
    ]
    if not parsed.quick:
        steps.append(("unittest", [python, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], 180))
    steps.extend(
        [
            ("doctor", [python, "-m", "ga_cli", "doctor"], 120),
            ("import smoke", [python, "-c", "import agent_loop; import agentmain; print('imports ok')"], 60),
            (
                "agent init smoke",
                [
                    python,
                    "-c",
                    "from agentmain import GeneraticAgent; a=GeneraticAgent(); assert a.list_llms(); print('llm profiles ok')",
                ],
                120,
            ),
            ("skills validate", [python, "-m", "ga_cli", "skills", "validate"], 60),
            ("git diff check", ["git", "diff", "--check"], 60),
        ]
    )

    results = [_run_verify_step(name, cmd, timeout) for name, cmd, timeout in steps]
    try:
        from verify_checks import scan_candidate_files_for_configured_secrets

        secret_matches = scan_candidate_files_for_configured_secrets(PROJECT_DIR)
        results.append(
            {
                "name": "configured secret scan",
                "ok": not secret_matches,
                "returncode": 0 if not secret_matches else 1,
                "stdout": "" if secret_matches else "no configured secrets found in git candidate files",
                "stderr": json.dumps(secret_matches, ensure_ascii=True),
            }
        )
    except Exception as exc:
        results.append({"name": "configured secret scan", "ok": False, "returncode": 1, "stdout": "", "stderr": str(exc)})

    if parsed.json:
        print(json.dumps(results, ensure_ascii=True, indent=2))
    else:
        print("\nGenericAgent verify\n")
        for result in results:
            status = "PASS" if result["ok"] else "FAIL"
            print(f"[{status:4s}] {result['name']}")
            if not result["ok"]:
                detail = _verify_tail((result.get("stdout") or "") + "\n" + (result.get("stderr") or ""))
                if detail:
                    print(textwrap.indent(detail, "       "))
        print()
        if all(result["ok"] for result in results):
            print("Verify result: PASS - ready for commit/push.")
        else:
            print("Verify result: FAIL - fix failed checks above.")
    if not all(result["ok"] for result in results):
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="ga",
        description="GenericAgent 全局命令入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              ga gui               启动桌面 GUI
              ga web               启动 Web 增强版
              ga web --native      启动 Web 基础版(桌面壳)
              ga tui               启动终端 TUI (v1)
              ga tui2              启动终端 TUI (v2 增强版)
              ga pet               启动桌面宠物 v2
              ga launch            启动 webview 桌面壳
              ga list              列出所有命令
              ga doctor            运行环境自诊断
              ga verify            运行提交前验证套件
              ga policy check code_run '{"type":"python","code":"print(1)"}'
              ga audit             查看最近审计事件
              ga skills sync       更新技能注册表
              ga snapshots list    查看最近文件快照
        """),
    )
    parser.add_argument("command", nargs="?", help="命令名")
    parser.add_argument("args", nargs="*", help="子命令参数")
    parser.add_argument("-v", "--version", action="store_true", help="显示版本")

    args, unknown = parser.parse_known_args()

    if args.version:
        print("GenericAgent v0.1.0")
        return

    cmd = args.command

    if not cmd or cmd == "help":
        parser.print_help()
        print("\n--- 命令列表 ---")
        cmd_list()
        return

    if cmd == "list":
        cmd_list()
        return

    if cmd == "status":
        cmd_status()
        return

    if cmd == "update":
        cmd_update()
        return

    if cmd == "doctor":
        cmd_doctor()
        return

    if cmd == "audit":
        cmd_audit(sys.argv[2:])
        return

    if cmd == "policy":
        cmd_policy(sys.argv[2:])
        return

    if cmd == "skills":
        cmd_skills(sys.argv[2:])
        return

    if cmd == "snapshots":
        cmd_snapshots(sys.argv[2:])
        return

    if cmd == "verify":
        cmd_verify(sys.argv[2:])
        return

    if cmd not in COMMANDS:
        print(f"❌ 未知命令: {cmd}")
        print(f"   使用 'ga list' 查看可用命令")
        sys.exit(1)

    info = COMMANDS[cmd]

    # 内置命令走内部逻辑
    if info.get("internal"):
        print(f"❌ 命令 {cmd} 没有配置启动命令")
        sys.exit(1)

    extra = list(args.args) + unknown

    # === 处理命令特有 flags ===
    cmd_parts = list(info["cmd"])

    # 处理 flags (如 --native)
    flags = info.get("flags", {})
    for flag_name, flag_info in flags.items():
        if flag_name in extra:
            cmd_parts = list(flag_info["cmd"])
            extra.remove(flag_name)
            break

    launch_frontend(cmd_parts, extra if extra else None)


if __name__ == "__main__":
    main()
