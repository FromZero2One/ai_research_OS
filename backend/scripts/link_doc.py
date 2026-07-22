"""Link Bank of China document to its company record."""
import asyncio, asyncpg

async def link():
    conn = await asyncpg.connect('postgresql://airesearch:airesearch_dev@localhost:5432/airesearch')
    r = await conn.execute(
        "UPDATE document.documents SET company_id = '23eefcac-720f-4d60-a8c7-bb107d34451b' WHERE title LIKE '%中国银行%'"
    )
    print(f'Done: {r}')
    await conn.close()

asyncio.run(link())
