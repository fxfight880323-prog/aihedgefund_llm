# -*- coding: utf-8 -*-
"""
全市场数据 → SQLite 迁移脚本（DBBrowser SQLite 可直接打开）
数据源：项目根目录 JSON 缓存（万得全A PIT 成分 + 腾讯月K + 申万金工因子/估值 + 一致预期 + GBM因子）
用法：
  python _db_migrate.py            # 全量重建（GBM 文件存在则一并导入）
  python _db_migrate.py --with-gbm # 仅追加 GBM 因子值（后台拉取完成后用）
输出：data/a_share_market.db
"""
import json, math, os, sqlite3, sys, time

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, 'data', 'a_share_market.db')
GBM_FILE = os.path.join(ROOT, '_bt_gbm_values.json')
INDEX_CODE = '000985.SH'  # 中证全指（_bt_winda_index.json 对应的基准指数）


def _num(v):
    """转 float，NaN/None -> None"""
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def create_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS pit_universe (
        month  TEXT NOT NULL,
        ticker TEXT NOT NULL,
        as_of  TEXT,
        PRIMARY KEY (month, ticker)
    );
    CREATE INDEX IF NOT EXISTS idx_pit_universe_ticker ON pit_universe(ticker);

    CREATE TABLE IF NOT EXISTS monthly_close (
        ticker TEXT NOT NULL,
        month  TEXT NOT NULL,
        close  REAL,
        PRIMARY KEY (ticker, month)
    );
    CREATE INDEX IF NOT EXISTS idx_monthly_close_month ON monthly_close(month);

    CREATE TABLE IF NOT EXISTS index_monthly (
        index_code TEXT NOT NULL,
        month      TEXT NOT NULL,
        close      REAL,
        PRIMARY KEY (index_code, month)
    );

    CREATE TABLE IF NOT EXISTS consensus (
        month         TEXT NOT NULL,
        ticker        TEXT NOT NULL,
        con_date      TEXT,
        con_year      INTEGER,
        con_np        REAL, con_eps REAL, con_pe REAL, con_peg REAL,
        con_roe       REAL, con_np_yoy REAL,
        np_revision_4w REAL, np_revision_13w REAL, np_revision_26w REAL,
        PRIMARY KEY (month, ticker)
    );
    CREATE INDEX IF NOT EXISTS idx_consensus_ticker ON consensus(ticker);

    CREATE TABLE IF NOT EXISTS factor_panel (
        month     TEXT NOT NULL,
        ticker    TEXT NOT NULL,
        date      TEXT,
        gpm       REAL, cetop REAL, npyoy REAL, roes REAL,
        dtop5     REAL, oryoy REAL, lncap REAL,
        PRIMARY KEY (month, ticker)
    );
    CREATE INDEX IF NOT EXISTS idx_factor_panel_ticker ON factor_panel(ticker);

    CREATE TABLE IF NOT EXISTS valuation (
        month         TEXT NOT NULL,
        ticker        TEXT NOT NULL,
        date          TEXT,
        turnover      REAL, free_turnover REAL, free_shares REAL,
        total_mv      REAL, float_mv REAL, pe_ttm REAL, pb REAL,
        PRIMARY KEY (month, ticker)
    );
    CREATE INDEX IF NOT EXISTS idx_valuation_ticker ON valuation(ticker);

    CREATE TABLE IF NOT EXISTS gbm_factor (
        month  TEXT NOT NULL,
        ticker TEXT NOT NULL,
        gbm    REAL,
        PRIMARY KEY (month, ticker)
    );
    CREATE INDEX IF NOT EXISTS idx_gbm_ticker ON gbm_factor(ticker);
    """)


def import_universe(conn, only_gbm=False):
    if only_gbm:
        return 0
    # 万得全A PIT 成分（10 期）
    d = load_json(os.path.join(ROOT, '_bt_winda_universe.json'))
    rows, n = [], 0
    for month, m in d.items():
        as_of = m.get('as_of') if isinstance(m, dict) else None
        members = m.get('members', []) if isinstance(m, dict) else m
        for tk in members:
            rows.append((month, tk, as_of))
            n += 1
    # 最新一期（2026-08，_lx_now 快照）
    now_path = os.path.join(ROOT, '_bt_lx_now_universe.json')
    if os.path.exists(now_path):
        nd = load_json(now_path)
        as_of = nd.get('as_of')
        month = as_of[:7] if as_of else '2026-08'
        for tk in nd.get('members', []):
            rows.append((month, tk, as_of))
            n += 1
    conn.executemany("INSERT OR REPLACE INTO pit_universe VALUES (?,?,?)", rows)
    return n


def import_prices(conn, only_gbm=False):
    if only_gbm:
        return 0
    d = load_json(os.path.join(ROOT, '_bt_winda_prices.json'))
    rows = []
    for tk, months in d.items():
        for month, close in months.items():
            rows.append((tk, month, _num(close)))
    conn.executemany("INSERT OR REPLACE INTO monthly_close VALUES (?,?,?)", rows)

    # 中证全指指数月K
    idx = load_json(os.path.join(ROOT, '_bt_winda_index.json'))
    rows = [(INDEX_CODE, month, _num(v)) for month, v in idx.items()]
    conn.executemany("INSERT OR REPLACE INTO index_monthly VALUES (?,?,?)", rows)
    return len(rows)


def _records(month, d):
    """统一取 {month: {records:[...]}} 的 records"""
    v = d.get(month)
    if isinstance(v, dict) and isinstance(v.get('records'), list):
        return v['records']
    if isinstance(v, list):
        return v
    return []


def import_consensus(conn, only_gbm=False):
    if only_gbm:
        return 0
    rows, seen = [], set()
    # 主源：万得全A 一致预期（10 期）
    d = load_json(os.path.join(ROOT, '_bt_winda_consensus.json'))
    for month in d:
        for r in _records(month, d):
            key = (month, r.get('stock_code'))
            seen.add(key)
            rows.append((
                month, r.get('stock_code'), r.get('con_date'), r.get('con_year'),
                _num(r.get('con_np')), _num(r.get('con_eps')), _num(r.get('con_pe')),
                _num(r.get('con_peg')), _num(r.get('con_roe')), _num(r.get('con_np_yoy')),
                _num(r.get('np_revision_4w')), _num(r.get('np_revision_13w')),
                _num(r.get('np_revision_26w')),
            ))
    # 补充源：C-Score 一致预期（8 期，同 PIT 快照口径）
    cs = load_json(os.path.join(ROOT, '_bt_cscore_consensus.json'))
    for month in cs:
        for r in _records(month, cs):
            key = (month, r.get('stock_code'))
            if key in seen:
                continue
            rows.append((
                month, r.get('stock_code'), r.get('con_date'), r.get('con_year'),
                _num(r.get('con_np')), _num(r.get('con_eps')), _num(r.get('con_pe')),
                _num(r.get('con_peg')), _num(r.get('con_roe')), _num(r.get('con_np_yoy')),
                _num(r.get('np_revision_4w')), _num(r.get('np_revision_13w')),
                _num(r.get('np_revision_26w')),
            ))
    # 最新一期（2026-08）
    now_path = os.path.join(ROOT, '_bt_lx_now_consensus.json')
    if os.path.exists(now_path):
        nd = load_json(now_path)
        as_of = nd.get('as_of')
        month = as_of[:7] if as_of else '2026-08'
        for r in nd.get('records', []):
            rows.append((
                month, r.get('stock_code'), r.get('con_date'), r.get('con_year'),
                _num(r.get('con_np')), _num(r.get('con_eps')), _num(r.get('con_pe')),
                _num(r.get('con_peg')), _num(r.get('con_roe')), _num(r.get('con_np_yoy')),
                _num(r.get('np_revision_4w')), _num(r.get('np_revision_13w')),
                _num(r.get('np_revision_26w')),
            ))
    conn.executemany("INSERT OR REPLACE INTO consensus VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def import_factor_panel(conn, only_gbm=False):
    if only_gbm:
        return 0
    rows = []
    d = load_json(os.path.join(ROOT, '_bt_lx_allA_factors.json'))
    for month in d:
        for r in _records(month, d):
            rows.append((
                month, r.get('stock_code'), r.get('date'),
                _num(r.get('gpm')), _num(r.get('cetop')), _num(r.get('npyoy')),
                _num(r.get('roes')), _num(r.get('dtop5')), _num(r.get('oryoy')),
                _num(r.get('lncap')),
            ))
    now_path = os.path.join(ROOT, '_bt_lx_now_factors.json')
    if os.path.exists(now_path):
        nd = load_json(now_path)
        as_of = nd.get('as_of')
        month = as_of[:7] if as_of else '2026-08'
        for r in nd.get('records', []):
            rows.append((
                month, r.get('stock_code'), r.get('date'),
                _num(r.get('gpm')), _num(r.get('cetop')), _num(r.get('npyoy')),
                _num(r.get('roes')), _num(r.get('dtop5')), _num(r.get('oryoy')),
                _num(r.get('lncap')),
            ))
    conn.executemany("INSERT OR REPLACE INTO factor_panel VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def import_valuation(conn, only_gbm=False):
    if only_gbm:
        return 0
    rows = []
    d = load_json(os.path.join(ROOT, '_bt_lx_allA_valuation.json'))
    for month in d:
        for r in _records(month, d):
            rows.append((
                month, r.get('stock_code'), r.get('date'),
                _num(r.get('turnover')), _num(r.get('free_turnover')),
                _num(r.get('free_shares')), _num(r.get('total_mv')),
                _num(r.get('float_mv')), _num(r.get('pe_ttm')), _num(r.get('pb')),
            ))
    now_path = os.path.join(ROOT, '_bt_lx_now_valuation.json')
    if os.path.exists(now_path):
        nd = load_json(now_path)
        as_of = nd.get('as_of')
        month = as_of[:7] if as_of else '2026-08'
        for r in nd.get('records', []):
            rows.append((
                month, r.get('stock_code'), r.get('date'),
                _num(r.get('turnover')), _num(r.get('free_turnover')),
                _num(r.get('free_shares')), _num(r.get('total_mv')),
                _num(r.get('float_mv')), _num(r.get('pe_ttm')), _num(r.get('pb')),
            ))
    conn.executemany("INSERT OR REPLACE INTO valuation VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def import_gbm(conn):
    if not os.path.exists(GBM_FILE):
        return 0
    d = load_json(GBM_FILE)
    rows = []
    for month, m in d.items():
        for tk, v in m.items():
            rows.append((month, tk, _num(v)))
    conn.executemany("INSERT OR REPLACE INTO gbm_factor VALUES (?,?,?)", rows)
    return len(rows)


def main():
    only_gbm = '--with-gbm' in sys.argv
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    t0 = time.time()
    create_tables(conn)
    if not only_gbm:
        # 全量模式：先清空重建，保证与 JSON 源一致
        for t in ['pit_universe', 'monthly_close', 'index_monthly',
                  'consensus', 'factor_panel', 'valuation', 'gbm_factor']:
            conn.execute(f'DELETE FROM {t}')
        conn.commit()

    stats = {}
    stats['pit_universe'] = import_universe(conn, only_gbm)
    stats['monthly_close'] = import_prices(conn, only_gbm)
    stats['index_monthly'] = 0  # 与 prices 同源，见 import_prices
    stats['consensus'] = import_consensus(conn, only_gbm)
    stats['factor_panel'] = import_factor_panel(conn, only_gbm)
    stats['valuation'] = import_valuation(conn, only_gbm)
    stats['gbm_factor'] = import_gbm(conn)
    conn.commit()

    print(f'DB: {DB_PATH}')
    print(f'耗时: {time.time()-t0:.1f}s')
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    for (t,) in cur.fetchall():
        n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'  {t:16s} {n:>8,} 行')
    # 各表时点覆盖
    print('\n各表月份覆盖:')
    for t in ['pit_universe', 'factor_panel', 'valuation', 'consensus', 'gbm_factor']:
        rows = conn.execute(f'SELECT DISTINCT month FROM {t} ORDER BY month').fetchall()
        print(f'  {t:16s} {[r[0] for r in rows]}')
    conn.close()


if __name__ == '__main__':
    main()
