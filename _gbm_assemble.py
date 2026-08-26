# -*- coding: utf-8 -*-
"""汇总 _gbm_batches/*_res.json 为 _bt_gbm_values.json 并生成覆盖率报告。
用法: python _gbm_assemble.py [--check] [--verbose]
--check: 只校验已完成的批次结果与批次文件 ts_codes 是否匹配，不写最终文件。
"""
import json, os, sys, glob, time

BASE = os.path.dirname(os.path.abspath(__file__))
BATCH_DIR = os.path.join(BASE, '_gbm_batches')
UNIVERSE = os.path.join(BASE, '_bt_winda_universe.json')
OUT = os.path.join(BASE, '_bt_gbm_values.json')

def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    check_only = '--check' in sys.argv
    verbose = '--verbose' in sys.argv
    t0 = time.time()

    uni = load(UNIVERSE)
    with open(os.path.join(BATCH_DIR, 'manifest.json'), 'r', encoding='utf-8') as f:
        manifest = load(os.path.join(BATCH_DIR, 'manifest.json'))

    result = {}          # month -> {ticker: value}
    summary = {}         # month -> stats
    total_requested = 0
    total_found = 0
    total_missing = 0
    n_batches_done = 0
    n_batches_total = 0
    problems = []

    for month, info in manifest.items():
        n_members = info['n_members']
        n_batches_total += info['n_batches']
        month_result = {}
        month_found = 0
        month_missing = []
        for bname in info['batches']:
            bpath = os.path.join(BATCH_DIR, bname + '.json')
            rpath = os.path.join(BATCH_DIR, bname + '_res.json')
            if not os.path.exists(rpath):
                if not check_only:
                    problems.append(f'缺少结果文件: {bname}')
                continue
            n_batches_done += 1
            b = load(bpath)
            try:
                res = load(rpath)
            except Exception as e:
                problems.append(f'结果文件解析失败: {bname}: {e}')
                continue
            # res 有两种格式: {ts_code: value} 或 records 数组
            if isinstance(res, list):
                mapping = {r['ts_code']: r['GBM量价'] for r in res}
            elif isinstance(res, dict):
                mapping = res
            else:
                problems.append(f'结果格式异常: {bname}')
                continue
            # 校验: 结果中的 key 必须都在批次的 ts_codes 里
            batch_codes = set(b['ts_codes'])
            res_codes = set(mapping.keys())
            extra = res_codes - batch_codes
            if extra:
                problems.append(f'{bname}: 结果出现批次外的代码 {sorted(extra)[:5]}')
            for tk in b['ts_codes']:
                if tk in mapping:
                    month_result[tk] = mapping[tk]
                    month_found += 1
                else:
                    month_missing.append(tk)
        month_missing_n = len(month_missing)
        total_requested += n_members
        total_found += month_found
        total_missing += month_missing_n
        summary[month] = {
            'n_members': n_members,
            'n_batches_total': info['n_batches'],
            'n_batches_done': sum(1 for bn in info['batches'] if os.path.exists(os.path.join(BATCH_DIR, bn + '_res.json'))),
            'n_found': month_found,
            'n_missing': month_missing_n,
            'coverage': round(month_found / n_members * 100, 2) if n_members else 0.0,
            'missing_sample': month_missing[:10],
        }
        result[month] = month_result

    print('=' * 70)
    print(f"{'月份':<10}{'成分数':>8}{'有值数':>8}{'覆盖率':>9}{'缺失数':>8}  缺失样例")
    for month in manifest:
        s = summary[month]
        print(f"{month:<10}{s['n_members']:>8}{s['n_found']:>8}{s['coverage']:>8.2f}%{s['n_missing']:>8}  {s['missing_sample'][:5]}")
    print('=' * 70)
    print(f"批次: {n_batches_done}/{n_batches_total}  请求对: {total_requested}  有值: {total_found}  缺失: {total_missing}")
    if problems:
        print(f"\n问题数: {len(problems)}")
        for p in problems[:40]:
            print('  ', p)
    else:
        print('\n无一致性问题')
    print(f"耗时: {time.time()-t0:.1f}s")

    if not check_only and n_batches_done == n_batches_total and not problems:
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
        print(f'\n已写入 {OUT}')
    elif not check_only:
        print('\n未写入: 仍有批次未完成或存在一致性问题')

if __name__ == '__main__':
    main()
