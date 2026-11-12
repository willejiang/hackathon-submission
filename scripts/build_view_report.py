"""Build an offline comparison of reference images and current STEP projections."""
from pathlib import Path
import base64
import io
import json
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agentic_cad import cad, raster


def case_status(name, available):
    if not available:
        return '无 STEP 产物 · 仅展示输入'
    records = sorted((ROOT/'reports/runs').glob(f'*/{name}/metrics.json'))
    if not records:
        return '已有 STEP · 8 / 8 视图'
    metrics = json.loads(records[-1].read_text())
    score_path = records[-1].parent/'score.json'
    if not score_path.exists():
        return '已有 STEP · 8 / 8 视图'
    score = json.loads(score_path.read_text())
    if metrics.get('timed_out'):
        return f'超时候选 · IoU {score["iou_all"]:.4f} · 体积 {score["volume_ratio"]:.4f}×'
    return f'本地硬性检查{"通过" if score["gating_ok"] else "失败"} · IoU {score["iou_all"]:.4f}'


def uri(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()


def shaded(vertices, faces, view, size=768):
    """Orthographic triangle rasterization with a depth buffer and flat lighting."""
    u, v = np.array(view.u), np.array(view.v)
    toward = np.cross(u, v)
    uv = raster.project(vertices, view)
    xy, _ = raster._fit(uv, size=size, fit_px=size * 0.963)
    xy[:, 1] = size - xy[:, 1]
    depth = vertices @ toward
    zbuf = np.full((size, size), -np.inf)
    rgb = np.full((size, size, 3), 255, dtype=np.uint8)
    light = .35*u + .55*v + toward
    light /= np.linalg.norm(light)
    for face in faces:
        tri = xy[face]
        a, b, c = vertices[face]
        normal = np.cross(b-a, c-a)
        norm = np.linalg.norm(normal)
        if norm < 1e-12:
            continue
        normal /= norm
        x0, y0 = np.maximum(np.floor(tri.min(axis=0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(tri.max(axis=0)).astype(int), size-1)
        if x1 < x0 or y1 < y0:
            continue
        ax, ay = tri[0]; bx, by = tri[1]; cx, cy = tri[2]
        den = (by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
        if abs(den) < 1e-10:
            continue
        yy, xx = np.mgrid[y0:y1+1, x0:x1+1]
        xx = xx+.5; yy = yy+.5
        w0 = ((by-cy)*(xx-cx)+(cx-bx)*(yy-cy))/den
        w1 = ((cy-ay)*(xx-cx)+(ax-cx)*(yy-cy))/den
        w2 = 1-w0-w1
        z = w0*depth[face[0]]+w1*depth[face[1]]+w2*depth[face[2]]
        old = zbuf[y0:y1+1, x0:x1+1]
        mask = (w0 >= -1e-7)&(w1 >= -1e-7)&(w2 >= -1e-7)&(z > old)
        old[mask] = z[mask]
        shade = .35 + .65*max(0, float(normal @ light))
        rgb[y0:y1+1, x0:x1+1][mask] = np.array([155, 178, 196])*shade
    return Image.fromarray(rgb)


def main():
    cases = []
    for directory in sorted((ROOT/'artifacts/inputs').glob('test_case_*'), key=lambda p: int(p.name.split('_')[-1])):
        output = ROOT/'artifacts/outputs'/f'{directory.name}.stp'
        mesh = raster.mesh_of(cad.reopen_step(output)) if output.exists() else None
        views = []
        for view in raster.VIEWS:
            with Image.open(directory/'images'/f'{view.stem}.png') as image:
                original = uri(image.convert('RGB'))
            views.append({'name': view.stem, 'original': original,
                          'generated': uri(shaded(*mesh, view)) if mesh else None})
        status = case_status(directory.name, mesh is not None)
        run_data = {}
        records = sorted((ROOT/'reports/runs').glob(f'*/{directory.name}/metrics.json'))
        if records:
            metrics = json.loads(records[-1].read_text())
            score_file = records[-1].parent/'score.json'
            if score_file.exists():
                scored = json.loads(score_file.read_text())
                run_data = {'rounds': metrics.get('round_count'), 'builds': metrics.get('reconstruction_build_calls'),
                            'elapsed_s': metrics.get('elapsed_s'), 'tokens': metrics.get('reported_usage', {}).get('totalTokens'),
                            'iou': scored.get('iou_all'), 'volume_ratio': scored.get('volume_ratio'),
                            'gating_ok': scored.get('gating_ok'), 'timed_out': metrics.get('timed_out', False)}
        trace = []
        trace_files = sorted((ROOT/'reports/runs').glob(f'*/{directory.name}/session-trace.jsonl'))
        trace_files = [path for path in trace_files if (path.parent/'metrics.json').exists()]
        if trace_files:
            for line in trace_files[-1].read_text().splitlines():
                try: trace.append(json.loads(line))
                except json.JSONDecodeError: continue
        cases.append({'name': directory.name, 'available': mesh is not None, 'status': status, 'run': run_data, 'trace': trace, 'views': views})
        print(directory.name, 'rendered' if mesh else 'no STEP', flush=True)
    template = ROOT/'scripts/view_report_template.html'
    target = ROOT/'reports/cad-view-comparison.html'
    target.parent.mkdir(exist_ok=True)
    target.write_text(template.read_text().replace('__CASE_DATA__', json.dumps(cases)), encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
