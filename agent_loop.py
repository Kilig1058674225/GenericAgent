import json, re, os
from dataclasses import dataclass
from typing import Any, Optional
try: from plugins.hooks import trigger as _hook
except ImportError: _hook = lambda *a, **k: None
try:
    from safety_policy import (
        CONFIRMATION_TOKEN_ENV,
        classify_tool_call,
        confirmation_token_for_decision,
        consume_confirmation_token,
        write_policy_audit,
    )
except ImportError:
    CONFIRMATION_TOKEN_ENV = "GA_POLICY_CONFIRM_TOKEN"
    classify_tool_call = confirmation_token_for_decision = consume_confirmation_token = write_policy_audit = None
@dataclass
class StepOutcome:
    data: Any
    next_prompt: Optional[str] = None
    should_exit: bool = False
def _exception_data(exc):
    return {"type": type(exc).__name__, "message": str(exc)[:1000]}
def try_call_generator(func, *args, **kwargs):
    ret = func(*args, **kwargs)
    if hasattr(ret, '__iter__') and not isinstance(ret, (str, bytes, dict, list)): ret = yield from ret
    return ret

class BaseHandler:
    def turn_end_callback(self, response, tool_calls, tool_results, turn, next_prompt, exit_reason): return next_prompt
    def dispatch(self, tool_name, args, response, index=0, tool_num=1):
        method_name = f"do_{tool_name}"
        if classify_tool_call and write_policy_audit:
            decision = classify_tool_call(tool_name, args, handler=self)
            confirmation_token = None
            confirmation_approved = False
            audit_extra = None
            if decision.needs_confirmation and confirmation_token_for_decision and consume_confirmation_token:
                confirmation_token = confirmation_token_for_decision(decision, args)
                confirmation_approved = consume_confirmation_token(decision, args)
                audit_extra = {
                    "confirmation": {
                        "status": "approved" if confirmation_approved else "required",
                        "env_var": CONFIRMATION_TOKEN_ENV,
                        "token_id": confirmation_token[-12:],
                    }
                }
            executed = not decision.blocks_execution or confirmation_approved
            write_policy_audit(decision, args, index=index, tool_num=tool_num, executed=executed, extra=audit_extra)
            if confirmation_approved:
                yield f"[Policy] confirmed: {tool_name} ({decision.risk}) - {decision.reason}\n"
            if decision.blocks_execution and not confirmation_approved:
                yield f"[Policy] {decision.decision}: {tool_name} ({decision.risk}) - {decision.reason}\n"
                data = {
                    "status": "blocked",
                    "tool_name": tool_name,
                    "policy": decision.public_dict(),
                }
                if decision.needs_confirmation:
                    data = {
                        "status": "INTERRUPT",
                        "intent": "HUMAN_CONFIRMATION_REQUIRED",
                        "data": {
                            "question": f"工具 {tool_name} 被安全策略暂停：{decision.reason}。如确认本次精确调用可执行，请设置 {CONFIRMATION_TOKEN_ENV} 后重试；该 token 只匹配当前工具与参数。",
                            "candidates": ["取消执行", f"设置 {CONFIRMATION_TOKEN_ENV} 后重试"],
                            "confirmation_token": confirmation_token,
                            "confirmation_env_var": CONFIRMATION_TOKEN_ENV,
                            "policy": decision.public_dict(),
                        },
                    }
                    return StepOutcome(data, next_prompt="", should_exit=True)
                return StepOutcome(data, next_prompt=f"工具 {tool_name} 已被安全策略阻止：{decision.reason}", should_exit=False)
        if hasattr(self, method_name):
            args['_index'] = index; args['_tool_num'] = tool_num
            _hook('tool_before', locals())
            ret = None; error = None
            try:
                ret = yield from try_call_generator(getattr(self, method_name), args, response)
                return ret
            except Exception as exc:
                error = _exception_data(exc)
                raise
            finally:
                _hook('tool_after', locals())
        elif tool_name == 'bad_json': return StepOutcome(None, next_prompt=args.get('msg', 'bad_json'), should_exit=False)
        else:
            yield f"未知工具: {tool_name}\n"
            return StepOutcome(None, next_prompt=f"未知工具 {tool_name}", should_exit=False)

def json_default(o): return list(o) if isinstance(o, set) else str(o)
def exhaust(g):
    try: 
        while True: next(g)
    except StopIteration as e: return e.value

def get_pretty_json(data):
    if isinstance(data, dict) and "script" in data:
        data = data.copy(); data["script"] = data["script"].replace("; ", ";\n  ")
    return json.dumps(data, indent=2, ensure_ascii=False).replace('\\n', '\n')

def agent_runner_loop(client, system_prompt, user_input, handler, tools_schema, 
                      max_turns=40, verbose=True, initial_user_content=None, yield_info=False):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_content if initial_user_content is not None else user_input}
    ]
    turn = 0; response = None; tool_calls = []; tool_results = []; next_prompt = ''; exit_reason = {}
    handler.max_turns = max_turns
    error = None
    _hook('agent_before', locals())
    try:
        while turn < handler.max_turns:
            turn += 1; turnstr = f'LLM Running (Turn {turn}) ...'
            if handler.parent.task_dir: turnstr = f'Turn {turn} ...'
            if verbose: turnstr = f'**{turnstr}**'
            if yield_info: yield {'turn': turn}
            yield f"\n\n{turnstr}\n\n"
            if turn%10 == 0: client.last_tools = ''  # 每10轮重置一次工具描述
            _hook('turn_before', locals())
            _hook('llm_before', locals())
            response_gen = client.chat(messages=messages, tools=tools_schema)
            if verbose:
                response = yield from response_gen
                yield '\n\n'
            else:
                response = exhaust(response_gen)
                cleaned = _clean_content(response.content)
                if cleaned: yield cleaned + '\n'
            _hook('llm_after', locals())

            if not response.tool_calls: tool_calls = [{'tool_name': 'no_tool', 'args': {}}]
            else: tool_calls = [{'tool_name': tc.function.name, 'args': json.loads(tc.function.arguments), 'id': tc.id}
                              for tc in response.tool_calls]

            tool_results = []; next_prompts = set(); exit_reason = {}; final_turn = False
            for ii, tc in enumerate(tool_calls):
                tool_name, args, tid = tc['tool_name'], tc['args'], tc.get('id', '')
                if tool_name == 'no_tool': pass
                else:
                    if verbose: yield f"🛠️ Tool: `{tool_name}`  📥 args:\n````text\n{get_pretty_json(args)}\n````\n"
                    else: yield f"🛠️ {tool_name}({_compact_tool_args(tool_name, args)})\n\n\n"
                handler.current_turn = turn
                gen = handler.dispatch(tool_name, args, response, index=ii, tool_num=len(tool_calls))
                try:
                    v = next(gen)
                    def proxy(): yield v; return (yield from gen)
                    if verbose: yield '`````\n'
                    outcome = (yield from proxy()) if verbose else exhaust(proxy())
                    if verbose: yield '`````\n'
                except StopIteration as e: outcome = e.value

                if outcome.should_exit:
                    exit_reason = {'result': 'EXITED', 'data': outcome.data}; break
                if not outcome.next_prompt:
                    exit_reason = {'result': 'CURRENT_TASK_DONE', 'data': outcome.data}; break
                if outcome.next_prompt.startswith('未知工具'): client.last_tools = ''
                if outcome.data is not None and tool_name != 'no_tool':
                    datastr = json.dumps(outcome.data, ensure_ascii=False, default=json_default) if type(outcome.data) in [dict, list] else str(outcome.data)
                    tool_results.append({'tool_use_id': tid, 'content': datastr})
                next_prompts.add(outcome.next_prompt)
            if len(next_prompts) == 0 or exit_reason:
                if len(handler._done_hooks) == 0 or exit_reason.get('result', '') == 'EXITED':
                    final_turn = True
                else:
                    next_prompts.add(handler._done_hooks.pop(0))
            if not exit_reason and turn >= handler.max_turns:
                exit_reason = {'result': 'MAX_TURNS_EXCEEDED'}
                final_turn = True
            next_prompt = handler.turn_end_callback(response, tool_calls, tool_results, turn, '\n'.join(next_prompts), exit_reason)
            _hook('turn_after', locals())
            if final_turn: break
            messages = [{"role": "user", "content": next_prompt, "tool_results": tool_results}]   # just new message, history is kept in *Session
        if not exit_reason: exit_reason = {'result': 'MAX_TURNS_EXCEEDED'}
        return exit_reason
    except Exception as exc:
        error = _exception_data(exc)
        exit_reason = {'result': 'ERROR', 'error': error}
        raise
    finally:
        _hook('agent_after', locals())

def _clean_content(text):
    if not text: return ''
    def _shrink_code(m):
        lines = m.group(0).split('\n')
        lang = lines[0].replace('```','').strip()
        body = [l for l in lines[1:-1] if l.strip()]
        if len(body) <= 6: return m.group(0)
        preview = '\n'.join(body[:5])
        return f'```{lang}\n{preview}\n  ... ({len(body)} lines)\n```'
    text = re.sub(r'```[\s\S]*?```', _shrink_code, text)
    for p in [r'<file_content>[\s\S]*?</file_content>', r'<tool_(?:use|call)>[\s\S]*?</tool_(?:use|call)>', r'(\r?\n){3,}']:
        text = re.sub(p, '\n\n' if '\\n' in p else '', text)
    return text.strip()

def _compact_tool_args(name, args):
    a = {k: v for k, v in args.items() if k != '_index'}
    for k in ('path',): 
        if k in a: a[k] = os.path.basename(a[k])
    if name == 'update_working_checkpoint': s = a.get('key_info', ''); return (s[:60]+'...') if len(s)>60 else s
    if name == 'ask_user':
        q = str(a.get('question', ''))
        cs = a.get('candidates') or []
        if cs: q += '\ncandidates:\n' + '\n'.join(f'- {c}' for c in cs)
        return q
    s = json.dumps(a, ensure_ascii=False); return (s[:120]+'...') if len(s)>120 else s
