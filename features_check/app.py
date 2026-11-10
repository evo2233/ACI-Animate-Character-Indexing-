"""Local, single-user CSV attribute editor. Run with --help for options."""
import argparse
import csv
import hashlib
import io
import os
from pathlib import Path
import secrets
import tempfile
import threading

from flask import Flask, jsonify, render_template, request

PRESETS = {
    "hair_color": ["黑色", "棕色", "金色", "白色", "银色", "红色", "蓝色", "绿色", "紫色", "粉色", "多色", "无法判断", "不适用"],
    "eye_color": ["黑色", "棕色", "蓝色", "绿色", "红色", "紫色", "金色", "灰色", "异色", "无法判断"],
    "hair_style": ["短发", "中长发", "长发", "单马尾", "双马尾", "辫子", "盘发", "光头", "无法判断"],
}


class CsvStore:
    def __init__(self, path, column, encoding="auto"):
        self.path = Path(path).expanduser().resolve()
        self.column = column.strip()
        if not self.column or self.column in {"img_url", "name_cn", "subject_name_cn"}:
            raise ValueError("请指定有效的属性列，不能使用图片、角色名或动漫名列。")
        self.lock = threading.Lock()
        raw = self.path.read_bytes()
        self.digest = hashlib.sha256(raw).digest()
        self.encoding = encoding
        if encoding == "auto":
            self.encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        try:
            content = raw.decode(self.encoding)
        except UnicodeDecodeError as exc:
            raise ValueError("无法解码 CSV，请使用 --encoding 指定编码，例如 gb18030。") from exc
        try:
            self.dialect = csv.Sniffer().sniff(content[:65536], delimiters=",;\t|")
        except csv.Error:
            self.dialect = csv.excel
        self.newline = "\r\n" if "\r\n" in content else "\n"
        # Sniffer can incorrectly infer doublequote=False from a short sample.
        # Standard CSV escapes a quote inside a quoted field as two quotes.
        reader = csv.DictReader(io.StringIO(content, newline=""), dialect=self.dialect, doublequote=True)
        self.fields = list(reader.fieldnames or [])
        if not self.fields or len(set(self.fields)) != len(self.fields):
            raise ValueError("CSV 表头为空或包含重复列名。")
        missing = {"img_url", "name_cn", "subject_name_cn"} - set(self.fields)
        if missing:
            raise ValueError("CSV 缺少列：" + ", ".join(sorted(missing)))
        self.rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in self.rows):
            raise ValueError("CSV 存在字段数量与表头不一致的记录，请先修正。")
        if self.column not in self.fields:
            similar = [f for f in self.fields if f.strip().casefold() == self.column.casefold()]
            if similar:
                raise ValueError(f"发现相似列名 {similar!r}，请先统一表头。")
            self.fields.append(self.column)
            for row in self.rows:
                row[self.column] = ""
            self._write(self.rows)
        self.revision = 0

    def _write(self, rows):
        def check_original():
            if hashlib.sha256(self.path.read_bytes()).digest() != self.digest:
                raise ValueError("CSV 已被其他程序修改，未覆盖。请重启工具重新加载。")
        check_original()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding=self.encoding, newline="", dir=self.path.parent,
                                             prefix=".features-check-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                writer = csv.DictWriter(handle, fieldnames=self.fields, dialect=self.dialect,
                                        lineterminator=self.newline, doublequote=True)
                writer.writeheader()
                writer.writerows(rows)
                handle.flush()
                os.fsync(handle.fileno())
            new_digest = hashlib.sha256(temporary.read_bytes()).digest()
            check_original()
            os.replace(temporary, self.path)
            self.digest = new_digest
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def snapshot(self):
        with self.lock:
            return {"file": self.path.name, "column": self.column, "revision": self.revision,
                    "rows": [{"index": i + 1, "name": r["name_cn"], "subject": r["subject_name_cn"],
                              "image": r["img_url"], "value": r[self.column]} for i, r in enumerate(self.rows)]}

    def save(self, index, value, revision):
        with self.lock:
            if revision != self.revision:
                raise ValueError("页面数据已过期（可能有另一标签页保存），请刷新后重试。")
            if type(index) is not int or not 1 <= index <= len(self.rows) or not isinstance(value, str):
                raise ValueError("无效的记录序号或属性值。")
            updated = self.rows.copy()
            updated[index - 1] = {**updated[index - 1], self.column: value}
            self._write(updated)
            self.rows = updated
            self.revision += 1
            return self.revision


def create_app(store, options=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
    token = secrets.token_urlsafe(32)

    @app.before_request
    def local_only():
        if request.host.split(":")[0] not in {"127.0.0.1", "localhost"}:
            return jsonify(error="只允许本机访问。"), 403
        if request.method == "POST" and request.headers.get("X-Editor-Token") != token:
            return jsonify(error="请求校验失败，请刷新页面。"), 403

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/")
    def home():
        return render_template("index.html", token=token, options=options if options is not None else PRESETS.get(store.column, []))

    @app.get("/api/data")
    def data():
        return jsonify(store.snapshot())

    @app.post("/api/save")
    def save():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify(error="无效的保存请求。"), 400
        try:
            revision = store.save(payload.get("index"), payload.get("value"), payload.get("revision"))
            return jsonify(revision=revision)
        except ValueError as exc:
            return jsonify(error=str(exc)), 409
        except (OSError, UnicodeError, csv.Error):
            return jsonify(error="写入失败。请关闭占用 CSV 的 Excel 等程序，并检查文件权限后重试。"), 500

    return app


def main():
    parser = argparse.ArgumentParser(description="角色属性 CSV 本地录入工具")
    parser.add_argument("csv", help="CSV 文件路径；保存会直接更新此文件")
    parser.add_argument("--column", required=True, help="目标属性列，例如 hair_color")
    parser.add_argument("--encoding", default="auto", help="默认识别 UTF-8/BOM；其他编码请显式指定")
    parser.add_argument("--options", nargs="*", help="自定义快捷选项，以空格分隔")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    try:
        store = CsvStore(args.csv, args.column, args.encoding)
    except (OSError, ValueError, csv.Error, LookupError) as exc:
        parser.error(str(exc))
    print(f"打开 http://127.0.0.1:{args.port} 进行录入。Ctrl+C 退出。")
    create_app(store, args.options).run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
