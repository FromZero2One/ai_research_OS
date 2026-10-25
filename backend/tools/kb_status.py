"""知识库（文档中心）状态：文档数 / 已索引 / 切片数 / 逐文档明细。"""
import psycopg2

c = psycopg2.connect(host="localhost", port=5432, dbname="airesearch",
                     user="airesearch", password="airesearch_dev")
cur = c.cursor()
cur.execute("""
    SELECT count(*), count(*) FILTER (WHERE is_indexed), coalesce(sum(chunk_count), 0)
    FROM document.documents
""")
total, indexed, chunks = cur.fetchone()
print(f"文档: {total} 份，已索引: {indexed} 份，切片总数: {chunks}")

cur.execute("""
    SELECT d.title, c.ticker, d.chunk_count, d.is_indexed
    FROM document.documents d
    LEFT JOIN company.companies c ON c.id = d.company_id
    ORDER BY d.created_at
""")
for title, ticker, n, ok in cur.fetchall():
    print(f"  {ticker or '-':8} {str(n or 0):5} 切片  indexed={ok}  {title}")
c.close()
