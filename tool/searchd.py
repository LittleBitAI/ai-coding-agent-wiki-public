"""searchd — the search daemon. One per machine, started by the hook.

Chunks every page at its `##`/`###` headings and ranks them two ways — BM25
over English words and Hangul bigrams, and cosine over a local
`multilingual-e5-small` — merged by reciprocal rank. The regex triggers stay
the authority; the hook only adds a line for what they missed.

The four questions of `craft/client-lifecycle-in-one-scope`:

- Creation. `search.spawn`, from the hook, when no answer came. Binding the
  fixed port is the lock: a second one fails to bind and exits.
- Sharing. One process on the machine. A request names its repository and
  each repository gets its own index; the model is loaded once.
- Closing. Three hours after the last request it ends itself. `/quit` only
  with the token. The state file is removed on the way out.
- Ownership. The user's. `~/.cache/ai-coding-agent-wiki/searchd.json` holds
  `port`, `token`, `pid`, `version`. A daemon that died leaving the file is
  found by the next hook failing to connect, and a new one is started.

Without `onnxruntime`, `tokenizers` and `numpy` it answers with BM25 alone,
and it does the same while the model downloads (about 120 MB, first start).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import queue
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from search import PORT, cache_dir, proof, state_path, version  # noqa: E402
from wikilib import WIKI, front_matter  # noqa: E402

# The version this process runs, read once. Read per request it would follow
# the file on disk and a pulled daemon would never be told it is stale.
RUNNING = version()
IDLE = 3 * 3600
RRF_K = 60
INJECTABLE = {"landmine", "contract"}

MODEL = "intfloat/multilingual-e5-small"
FILES = {"model.onnx": "onnx/model_qint8_avx512_vnni.onnx", "tokenizer.json": "onnx/tokenizer.json"}
# In every vector's cache key, so another model or file never reads these.
MODEL_ID = f"{MODEL}/{FILES['model.onnx']}"

HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
WORD = re.compile(r"[a-z0-9_]+|[가-힣]+")


def terms(text: str) -> list[str]:
    """English words in lower case, Hangul as overlapping bigrams.

    Both, because the query is the utterance and its English rendering, and
    the hub's pages are English while a repository's are Korean. Bigrams
    catch a Korean stem through its endings without a morphological analyser.
    """

    out = []
    for word in WORD.findall(text.lower()):
        if "가" <= word[0] <= "힣":
            out += [word[i:i + 2] for i in range(len(word) - 1)] or [word]
        else:
            out.append(word)
    return out


def chunks(text: str, path: Path) -> list[dict]:
    """A page cut at `##` and `###`. Each chunk knows its first line.

    The page title and the heading path go in front of what is indexed — the
    cheap form of contextual retrieval, no model call. A heading inside a
    code fence is not a heading.
    """

    _meta, body = front_matter(text)
    offset = text[: len(text) - len(body)].count("\n")
    lines = body.splitlines()
    title = next((x[2:].strip() for x in lines if x.startswith("# ")), path.stem)
    found, trail, start, buf, fence = [], [], offset + 1, [], False

    def flush() -> None:
        # A heading with nothing under it before the next one is not a chunk.
        if "".join(buf[1:] if trail else buf).strip():
            heading = " > ".join([title, *trail])
            found.append({"path": str(path), "line": start, "heading": heading,
                          "text": "\n".join(buf), "indexed": heading + "\n" + "\n".join(buf)})

    for number, line in enumerate(lines, offset + 1):
        if line.startswith(("```", "~~~")):
            fence = not fence
        match = None if fence else HEADING.match(line)
        if match and len(match.group(1)) >= 2:
            flush()
            trail = trail[: len(match.group(1)) - 2] + [match.group(2)]
            start, buf = number, [line]
            continue
        buf.append(line)
    flush()
    return found


def listing(project: Path | None, pool: str) -> list[Path]:
    """The files a pool reads.

    `hook`: the hub's rules and the repository's `.wiki/*.md` — decision
    records stay out, and `Pool.refresh` keeps only pages with an injectable
    severity: those are the pages the recall labels can judge. `chat`: every hub rule and every Markdown file
    the repository keeps, as git sees it, so `node_modules` and the like never
    come in.
    """

    files = [p for scope in ("operator", "craft") for p in sorted((WIKI / scope).glob("*.md"))]
    if project is None:
        return files
    if pool == "hook":
        return files + sorted((project / ".wiki").glob("*.md"))
    try:
        out = subprocess.run(
            ["git", "-C", str(project), "ls-files", "-co", "--exclude-standard", "-z", "--", "*.md"],
            capture_output=True, timeout=30, check=True).stdout.decode("utf-8", errors="replace")
        mine = [project / name for name in out.split("\0") if name]
    except (OSError, subprocess.SubprocessError):
        mine = [p for p in project.rglob("*.md")
                if not any(part.startswith(".") or part == "node_modules"
                           for part in p.relative_to(project).parts[:-1])]
    seen = {p.resolve() for p in files}
    return files + [p for p in mine if p.resolve() not in seen]


def injectable(text: str) -> bool:
    meta, _body = front_matter(text)
    return str(meta.get("severity") or "") in INJECTABLE


class Embedder:
    """The model, loaded once, and a worker that fills the vector cache.

    Off for good when the libraries are missing or the download fails; the
    daemon then ranks with BM25 alone. Only the worker thread touches SQLite.
    """

    def __init__(self, root: Path | None):
        self.root = root
        self.state = "off" if root is None else "loading"
        self.vectors: dict[str, object] = {}
        self.pending: set[str] = set()
        self.jobs: queue.Queue = queue.Queue()

    def start(self) -> None:
        if self.root is not None:
            threading.Thread(target=self.run, daemon=True).start()

    def run(self) -> None:
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer

            folder = self.root / "models/e5"
            for name, remote in FILES.items():
                if not (folder / name).exists():
                    folder.mkdir(parents=True, exist_ok=True)
                    part = folder / (name + ".part")
                    urllib.request.urlretrieve(f"https://huggingface.co/{MODEL}/resolve/main/{remote}", part)
                    part.replace(folder / name)
            self.np = np
            self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
            self.tokenizer.enable_truncation(512)
            options = ort.SessionOptions()
            # Two threads: this runs beside the session it serves.
            options.intra_op_num_threads = 2
            options.enable_cpu_mem_arena = False
            self.session = ort.InferenceSession(str(folder / "model.onnx"), options,
                                                providers=["CPUExecutionProvider"])
            db = sqlite3.connect(self.root / "vectors.sqlite3")
            db.execute("CREATE TABLE IF NOT EXISTS v (k TEXT PRIMARY KEY, v BLOB)")
            for key, blob in db.execute("SELECT k, v FROM v"):
                self.vectors[key] = np.frombuffer(blob, dtype=np.float32)
            self.state = "ready"
        except Exception as error:  # noqa: BLE001
            self.state = "off"
            print(f"vectors off: {type(error).__name__}", file=sys.stderr)
            return
        while True:
            batch = [self.jobs.get()]
            while len(batch) < 8 and not self.jobs.empty():
                batch.append(self.jobs.get())
            try:
                done = self.encode([text for _key, text in batch], "passage: ")
            except Exception as error:  # noqa: BLE001
                print(f"embedding skipped: {type(error).__name__}", file=sys.stderr)
                continue
            for (key, _text), vector in zip(batch, done):
                self.vectors[key] = vector
                db.execute("INSERT OR REPLACE INTO v VALUES (?, ?)", (key, vector.tobytes()))
                self.pending.discard(key)
            db.commit()

    def encode(self, texts: list[str], prefix: str):
        """e5's convention: `passage: ` and `query: `, mean pooling, unit length."""

        np = self.np
        encoded = self.tokenizer.encode_batch([prefix + t for t in texts])
        width = max(len(e.ids) for e in encoded)
        ids = np.array([e.ids + [1] * (width - len(e.ids)) for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask + [0] * (width - len(e.ids)) for e in encoded], dtype=np.int64)
        hidden = self.session.run(None, {"input_ids": ids, "attention_mask": mask,
                                         "token_type_ids": np.zeros_like(ids)})[0]
        pooled = (hidden * mask[..., None]).sum(1) / mask.sum(1, keepdims=True)
        return (pooled / np.linalg.norm(pooled, axis=1, keepdims=True)).astype(np.float32)

    def want(self, items: list[tuple[str, str]]) -> None:
        if self.state == "off":
            return
        for key, text in items:
            if key not in self.vectors and key not in self.pending:
                self.pending.add(key)
                self.jobs.put((key, text))


def key_of(text: str) -> str:
    return hashlib.sha256((MODEL_ID + "\0" + text).encode("utf-8")).hexdigest()


class Pool:
    """One repository's index for one pool. Re-cut only the files whose
    modification time moved; re-embed only the chunks whose text changed."""

    def __init__(self, project: Path | None, kind: str, embedder: Embedder):
        self.project, self.kind, self.embedder = project, kind, embedder
        self.files: dict[Path, tuple[int, list[dict]]] = {}
        self.chunks: list[dict] = []
        self.matrix = None

    def refresh(self) -> None:
        changed = False
        now = {}
        for path in listing(self.project, self.kind):
            try:
                now[path] = path.stat().st_mtime_ns
            except OSError:
                continue
        for path in list(self.files):
            if path not in now:
                del self.files[path]
                changed = True
        for path, stamp in now.items():
            if path in self.files and self.files[path][0] == stamp:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            keep = self.kind != "hook" or injectable(text)
            self.files[path] = (stamp, chunks(text, path) if keep else [])
            changed = True
        if not changed and self.chunks:
            return
        self.chunks = [c for _stamp, cs in self.files.values() for c in cs]
        for chunk in self.chunks:
            chunk["key"] = key_of(chunk["indexed"])
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths = []
        for i, chunk in enumerate(self.chunks):
            counts = Counter(terms(chunk["indexed"]))
            self.lengths.append(sum(counts.values()))
            for term, n in counts.items():
                self.postings[term].append((i, n))
        self.average = sum(self.lengths) / max(1, len(self.lengths))
        self.matrix = None
        self.embedder.want([(c["key"], c["indexed"]) for c in self.chunks])

    def complete(self) -> bool:
        return self.embedder.state == "ready" and all(
            c["key"] in self.embedder.vectors for c in self.chunks)

    def bm25(self, query: str) -> dict[int, float]:
        k1, b, total = 1.5, 0.75, len(self.chunks)
        scores: dict[int, float] = defaultdict(float)
        for term in set(terms(query)):
            posting = self.postings.get(term, ())
            if not posting:
                continue
            idf = math.log(1 + (total - len(posting) + 0.5) / (len(posting) + 0.5))
            for i, n in posting:
                norm = n + k1 * (1 - b + b * self.lengths[i] / self.average)
                scores[i] += idf * n * (k1 + 1) / norm
        return scores

    def search(self, query: str, k: int) -> list[dict]:
        """Pages, best first. A page scores as its best chunk.

        `rrf` merges the two rankings; `cos` is the best chunk's cosine, or
        `None` while the vectors are incomplete — then the ranking is BM25
        alone, since a vector ranking over part of the pool would favour
        whatever happened to be embedded first.
        """

        lexical = self.bm25(query)
        fused: dict[int, float] = defaultdict(float)
        for rank, i in enumerate(sorted(lexical, key=lexical.get, reverse=True)):
            fused[i] += 1 / (RRF_K + rank + 1)
        cosine = None
        if self.chunks and self.complete():
            np = self.embedder.np
            if self.matrix is None:
                self.matrix = np.stack([self.embedder.vectors[c["key"]] for c in self.chunks])
            cosine = self.matrix @ self.embedder.encode([query], "query: ")[0]
            for rank, i in enumerate(np.argsort(-cosine)):
                fused[int(i)] += 1 / (RRF_K + rank + 1)
        best: dict[str, tuple[float, int]] = {}
        for i, score in fused.items():
            path = self.chunks[i]["path"]
            if path not in best or score > best[path][0]:
                best[path] = (score, i)
        pages = []
        for path, (score, i) in sorted(best.items(), key=lambda x: -x[1][0])[:k]:
            chunk = self.chunks[i]
            top = None
            if cosine is not None:
                top = max(float(cosine[j]) for j, c in enumerate(self.chunks) if c["path"] == path)
            pages.append({"path": path, "line": chunk["line"], "heading": chunk["heading"],
                          "text": chunk["text"], "rrf": round(score, 5),
                          "cos": None if top is None else round(top, 4),
                          "bm25": round(lexical.get(i, 0.0), 3)})
        return pages


class Daemon:
    def __init__(self, token: str, embedder: Embedder):
        self.token, self.embedder = token, embedder
        self.pools: dict[tuple[str, str], Pool] = {}
        # ponytail: one lock for every pool; per-pool locks if requests ever queue
        self.lock = threading.Lock()
        self.last = time.monotonic()

    def search(self, query: str, project: str | None, pool: str, k: int, wait: float) -> list[dict]:
        root = Path(project).resolve() if project else None
        with self.lock:
            index = self.pools.setdefault((str(root), pool), Pool(root, pool, self.embedder))
            index.refresh()
        until = time.monotonic() + wait
        while not index.complete() and self.embedder.state != "off" and time.monotonic() < until:
            time.sleep(0.2)
        with self.lock:
            return index.search(query, k)


def handler(daemon: Daemon, server_ref: list) -> type:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args) -> None:
            pass

        def reply(self, status: int, data: dict) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def allowed(self) -> bool:
            return hmac.compare_digest(self.headers.get("X-Wiki-Token", ""), daemon.token)

        def do_GET(self) -> None:
            daemon.last = time.monotonic()
            if self.path != "/health":
                return self.reply(404, {})
            nonce = self.headers.get("X-Wiki-Nonce", "")
            self.reply(200, {"version": RUNNING, "proof": proof(daemon.token, nonce),
                             "vectors": daemon.embedder.state})

        def do_POST(self) -> None:
            daemon.last = time.monotonic()
            data = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if not self.allowed():
                return self.reply(403, {})
            if self.path == "/quit":
                self.reply(200, {})
                threading.Thread(target=server_ref[0].shutdown, daemon=True).start()
                return None
            if self.path != "/search":
                return self.reply(404, {})
            try:
                ask = json.loads(data)
                results = daemon.search(str(ask["query"]), ask.get("project"), str(ask.get("pool") or "hook"),
                                        int(ask.get("k") or 8), float(ask.get("wait") or 0))
            except Exception as error:  # noqa: BLE001
                return self.reply(400, {"error": type(error).__name__})
            return self.reply(200, {"results": results})

    return Handler


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second socket bind a port already bound,
    # and binding is this daemon's only lock.
    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True


def serve(port: int, daemon: Daemon, tries: int = 1) -> Server | None:
    """Bind, or `None` when another holds the port. A few tries, because a
    daemon replaced for its version is still letting go of the port."""

    ref: list = []
    for attempt in range(tries):
        try:
            server = Server(("127.0.0.1", port), handler(daemon, ref))
            ref.append(server)
            return server
        except OSError:
            if attempt + 1 < tries:
                time.sleep(0.2)
    return None


def main() -> int:
    # Detached, its streams are the null device — but pinned like every tool.
    sys.stdout.reconfigure(encoding="utf-8")
    token = secrets.token_hex(16)
    embedder = Embedder(cache_dir())
    daemon = Daemon(token, embedder)
    server = serve(PORT, daemon, tries=15)
    if server is None:
        return 0
    state = state_path()
    state.parent.mkdir(parents=True, exist_ok=True)
    temporary = state.with_suffix(".tmp")
    temporary.write_text(json.dumps({"port": PORT, "token": token, "pid": os.getpid(),
                                     "version": RUNNING}), encoding="utf-8")
    temporary.replace(state)
    embedder.start()

    def idle() -> None:
        while time.monotonic() - daemon.last < IDLE:
            time.sleep(60)
        server.shutdown()

    threading.Thread(target=idle, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            if json.loads(state.read_text(encoding="utf-8")).get("token") == token:
                state.unlink()
        except (OSError, ValueError):
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
