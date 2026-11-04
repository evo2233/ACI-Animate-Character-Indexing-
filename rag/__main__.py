import argparse
import logging
from .config import Config
from .store import build_index, open_store, verify
from .chain import make_chain, answer


def main():
    parser = argparse.ArgumentParser(description='ACI RAG System')
    parser.add_argument('command', choices=['index', 'chat'])
    parser.add_argument('--question', help='单次提问')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    try:
        c = Config()
        if args.command == 'index':
            build_index(c)
            return 0

        verify(c)
        store, chain = open_store(c), make_chain(c)
        if not store.get(limit=1)['ids']:
            raise ValueError('索引为空，请重新执行 index')
        while True:
            question = args.question if args.question is not None else input(
                '\n我是ACG大图书馆的管理员，乐意为您效劳~'
                '\n试着问我些问题吧（exit 退出）> '
            )
            if question.strip().lower() in {'exit'}:
                print('\n期待与您的再会~')
                break
            # if question is empty
            if not question.strip():
                if args.question is not None:
                    raise ValueError('问题不能为空')
                continue

            result, docs = answer(store, chain, question, c.k)
            print(result)
            for i, d in enumerate(docs, 1):
                m = d.metadata
                print(f"[S{i}] {m['source']} 记录#{m['record']} ID={m['character_id']} {m['full_name']} 分块={m['chunk']} {m['url']}")

            if args.question is not None:
                break
        return 0
    except (EOFError, KeyboardInterrupt):
        return 0
    except Exception as e:
        logging.error('%s: %s', type(e).__name__, e)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
