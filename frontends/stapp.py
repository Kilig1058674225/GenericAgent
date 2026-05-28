import os, sys, subprocess
from urllib.request import urlopen
from urllib.parse import quote
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")
try: sys.stdout.reconfigure(errors='replace')
except: pass
try: sys.stderr.reconfigure(errors='replace')
except: pass
script_dir = os.path.dirname(__file__)
sys.path.append(os.path.abspath(os.path.join(script_dir, '..')))
sys.path.append(os.path.abspath(script_dir))

import streamlit as st
import time, json, re, threading, queue
from audit_view import audit_event_detail, audit_event_names, audit_event_row, filter_audit_events
from agentmain import GeneraticAgent
import chatapp_common  # activate /continue command (monkey patches GeneraticAgent)
from continue_cmd import handle_frontend_command, reset_conversation, list_sessions, extract_ui_messages
from btw_cmd import handle_frontend_command as btw_handle_frontend
from export_cmd import last_assistant_text, export_to_temp, wrap_for_clipboard
from policy_confirmation import apply_confirmation_token

st.set_page_config(page_title="Cowork", layout="wide")

DEFAULT_LANG = os.environ.get('GA_LANG', 'zh')
if DEFAULT_LANG not in ('zh', 'en'): DEFAULT_LANG = 'zh'
st.session_state.setdefault('ui_lang', DEFAULT_LANG)
LANG = st.session_state.get('ui_lang', DEFAULT_LANG)
if LANG not in ('zh', 'en'): LANG = DEFAULT_LANG
I18N = {
    'zh': {
        'app_title': 'Cowork',
        'app_subtitle': '本地安全 Agent 工作台',
        'app_status': '在线',
        'language': '界面语言',
        'model_label': '模型',
        'model_core': '当前模型',
        'force_stop': '强行停止任务',
        'reinject_tools': '重新注入工具',
        'desktop_pet': '桌面宠物',
        'audit_timeline': '审计时间线',
        'audit_latest': '最近 {value} 条',
        'audit_filter': '筛选事件类型',
        'audit_filter_placeholder': '全部事件类型',
        'audit_show_details': '显示详情',
        'audit_no_matches': '没有匹配的审计事件',
        'audit_unavailable': '审计不可用: {error}',
        'audit_showing': '显示 {shown} / {total} 条匹配事件',
        'find_tasks': '给我找点事做',
        'start_autonomous': '开始空闲自主行动',
        'stop_autonomous': '禁止自主行动',
        'allow_autonomous': '允许自主行动',
        'autonomous_on': '自主行动运行中，会在你离开它 30 分钟后自动进行',
        'autonomous_off': '自主行动已停止',
        'autonomous_started': '已将上次回复时间设为 1800 秒前，自主行动已激活',
        'autonomous_disabled': '已禁止自主行动',
        'autonomous_enabled': '已允许自主行动',
        'find_tasks_prompt': '按照自主行动的规划部分，充分分析我的情况，给我生成一批TODO，务必让我感兴趣',
        'chat_placeholder': '输入任务或 / 命令',
        'stop_sent': '已发送停止信号',
        'tools_injected': '工具已重新注入',
        'tools_failed': '工具注入失败: {error}',
        'pet_started': '桌面宠物已启动',
        'policy_confirm_title': '需要确认后继续',
        'policy_confirm_allow': '允许一次并重试',
        'policy_confirm_cancel': '取消本次执行',
        'policy_confirm_retrying': '已允许一次，正在重试',
        'policy_confirm_cancelled': '已取消本次执行',
    },
    'en': {
        'app_title': 'Cowork',
        'app_subtitle': 'Local safe agent workbench',
        'app_status': 'Online',
        'language': 'Interface language',
        'model_label': 'Model',
        'model_core': 'Current model',
        'force_stop': 'Force Stop',
        'reinject_tools': 'Reinject Tools',
        'desktop_pet': 'Desktop Pet',
        'audit_timeline': 'Audit timeline',
        'audit_latest': 'Latest {value}',
        'audit_filter': 'Event filter',
        'audit_filter_placeholder': 'All event types',
        'audit_show_details': 'Show details',
        'audit_no_matches': 'No matching audit events.',
        'audit_unavailable': 'Audit unavailable: {error}',
        'audit_showing': 'Showing {shown} of {total} matched events.',
        'find_tasks': 'Find something for me',
        'start_autonomous': 'Start idle autonomy',
        'stop_autonomous': 'Pause autonomy',
        'allow_autonomous': 'Allow autonomy',
        'autonomous_on': 'Autonomy is active after 30 minutes away.',
        'autonomous_off': 'Autonomy is paused.',
        'autonomous_started': 'Idle autonomy is active.',
        'autonomous_disabled': 'Autonomy paused.',
        'autonomous_enabled': 'Autonomy enabled.',
        'find_tasks_prompt': 'Based on the autonomous planning section, analyze my situation and generate a list of interesting TODOs for me.',
        'chat_placeholder': 'Ask for a task or type / command',
        'stop_sent': 'Stop signal sent',
        'tools_injected': 'Tools injected',
        'tools_failed': 'Tool injection failed: {error}',
        'pet_started': 'Desktop pet started',
        'policy_confirm_title': 'Confirmation required',
        'policy_confirm_allow': 'Allow once and retry',
        'policy_confirm_cancel': 'Cancel this run',
        'policy_confirm_retrying': 'Allowed once, retrying',
        'policy_confirm_cancelled': 'Cancelled this run',
    },
}
def T(key, **kwargs):
    text = I18N.get(st.session_state.get('ui_lang', LANG), I18N['zh']).get(key, key)
    return text.format(**kwargs) if kwargs else text

st.markdown("""
<style>
  :root {
    --ga-bg: #f5f7f3;
    --ga-panel: #ffffff;
    --ga-ink: #17211b;
    --ga-muted: #66736b;
    --ga-line: #d9e0d8;
    --ga-accent: #0f766e;
    --ga-accent-2: #c2410c;
    --ga-sidebar: #151a17;
    --ga-sidebar-soft: #202822;
  }
  .stApp {
    background:
      linear-gradient(90deg, rgba(15, 118, 110, .035) 1px, transparent 1px),
      linear-gradient(180deg, rgba(15, 118, 110, .025) 1px, transparent 1px),
      var(--ga-bg);
    background-size: 32px 32px;
    color: var(--ga-ink);
  }
  [data-testid="stSidebar"] {
    background: var(--ga-sidebar);
    border-right: 1px solid rgba(255,255,255,.08);
  }
  [data-testid="stSidebar"] * { color: #edf4ec; }
  [data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] label p {
    color: #aeb9b1 !important;
  }
  [data-testid="stSidebar"] [data-baseweb="select"] > div,
  [data-testid="stSidebar"] [data-baseweb="input"] > div {
    background: var(--ga-sidebar-soft);
    border: 1px solid #344036;
    border-radius: 8px;
  }
  [data-testid="stSidebar"] button {
    border-radius: 8px !important;
    border: 1px solid #344036 !important;
    background: #202822 !important;
    color: #eef4ee !important;
  }
  [data-testid="stSidebar"] button:hover {
    border-color: #4f8f7f !important;
    color: #ffffff !important;
  }
  .ga-header {
    max-width: 980px;
    margin: 1.4rem auto 1.2rem;
    padding: 1rem 1.1rem;
    background: rgba(255,255,255,.82);
    border: 1px solid var(--ga-line);
    border-radius: 8px;
    box-shadow: 0 10px 32px rgba(23,33,27,.08);
  }
  .ga-header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }
  .ga-title {
    margin: 0;
    font-family: Georgia, Cambria, "Times New Roman", serif;
    font-size: clamp(2rem, 4vw, 3.5rem);
    line-height: .95;
    letter-spacing: 0;
    color: var(--ga-ink);
  }
  .ga-subtitle {
    margin-top: .35rem;
    color: var(--ga-muted);
    font-size: .98rem;
  }
  .ga-status {
    min-width: max-content;
    border: 1px solid #b8d9d4;
    background: #e7f4f1;
    color: #0f5f59;
    border-radius: 8px;
    padding: .38rem .65rem;
    font-size: .84rem;
    font-weight: 700;
  }
  [data-testid="stMainBlockContainer"] {
    padding-top: 1rem;
    max-width: 1120px;
  }
  [data-testid="stChatInput"] {
    max-width: 860px;
    margin: 0 auto;
  }
  [data-testid="stChatInput"] textarea {
    border-radius: 8px !important;
    border: 1px solid #ccd7cf !important;
    box-shadow: 0 10px 28px rgba(23,33,27,.09) !important;
  }
  [data-testid="stChatMessage"] {
    max-width: 920px;
    margin: .55rem auto;
    border-radius: 8px;
  }
  div[data-testid="stAlert"] {
    max-width: 920px;
    margin-left: auto;
    margin-right: auto;
    border-radius: 8px;
  }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init():
    agent = GeneraticAgent()
    if agent.llmclient is None:
        st.error("⚠️ Please set mykey.py!")
        st.stop()
    else: threading.Thread(target=agent.run, daemon=True).start()
    return agent

agent = init()

st.markdown(
    f"""
    <section class="ga-header">
      <div class="ga-header-row">
        <div>
          <h1 class="ga-title">{T('app_title')}</h1>
          <div class="ga-subtitle">{T('app_subtitle')}</div>
        </div>
        <div class="ga-status">{T('app_status')}</div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

st.session_state.setdefault('autonomous_enabled', False)
st.session_state.setdefault('pending_policy_confirmation', None)

@st.fragment
def render_sidebar():
    st.session_state.setdefault('autonomous_enabled', False)
    lang_labels = {'zh': '中文', 'en': 'English'}
    current_lang = st.session_state.get('ui_lang', LANG)
    selected_lang = st.radio(
        T('language'),
        ['zh', 'en'],
        index=0 if current_lang == 'zh' else 1,
        format_func=lang_labels.get,
        horizontal=True,
        key="sidebar_language_select",
    )
    if selected_lang != current_lang:
        st.session_state.ui_lang = selected_lang
        st.rerun(scope="app")

    llm_options = agent.list_llms()
    current_idx = agent.llm_no
    llm_labels = {idx: f"{idx}: {(name or '').strip()}" for idx, name, _ in llm_options}
    st.caption(f"{T('model_core')}: {llm_labels.get(current_idx, str(current_idx))}")
    selected_idx = st.selectbox(T('model_label'), [idx for idx, _, _ in llm_options], index=next((i for i, (idx, _, _) in enumerate(llm_options) if idx == current_idx), 0), format_func=llm_labels.get, label_visibility="collapsed", key="sidebar_llm_select")
    if selected_idx != current_idx:
        agent.next_llm(selected_idx); st.rerun(scope="fragment")
    if st.button(T('force_stop')):
        agent.abort(); st.toast(T('stop_sent')); st.rerun()
    if st.button(T('reinject_tools')):
        agent.llmclient.last_tools = ''
        try:
            hist_path = os.path.join(script_dir, '..', 'assets', 'tool_usable_history.json')
            with open(hist_path, 'r', encoding='utf-8') as f: tool_hist = json.load(f)
            agent.llmclient.backend.history.extend(tool_hist)
            st.toast(T('tools_injected'))
        except Exception as e: st.toast(T('tools_failed', error=e))
    if st.button(T('desktop_pet')):
        kwargs = {'creationflags': 0x08} if sys.platform == 'win32' else {}
        pet_script = os.path.join(script_dir, 'desktop_pet_v2.pyw')
        if not os.path.exists(pet_script): pet_script = os.path.join(script_dir, 'desktop_pet.pyw')
        subprocess.Popen([sys.executable, pet_script], **kwargs)
        def _pet_req(q):
            def _do():
                try: urlopen(f'http://127.0.0.1:41983/?{q}', timeout=2)
                except Exception: pass
            threading.Thread(target=_do, daemon=True).start()
        agent._pet_req = _pet_req
        if not hasattr(agent, '_turn_end_hooks'): agent._turn_end_hooks = {}
        def _pet_hook(ctx):
            parts = [f"Turn {ctx.get('turn','?')}"]
            if ctx.get('summary'): parts.append(ctx['summary'])
            if ctx.get('exit_reason'): parts.append('DONE')
            _pet_req(f'msg={quote(chr(10).join(parts))}')
            if ctx.get('exit_reason'): _pet_req('state=idle')
        agent._turn_end_hooks['pet'] = _pet_hook
        st.toast(T('pet_started'))

    with st.expander(T('audit_timeline'), expanded=False):
        try:
            from safety_policy import iter_audit_events
            audit_limit = st.selectbox(
                T('audit_timeline'),
                [12, 25, 50, 100],
                index=1,
                format_func=lambda value: T('audit_latest', value=value),
                label_visibility="collapsed",
                key="audit_timeline_limit",
            )
            events = iter_audit_events(limit=audit_limit)
            names = audit_event_names(events)
            selected_names = st.multiselect(
                T('audit_filter'),
                names,
                placeholder=T('audit_filter_placeholder'),
                label_visibility="collapsed",
                key="audit_timeline_event_filter",
            )
            show_details = st.checkbox(T('audit_show_details'), value=False, key="audit_timeline_show_details")
            visible_events = filter_audit_events(events, selected_names)
            if visible_events:
                for idx, event in enumerate(visible_events[:12]):
                    row = audit_event_row(event)
                    st.caption(f"{row['time']} | {row['event']}")
                    st.text(row["summary"] or "-")
                    if show_details:
                        st.json(audit_event_detail(event), expanded=False)
                if len(visible_events) > 12:
                    st.caption(T('audit_showing', shown=12, total=len(visible_events)))
            else:
                st.caption(T('audit_no_matches'))
        except Exception as e:
            st.caption(T('audit_unavailable', error=e))
    
    if st.button(T('find_tasks')):
        st.session_state['_inject_prompt'] = T('find_tasks_prompt')
        st.rerun(scope="app")
    st.divider()
    if st.button(T('start_autonomous')):
        st.session_state.last_reply_time = int(time.time()) - 1800
        st.session_state.autonomous_enabled = True
        st.toast(T('autonomous_started')); st.rerun(scope="app")
    if st.session_state.autonomous_enabled:
        if st.button(T('stop_autonomous')):
            st.session_state.autonomous_enabled = False
            st.toast(T('autonomous_disabled')); st.rerun(scope="app")
        st.caption(T('autonomous_on'))
    else:
        if st.button(T('allow_autonomous'), type="primary"):
            st.session_state.autonomous_enabled = True
            st.toast(T('autonomous_enabled')); st.rerun(scope="app")
        st.caption(T('autonomous_off'))
with st.sidebar: render_sidebar()

def fold_turns(text):
    """Return list of segments: [{'type':'text','content':...}, {'type':'fold','title':...,'content':...}]"""
    # 先把4+反引号块替换为占位符，避免误切子agent嵌套的 LLM Running
    _ph = []
    safe = re.sub(r'`{4,}.*?`{4,}', lambda m: (_ph.append(m.group(0)), f'\x00PH{len(_ph)-1}\x00')[1], text, flags=re.DOTALL)
    # 流式中间态：末尾可能有未闭合的4+反引号块，也需保护
    safe = re.sub(r'`{4,}[^`].*$', lambda m: (_ph.append(m.group(0)), f'\x00PH{len(_ph)-1}\x00')[1], safe, flags=re.DOTALL)
    parts = re.split(r'(\**LLM Running \(Turn \d+\) \.\.\.\*\**)', safe)
    parts = [re.sub(r'\x00PH(\d+)\x00', lambda m: _ph[int(m.group(1))], p) for p in parts]
    if len(parts) < 4: return [{'type': 'text', 'content': text}]
    segments = []
    if parts[0].strip(): segments.append({'type': 'text', 'content': parts[0]})
    turns = []
    for i in range(1, len(parts), 2):
        marker = parts[i]
        content = parts[i+1] if i+1 < len(parts) else ''
        turns.append((marker, content))
    for idx, (marker, content) in enumerate(turns):
        if idx < len(turns) - 1:
            _c = re.sub(r'`{3,}.*?`{3,}|<thinking>.*?</thinking>', '', content, flags=re.DOTALL)
            matches = re.findall(r'<summary>\s*((?:(?!<summary>).)*?)\s*</summary>', _c, re.DOTALL)
            if matches:
                title = matches[0].strip()
                title = title.split('\n')[0]
                if len(title) > 50: title = title[:50] + '...'
            else:
                _plain = _c.strip().split('\n', 1)[0]
                title = (_plain[:50] + '...') if len(_plain) > 50 else (_plain or marker.strip('*'))
            segments.append({'type': 'fold', 'title': title, 'content': content})
        else: segments.append({'type': 'text', 'content': marker + content})
    return segments
_SUMMARY_TAG_RE = re.compile(r'<summary>.*?</summary>\s*', re.DOTALL)

def render_segments(segments, suffix=''):
    # 整块重画：调用方用 slot.container() 包裹，保证 DOM 路径稳定、跨 rerun 对齐（消除"灰色重影"）。
    # heartbeat 空转时 segments 不变 → Streamlit 后端 diff 无变化 → 前端零闪烁；
    # 但 container/markdown 本身是 API 调用，StopException 仍会被抛出（abort 照常起作用）。
    for seg in segments:
        if seg['type'] == 'fold':
            with st.expander(seg['title'], expanded=False): st.markdown(seg['content'])
        else:
            st.markdown(seg['content'] + suffix)

def render_policy_confirmation_panel():
    pending = st.session_state.get('pending_policy_confirmation')
    if not pending: return
    title = T('policy_confirm_title')
    tool = pending.get('tool_name') or '-'
    risk = pending.get('risk') or '-'
    reason = pending.get('reason') or pending.get('question') or ''
    token_id = pending.get('token_id') or ''
    st.warning(f"**{title}**\n\n`{tool}` | risk `{risk}` | token `{token_id}`\n\n{reason}")
    col_allow, col_cancel = st.columns([1, 1])
    with col_allow:
        if st.button(T('policy_confirm_allow'), type="primary", key="policy_confirm_allow_once"):
            result = apply_confirmation_token(pending)
            if result.get("status") == "success":
                st.session_state.pending_policy_confirmation = None
                st.session_state['_inject_prompt'] = pending.get('prompt') or ''
                st.toast(T('policy_confirm_retrying'))
                st.rerun(scope="app")
            else:
                st.error(result.get("msg", "confirmation failed"))
    with col_cancel:
        if st.button(T('policy_confirm_cancel'), key="policy_confirm_cancel"):
            st.session_state.pending_policy_confirmation = None
            st.toast(T('policy_confirm_cancelled'))
            st.rerun(scope="app")

def agent_backend_stream(prompt=None):
    """Drain main task display_queue.
    - prompt given:  start a fresh task; new dq is kept in session_state.
    - prompt is None: resume a dq left in session_state by a prior run (e.g. after /btw).
    Per-chunk progress is mirrored to session_state.partial_response so the rendered
    bubble survives reruns. No implicit agent.abort() — explicit stop is on the Stop button."""
    if prompt is not None:
        st.session_state.pending_policy_confirmation = None
        st.session_state.display_queue = agent.put_task(prompt, source="user")
        st.session_state.partial_response = ''
    dq = st.session_state.get('display_queue')
    if dq is None: return
    # Drop a dangling 'LLM Running (Turn N) ...' marker if the captured partial
    # ended right at a turn boundary with no content yet — otherwise the resume
    # bubble flashes as a marker-only gray line. The marker reappears with
    # content on the next chunk (raw_resp is cumulative).
    response = re.sub(r'\**LLM Running \(Turn \d+\) \.\.\.\**\s*$',
                      '', st.session_state.get('partial_response', '')).rstrip()
    try:
        while True:
            try: item = dq.get(timeout=1)
            except queue.Empty:
                yield response   # heartbeat: let outer st.markdown() run → Streamlit checks StopException
                continue
            if 'next' in item:
                response = item['next']
                st.session_state.partial_response = response
                yield response
            if 'done' in item:
                st.session_state.display_queue = None
                st.session_state.partial_response = ''
                st.session_state.pending_policy_confirmation = item.get('pending_confirmation')
                yield item['done']; break
    finally:
        agent.abort()
        try:
            st.session_state.display_queue = None
            st.session_state.partial_response = ''
        except BaseException:
            pass


def render_main_stream(prompt=None):
    """Render the assistant bubble for the main task (new or resumed). Saves final to messages."""
    with st.chat_message("assistant"):
        frozen = 0; live = st.empty(); response = ''
        CURSOR = ' ▌'
        for response in agent_backend_stream(prompt):
            segs = fold_turns(response)
            n_done = max(0, len(segs) - 1)
            while frozen < n_done:
                with live.container(): render_segments([segs[frozen]])
                live = st.empty(); frozen += 1
            with live.container(): render_segments([segs[-1]], suffix=CURSOR)   # live 区域
        segs = fold_turns(response)
        for i in range(frozen, len(segs)):
            with live.container(): render_segments([segs[i]])
            if i < len(segs) - 1: live = st.empty()
    if response:
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.last_reply_time = int(time.time())

if "messages" not in st.session_state: st.session_state.messages = []
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        # 用 slot=st.empty() + with slot.container(): ... 的外壳，DOM 路径和流式渲染完全一致，跨 rerun 对齐
        slot = st.empty()
        with slot.container():
            if msg["role"] == "assistant": render_segments(fold_turns(msg["content"]))
            else: st.markdown(msg["content"])

confirmation_slot = st.empty()
with confirmation_slot.container():
    render_policy_confirmation_panel()

# Scroll-height ghost fix: during streaming, expander open/close mid-animation can leave
# phantom height → scrollbar long but can't scroll to bottom. Periodically detect & reflow.
try:
    from streamlit import iframe as _st_iframe  # 1.56+
    _embed_html = lambda html, **kw: _st_iframe(html, **{k: max(v, 1) if isinstance(v, int) else v for k, v in kw.items()})
except (ImportError, AttributeError):
    from streamlit.components.v1 import html as _embed_html  # ≤1.55
_js_scroll_fix = (
    "!function(){var p=window.parent;if(p.__sfx2)return;p.__sfx2=1;var d=p.document;"
    "var pending=0;"
    "function f(){pending=0;var m=d.querySelector('section.main');if(!m)return;"
    "var s=m.scrollTop,h=m.scrollHeight;"
    "m.style.minHeight=h+1+'px';void m.offsetHeight;"
    "m.style.minHeight='';void m.offsetHeight;"
    "m.scrollTop=s}"
    "function schedule(){if(!pending){pending=1;requestAnimationFrame(f)}}"
    "d.addEventListener('transitionend',function(e){"
    "e.target.closest&&e.target.closest('details')&&setTimeout(schedule,60)},!0);"
    "new MutationObserver(function(){setTimeout(schedule,80)})"
    ".observe(d.body,{subtree:1,attributes:1,attributeFilter:['open']})}()"
)
# IME composition fix (macOS only) - prevents Enter from submitting during CJK input
_js_ime_fix = ("" if os.name == 'nt' else
    "!function(){if(window.parent.__imeFix)return;window.parent.__imeFix=1;"
    "var d=window.parent.document,c=0;"
    "d.addEventListener('compositionstart',()=>c=1,!0);"
    "d.addEventListener('compositionend',()=>c=0,!0);"
    "function f(){d.querySelectorAll('textarea[data-testid=stChatInputTextArea]')"
    ".forEach(t=>{t.__imeFix||(t.__imeFix=1,t.addEventListener('keydown',e=>{"
    "e.key==='Enter'&&!e.shiftKey&&(e.isComposing||c||e.keyCode===229)&&"
    "(e.stopImmediatePropagation(),e.preventDefault())},!0))})}"
    "f();new MutationObserver(f).observe(d.body,{childList:1,subtree:1})}()")
_embed_html(f'<script>{_js_scroll_fix};{_js_ime_fix}</script>', height=0)

_injected = st.session_state.pop('_inject_prompt', None)
prompt = st.chat_input(T('chat_placeholder')) or _injected
if prompt:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    cmd = (prompt or "").strip()
    def _reset_and_rerun():
        st.session_state.streaming = False
        st.session_state.stopping = False
        st.session_state.display_queue = None
        st.session_state.partial_response = ""
        st.session_state.reply_ts = ""
        st.session_state.current_prompt = ""
        st.session_state.last_reply_time = int(time.time())
        st.rerun()
    if cmd == "/new":
        st.session_state.messages = [{"role": "assistant", "content": reset_conversation(agent), "time": ts}]
        _reset_and_rerun()
    if cmd.startswith("/continue"):
        m = re.match(r'/continue\s+(\d+)\s*$', cmd.strip())
        sessions = list_sessions(exclude_pid=os.getpid()) if m else []
        idx = int(m.group(1)) - 1 if m else -1
        # Resolve target path BEFORE handle (which snapshots current log, shifting indices).
        target = sessions[idx][0] if 0 <= idx < len(sessions) else None
        result = handle_frontend_command(agent, cmd)
        history = extract_ui_messages(target) if target and result.startswith('✅') else None
        tail = [{"role": "assistant", "content": result, "time": ts}]
        if history: st.session_state.messages = history + tail
        else: st.session_state.messages = list(st.session_state.messages)+[{"role": "user", "content": cmd, "time": ts}]+tail
        _reset_and_rerun()
    if cmd.startswith("/btw"):
        answer = btw_handle_frontend(agent, cmd)  # sync; bypasses put_task → main agent.run() untouched
        st.session_state.messages = list(st.session_state.messages) + [
            {"role": "user", "content": prompt, "time": ts},
            {"role": "assistant", "content": answer, "time": ts},
        ]
        st.rerun()  # preserve display_queue/partial_response so resume path drains the running main task
    if cmd.startswith("/export"):
        parts = cmd.split(maxsplit=1)
        sub = parts[1].strip() if len(parts) > 1 else ""
        sub_lower = sub.lower()
        if not sub:
            result = (
                "**选择导出方式：**\n\n"
                "- `/export clip` — 整理到代码块中\n"
                "- `/export <文件名>` — 导出到 `temp/<文件名>`（默认 .md 后缀）\n"
                "- `/export all` — 显示完整对话日志路径"
            )
        elif sub_lower == "all":
            log = agent.log_path
            result = (f"📂 完整对话日志:\n\n`{log}`" if os.path.isfile(log)
                      else f"❌ 当前会话尚无日志文件")
        else:
            text = last_assistant_text(agent)
            if not text:
                result = "❌ 还没有模型回复可导出"
            elif sub_lower in ("clip", "copy"):
                result = f"📋 最后一轮回复（点代码块右上角 📋 复制）:\n\n{wrap_for_clipboard(text)}"
            else:
                try:
                    path = export_to_temp(text, sub)
                    result = f"✅ 已导出:\n\n`{path}`"
                except Exception as e:
                    result = f"❌ 导出失败: {e}"
        st.session_state.messages = list(st.session_state.messages) + [
            {"role": "user", "content": cmd, "time": ts},
            {"role": "assistant", "content": result, "time": ts},
        ]
        _reset_and_rerun()
    # Regular prompt: any in-flight task will be aborted by the finally block in
    # agent_backend_stream when StopException interrupts the prior generator.
    st.session_state.messages.append({"role": "user", "content": prompt})
    if hasattr(agent, '_pet_req') and not prompt.startswith('/'): agent._pet_req('state=walk')
    with st.chat_message("user"): st.markdown(prompt)
    render_main_stream(prompt)
    with confirmation_slot.container():
        render_policy_confirmation_panel()
elif st.session_state.get('display_queue') is not None:
    # No new prompt but a task is mid-flight (typically a /btw rerun) — resume drain.
    render_main_stream()
    with confirmation_slot.container():
        render_policy_confirmation_panel()

if st.session_state.autonomous_enabled:
    st.markdown(f"""<div id="last-reply-time" style="display:none">{st.session_state.get('last_reply_time', int(time.time()))}</div>""", unsafe_allow_html=True)
