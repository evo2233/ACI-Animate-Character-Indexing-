import csv
import json
from langchain_core.documents import Document


def load_documents(config):
    documents = []
    with config.csv.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        required = {'character_id', 'full_name', 'alternate_name', 'name', 'url', 'attributes', 'description'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f'CSV 缺少字段: {required - set(reader.fieldnames or [])}')

        for record, row in enumerate(reader, 1):
            if None in row or any(v is None for v in row.values()):
                # 允许空值，但不允许缺列或多列
                raise ValueError(f'CSV 记录 {record} 列数不正确')
            try:
                # remove "name"&"value" format
                attrs = json.loads(row['attributes'] or '[]')
                attributes = '\n'.join(f"{a['name']}: {a['value']}" for a in attrs)
            except (ValueError, TypeError, KeyError) as e:
                raise ValueError(f'记录 {record} attributes 不是有效的属性数组') from e
            identity = '\n'.join(f'{k}: {row[k]}' for k in ['character_id', 'full_name', 'alternate_name', 'name'])
            body = f"Attributes:\n{attributes}\nDescription:\n{row['description']}"

            # Short records stay intact. Long records overlap; every chunk carries identity.
            start, chunk = 0, 0
            while start < len(body):
                end = min(start + config.chunk, len(body))
                if end < len(body):
                    # 尝试让 end 往前落在词语边界附近
                    boundary = body.rfind(' ', start + config.chunk // 2, end)
                    if boundary > start:
                        end = boundary
                # each chunk will have its character's metadata
                metadata = {k: row[k] for k in ['character_id', 'full_name', 'alternate_name', 'url']}
                metadata.update(source=config.csv.name, record=record, csv_line_end=reader.line_num, chunk=chunk)
                documents.append(Document(page_content=identity+'\n'+body[start:end], metadata=metadata))

                if end == len(body):
                    break
                start = max(start + 1, end - config.overlap)
                chunk += 1
    if not documents:
        raise ValueError('CSV 没有数据')
    return documents
