"""Run selected Harness cases with lossless events, timing and reported usage.

One round = one Harness step (model generation plus associated tool execution).
Raw session events preserve provider attempts, tool arguments/results and all
provider-visible reasoning; private model reasoning is not observable.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import run_agent as runner


def load_key():
    for line in (runner.REPO_ROOT / '.env').read_text().splitlines():
        text = line.strip()
        if text and not text.startswith('#') and '=' in text:
            name, value = text.removeprefix('export ').split('=', 1)
            if name.strip() in ('ds_api_key', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY'):
                os.environ['DEEPSEEK_API_KEY'] = value.strip().strip('\"\'')
                return
    raise RuntimeError('No key configured in .env')


def summarize(trace: Path):
    rounds = []
    starts = {}
    attempts = 0
    calls = {}
    tool_starts = {}
    tool_timings = []
    model_times = {}
    pending_usage = {}
    raw_step_usage = {}
    last_turn_reason = None
    observed_models = set()
    auxiliary_requests = 0
    usage_missing = 0
    totals = {}
    if not trace.exists():
        return {'round_count': 0, 'rounds': [], 'reported_usage': {}, 'usage_complete': False}
    for line in trace.read_text().splitlines():
        record = json.loads(line)
        event = record['event']; kind = event['type']; data = event.get('data', {})
        key = str(data.get('step'))
        if kind == 'request/context':
            observed_models.add((str(data.get('provider')), str(data.get('model'))))
        if kind.endswith('-llm-request'):
            auxiliary_requests += 1
        if kind == 'turn/end':
            last_turn_reason = data.get('reason')
        if kind == 'step/start':
            starts[key] = record
        elif kind == 'assistant/message' and key in starts:
            model_times[key] = round((record['monotonic_ms']-starts[key]['monotonic_ms'])/1000, 3)
            if data.get('usage') is not None:
                pending_usage.setdefault(key, []).append(data['usage'])
                raw_step_usage.setdefault(key, []).append(data['usage'])
        elif kind == 'assistant/attempt':
            attempts += 1
        elif kind == 'tool/call':
            name = data.get('name', 'unknown'); calls[name] = calls.get(name, 0) + 1
            tool_starts[data['callId']] = (name, record)
        elif kind == 'tool/result' and event.get('surfaceOp') == 'append':
            call_id = data.get('message', {}).get('toolCallId')
            entry = tool_starts.pop(call_id, None)
            if entry:
                name, begin = entry
                tool_timings.append({'tool': name, 'call_id': call_id, 'step': data.get('step'),
                                     'is_error': bool(data.get('message', {}).get('isError')) or data.get('error') is not None,
                                     'elapsed_s': round((record['monotonic_ms']-begin['monotonic_ms'])/1000, 3)})
        elif kind == 'step/end':
            start = starts.pop(key, None)
            pending_usage.pop(key, None)
            rounds.append({'step': data.get('step'), 'started_at': start['recorded_at'] if start else None,
                           'ended_at': record['recorded_at'],
                           'model_elapsed_s': model_times.get(key),
                           'elapsed_s': round((record['monotonic_ms']-start['monotonic_ms'])/1000, 3) if start else None})
    # The CLI aggregates usage across failed/retried attempts for each step.
    projection = trace.parent / 'events.jsonl'
    samples = []
    if projection.exists():
        for line in projection.read_text().splitlines():
            try: item = json.loads(line)
            except json.JSONDecodeError: continue
            if item.get('type') == 'status' and item.get('phase') == 'step_end':
                usage = item.get('usage')
                samples.append(usage)
                if usage is None: usage_missing += 1
                else:
                    for name, value in usage.items():
                        if isinstance(value, (int, float)): totals[name] = totals.get(name, 0)+value
    recovered = []
    for index, row in enumerate(rounds):
        row['usage'] = samples[index] if index < len(samples) else None
        row['tool_error_count'] = sum(t['is_error'] for t in tool_timings if t['step'] == row['step'])
        if row['usage'] is None and raw_step_usage.get(str(row['step'])) and attempts == 0:
            raw_total = {}
            for sample in raw_step_usage[str(row['step'])]:
                for name, value in sample.items():
                    if isinstance(value, (int, float)):
                        raw_total[name] = raw_total.get(name, 0) + value
                        totals[name] = totals.get(name, 0) + value
            row['usage'] = raw_total
            row['usage_source'] = 'raw_session_trace'
            recovered.append(row['step'])
    incomplete = []
    for key, start in starts.items():
        reported = {}
        for sample in pending_usage.get(key, []):
            for name, value in sample.items():
                if isinstance(value, (int, float)):
                    reported[name] = reported.get(name, 0) + value
                    totals[name] = totals.get(name, 0) + value
        incomplete.append({'step': start['event']['data'].get('step'), 'started_at': start['recorded_at'],
                           'model_elapsed_s': model_times.get(key), 'reported_usage_so_far': reported or None})
    return {'round_count': len(rounds), 'round_started_count': len(rounds)+len(starts),
            'incomplete_round_count': len(starts), 'incomplete_rounds': incomplete, 'rounds': rounds,
            'provider_retry_attempt_events': attempts, 'tool_calls': calls,
            'reconstruction_build_calls': calls.get('cad_build', 0), 'tool_timings': tool_timings,
            'observed_models': [{'provider': p, 'model': m} for p, m in sorted(observed_models)],
            'auxiliary_request_events': auxiliary_requests,
            'last_turn_reason': last_turn_reason, 'usage_recovered_from_raw_trace_steps': recovered,
            'incomplete_tool_calls': [{'call_id': k, 'tool': v[0], 'started_at': v[1]['recorded_at']} for k, v in tool_starts.items()],
            'reported_usage': totals,
            'usage_complete': bool(rounds) and all(r.get('usage') is not None for r in rounds) and not starts,
            'usage_note': 'Harness-reported agent step usage including retries. For this provider cacheReadTokens are separate from inputTokens; use totalTokens for the total. Reasoning tokens, when reported, are included in output. Auxiliary background requests may not be included; missing usage is unknown, not zero.'}


def write_records(folder, summary):
    if summary.get('timed_out') and summary.get('rounds'):
        summary['rounds'][-1]['status'] = 'aborted'
    if summary.get('started_at') and summary.get('elapsed_s') is not None:
        ended = datetime.fromisoformat(summary['started_at']) + timedelta(seconds=summary['elapsed_s'])
        summary['ended_at'] = ended.isoformat()
        for row in summary.get('incomplete_rounds', []):
            row['ended_at'] = ended.isoformat()
            row['elapsed_s'] = round((ended-datetime.fromisoformat(row['started_at'])).total_seconds(), 3)
        for row in summary.get('incomplete_tool_calls', []):
            row['elapsed_s_until_case_end'] = round((ended-datetime.fromisoformat(row['started_at'])).total_seconds(), 3)
    (folder/'metrics.json').write_text(json.dumps(summary, indent=2))
    columns = ['step', 'status', 'started_at', 'ended_at', 'elapsed_s', 'model_elapsed_s', 'tool_error_count',
               'inputTokens', 'outputTokens', 'cacheReadTokens', 'totalTokens', 'reasoningTokens']
    with (folder/'rounds.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in summary['rounds']:
            writer.writerow({**row, 'status': row.get('status', 'completed'), **(row.get('usage') or {})})
        for row in summary.get('incomplete_rounds', []):
            writer.writerow({**row, 'status': 'incomplete', **(row.get('reported_usage_so_far') or {})})
    trace = folder/'session-trace.jsonl'
    with (folder/'trace.md').open('w') as handle:
        handle.write('# '+summary['case']+' agent trace\n\n')
        handle.write('Lossless source: session-trace.jsonl. Image payloads are retained there; this readable view omits binary image data. Only provider-returned reasoning is observable.\n\n')
        if trace.exists():
            for line in trace.read_text().splitlines():
                record = json.loads(line); event = record['event']; kind = event['type']; data = event.get('data', {})
                title = f"\n## {record['recorded_at']} · {kind}\n\n"
                if kind == 'assistant/message':
                    handle.write(title)
                    for block in data['message'].get('content', []):
                        if block.get('type') in ('text','reasoning'):
                            handle.write('### '+block['type']+'\n\n'+block.get('text','')+'\n\n')
                    handle.write('Usage: '+json.dumps(data.get('usage'))+'\n')
                elif kind in ('step/start','step/end','tool/call'):
                    handle.write(title+'```json\n'+json.dumps(data,ensure_ascii=False,indent=2)+'\n```\n')
                elif kind == 'tool/result' and event.get('surfaceOp') == 'append':
                    handle.write(title)
                    for block in data.get('message',{}).get('content',[]):
                        if block.get('type') == 'text': handle.write(block.get('text','')+'\n\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', default='4,5,6')
    parser.add_argument('--timeout', type=float, default=1200)
    parser.add_argument('--setup-only', action='store_true')
    parser.add_argument('--jobs', type=int, default=1)
    args = parser.parse_args()
    load_key()
    runner.setup(runner.DEFAULT_HOME, runner.DEFAULT_OUT)
    if args.setup_only: return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    record_root = runner.REPO_ROOT/'reports/runs'/stamp
    record_root.mkdir(parents=True)
    print('RECORD_ROOT:', record_root, flush=True)
    results = []
    all_started = time.monotonic()
    def run_one(number):
        case = 'test_case_'+number.strip().removeprefix('test_case_')
        folder = record_root/case; folder.mkdir()
        workspace = runner.WORKSPACES/(case+'_'+stamp); workspace.mkdir(parents=True)
        env = runner.child_env(runner.DEFAULT_HOME, runner.INPUTS/case, runner.DEFAULT_OUT)
        env['AGENTIC_CAD_TRACE_FILE'] = str(folder/'session-trace.jsonl')
        # Workspace has no reference solutions; grant case images read access.
        cmd = [runner.find_dsh(), '--profile', 'headless', '--json',
               '--add-dir', str(runner.INPUTS/case), runner.task_prompt(case)]
        started_at = datetime.now(timezone.utc).isoformat(); started = time.monotonic()
        print('START',case,started_at,flush=True)
        with (folder/'events.jsonl').open('w') as stdout, (folder/'stderr.log').open('w') as stderr:
            process = subprocess.Popen(cmd, cwd=workspace, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            timed_out = False
            while process.poll() is None:
                elapsed = time.monotonic()-started
                if elapsed >= args.timeout:
                    import signal
                    os.killpg(process.pid, signal.SIGTERM)
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait()
                    timed_out = True; break
                time.sleep(1)
        summary = {'case': case, 'started_at': started_at, 'elapsed_s': round(time.monotonic()-started, 3),
                   'returncode': process.returncode, 'timed_out': timed_out,
                   'workspace': str(workspace), 'model': 'deepseek-flash',
                   **summarize(folder/'session-trace.jsonl')}
        output = runner.DEFAULT_OUT/f'{case}.stp'
        summary['output_bytes'] = output.stat().st_size if output.exists() else 0
        if output.exists(): shutil.copy2(output, folder/output.name)
        for path in workspace.glob('*.py'): shutil.copy2(path, folder/path.name)
        write_records(folder, summary)
        print('DONE',case,'seconds',summary['elapsed_s'],'rounds',summary['round_count'],'tokens',summary['reported_usage'],'bytes',summary['output_bytes'],flush=True)
        return summary

    numbers = args.cases.split(',')
    if args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(run_one, number) for number in numbers]
            results.extend(f.result() for f in as_completed(futures))
    else:
        for number in numbers:
            results.append(run_one(number))
    (record_root/'summary.json').write_text(json.dumps({'total_elapsed_s':round(time.monotonic()-all_started,3),'cases':results},indent=2))
    print('COMPLETE',record_root,flush=True)


if __name__ == '__main__': main()
