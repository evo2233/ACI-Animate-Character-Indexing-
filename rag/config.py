import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    def __init__(self):
        load_dotenv(ROOT / '.env')
        self.csv = self.path('CSV_PATH', 'data.csv')
        self.db = self.path('CHROMA_PATH', '.chroma')
        self.url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.embedding = os.getenv('EMBEDDING_MODEL', '')
        self.model = os.getenv('CHAT_MODEL', '')
        self.collection = os.getenv('CHROMA_COLLECTION', 'characters')
        self.k = int(os.getenv('TOP_K', '5'))  # 返回相关的文本块数 ≥ 1
        self.chunk = int(os.getenv('CHUNK_SIZE', '1800'))  # 每块字符数
        self.overlap = int(os.getenv('CHUNK_OVERLAP', '200'))  # 相邻块重复字符数
        self.timeout = float(os.getenv('OLLAMA_TIMEOUT', '120'))
        if self.k < 1 or not 0 <= self.overlap < self.chunk:
            raise ValueError('TOP_K 必须为正数，且 0 <= CHUNK_OVERLAP < CHUNK_SIZE')

    @staticmethod
    def path(key, default):
        p = Path(os.getenv(key, default))
        return p if p.is_absolute() else ROOT / p
