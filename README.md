# 本地 CSV RAG 问答

Python + LangChain LCEL + 官方 Ollama/Chroma 集成。数据导入和问答完全分离，无 Web 服务或多 Agent。

## 数据与架构

原始 `data.csv` 保持不变：212 条动漫人物记录，字段为 character_id、full_name、alternate_name、name、url、attributes、description。ID 按字符串保留；名称、URL 和描述为文本；attributes 是 JSON 属性数组，转换为“属性名: 值”。最长描述 8186 字符，因此短记录不切分，长记录按约 1800 字符及 200 字符重叠切分，在空格处优先断开；每块附人物 ID 和各种名称。当前生成 268 个 Document。

metadata 包含原始 ID、名称、别名、URL、CSV 文件名、从 1 开始的数据记录序号、物理结束行号和块序号。CSV 可含字段内换行，因此记录序号不等同于文本文件行号。

导入：CSV → Document → nomic-embed-text → 持久化 Chroma。
问答：问题 → 同模型语义检索 → 带来源的上下文 → DeepSeek → 回答与检索来源列表。

使用内容与 metadata 的 SHA256 作为向量 ID；重复导入跳过已有块，成功插入后清理旧块。中断后可以重试，未完成索引禁止问答。配置清单防止混用不同 embedding/分块配置。不要同时运行多个导入进程，导入期间不要运行问答。模型同名但权重变更时也应使用新集合。

## 目录

```text
rag/config.py       环境配置
rag/data.py         CSV 与 Document 转换
rag/store.py        embedding、索引与持久化
rag/retrieval.py    Retriever
rag/chain.py        提示模板与 LCEL
rag/__main__.py     CLI
.env                配置路由
requirements.txt   最新稳定 SDK 依赖]
```

## 运行（PowerShell）

创建 `.env` 文件，并对照 `rag\config.py` 填入所有路由。创建、打开本项目的 conda 环境。

```powershell
# 审阅依赖变更后再执行；本次实现没有升级现有环境
python -m pip install --dry-run -r requirements.txt
python -m pip install -r requirements.txt
ollama serve
```

Ollama 服务默认 http://localhost:11434，可用 OLLAMA_BASE_URL 修改。

```powershell
python -m rag index
python -m rag chat
python -m rag chat --question "What is Rukia Kuchiki's birthday?"
```

输入 exit 或 Ctrl+C 退出。相对路径均相对于项目根目录；Chroma 自动落盘，无需调用已废弃的 persist()。第二次 index 应显示新增 0。问答直接打开已有数据库，不重新嵌入整个 CSV。

## Bangumi 角色采集（bangumi_lu）

从当前用户的动画收藏中采集主角和配角，输出角色 ID、性别、所属作品、名称、简介及图片链接。

在 `bangumi_lu/.env` 中配置 `BANGUMI_TOKEN=你的访问令牌`，安装上述依赖后，在项目根目录运行：

```powershell
# 全部动画收藏（默认）
python -m bangumi_lu
# 仅采集「在看」作品
python -m bangumi_lu --type 3
```

- `--type` 可选值：`1` 想看、`2` 看过、`3` 在看、`4` 搁置、`5` 抛弃；不传时查询全部收藏。
- 筛选仅影响本次查询；不同状态共用断点和 CSV，CSV 保留所有已采集作品的角色。
- 输出：`data/character.csv`，UTF-8 BOM 编码，含表头；同一角色在不同作品中分别保留记录。
- 断点：`data/character_checkpoints/{subject_id}.json`。每完成一部作品先保存断点，再追加 CSV；启动时从断点重建一次 CSV，恢复中断的写入。
- 请求遇到网络异常、429 或服务器错误时最多尝试 4 次；单部作品抓取失败后继续处理其他作品，重新运行即可补抓。
- 请保留断点目录，且不要同时运行多个采集进程。已完成作品不会自动刷新；需要更新时删除对应 JSON 后重新运行。CSV 中的手动修改会在下次重建时被覆盖。

## 配置和常见问题

- 连接拒绝：启动 Ollama，检查端口与 OLLAMA_BASE_URL；模型不存在：核对 ollama list 中的完整标签。
- 更换 embedding 或分块参数：设置新的 CHROMA_COLLECTION，重新 index。不要手工混用旧向量。
- 更新 CSV 后重新 index；问答不会自动检测或导入 CSV 修改。
- 标准语义召回总会返回近邻，并不保证有足够证据。提示词要求资料不足时拒答，但仍须人工检查引用。来源列表是检索依据，不表示模型逐项使用了所有片段。此系统不适合全表统计；英文数据对中文问句的召回质量需实际评估。

官方参考：[LangChain 集成](https://reference.langchain.com/python/integrations/overview)、[Ollama API](https://reference.langchain.com/python/langchain-ollama/langchain_ollama)、[Chroma 集成](https://cookbook.chromadb.dev/integrations/langchain/)、[PyPI LangChain](https://pypi.org/project/langchain/)。
