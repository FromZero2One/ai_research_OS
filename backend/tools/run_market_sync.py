"""手动触发每日行情刷新（验证用）。"""
import asyncio
import json

from core.market_sync import market_data_update

print(json.dumps(asyncio.run(market_data_update()), ensure_ascii=False))
