"""
ga_cli/cli.py - GenericAgent 命令行分发系统

通过 python -m ga_cli <命令> 或 ga <命令> 调用
"""
import os, sys, subprocess, argparse, textwrap


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
        statuses.append(_doctor_item("PASS", "policy mode", policy_mode))
    else:
        statuses.append(_doctor_item("WARN", "policy mode", f"invalid {policy_mode!r}; will fall back to observe"))

    try:
        from llmcore import reload_mykeys
        mykeys, _changed = reload_mykeys()
        llm_like = [k for k, v in mykeys.items() if isinstance(v, dict) and ("model" in v or "apikey" in v or "api_key" in v)]
        statuses.append(_doctor_item("PASS", "model profiles", f"{len(llm_like)} profile(s) loaded; values hidden"))
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
