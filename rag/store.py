import hashlib
import json
import logging
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from chromadb.config import Settings
from .data import load_documents


def signature(c):
    return {'embedding': c.embedding, 'url': c.url, 'chunk': c.chunk, 'overlap': c.overlap, 'schema': 1}


def manifest(c):
    """
    :param c: 索引配置实例
    :return: 索引相关配置 json 文件的路径
    """
    return c.db / (c.collection + '.manifest.json')


def open_store(c, embeddings=None):
    return Chroma(collection_name=c.collection, persist_directory=str(c.db),
                  embedding_function=embeddings or OllamaEmbeddings(model=c.embedding, base_url=c.url, client_kwargs={'timeout': c.timeout}),
                  client_settings=Settings(anonymized_telemetry=False))


def verify(c, require_ready=True):
    p = manifest(c)
    if not p.exists():
        raise ValueError('索引未就绪，请先运行 python -m rag index')
    if json.loads(p.read_text(encoding='utf-8')) != signature(c):
        raise ValueError('索引配置变化，请设置新的 CHROMA_COLLECTION 后重新导入')
    if require_ready and not p.with_suffix('.ready').exists():
        raise ValueError('索引导入未完成，请重新执行 index')


def build_index(c, embeddings=None):
    docs = load_documents(c)
    p = manifest(c)
    if p.exists():
        verify(c, require_ready=False)
    store = open_store(c, embeddings)
    if not p.exists() and store.get(limit=1)['ids']:
        raise ValueError('集合缺少配置清单，请使用新的 CHROMA_COLLECTION')
    c.db.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(signature(c)), encoding='utf-8')
    # remove 'ready' flag of indexing
    p.with_suffix('.ready').unlink(missing_ok=True)

    desired = {}
    for d in docs:
        # hash key is 'ids'
        key = hashlib.sha256(json.dumps([d.page_content, d.metadata], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        desired[key] = d

    # remove duplicates
    existing = set(store.get()['ids'])
    pending = sorted(set(desired) - existing)

    # write into DB in batch(different from doc's chunk)
    for offset in range(0, len(pending), 32):
        batch = pending[offset:offset+32]
        store.add_documents([desired[k] for k in batch], ids=batch)
        logging.info('已写入 %s/%s 个新分块', min(offset+32, len(pending)), len(pending))

    # remove deleted items
    stale = sorted(existing - set(desired))
    if stale:
        store.delete(ids=stale)

    # mark 'ready' again
    p.with_suffix('.ready').touch()
    logging.info('索引完成: 总计 %s，新增 %s，移除旧分块 %s', len(desired), len(pending), len(stale))
    return len(desired), len(pending), len(stale)
