"""ai_fund_framework 统一数据管线编排包。

用法（根目录）:
    python run.py daily       # 模拟组合每日净值（LX-top40 + Q20·质衡优选）
    python run.py screen      # 数据刷新 + 三轨名单（主轨/KFIN轨/q20）
    python run.py backtest    # 权威回测集重跑
    python run.py all         # screen + backtest + daily 全流程
    python run.py status      # 数据新鲜度体检
    python run.py --list      # 预览所有步骤
"""
