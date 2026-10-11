"""Read-only legacy inventory. Never infer payer or convert saved amounts."""
import argparse
import json
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.config import get_settings
from app.ledger.service import history_inventory


def main():
    parser=argparse.ArgumentParser(description='历史费用只读盘点（不迁入、不写账）')
    parser.add_argument('--output',type=Path,help='可选：将盘点 JSON 保存到指定文件')
    args=parser.parse_args()
    engine=create_engine(get_settings().database_url)
    with Session(engine) as db:
        if engine.dialect.name=='postgresql': db.execute(text('SET TRANSACTION READ ONLY'))
        data=history_inventory(db)
    content=json.dumps(data,ensure_ascii=False,indent=2)
    if args.output: args.output.write_text(content,encoding='utf-8')
    else: print(content)
    engine.dispose()


if __name__=='__main__': main()
