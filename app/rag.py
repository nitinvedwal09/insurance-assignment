import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

RAG_DIR = Path(__file__).parent.parent / "data" / "rag"
INDEX_DIR = Path(__file__).parent.parent / "data" / "rag_index"
COLLECTION_NAME = "claims_kb"

# BAAI/bge-small-en-v1.5: 384-dim sentence embeddings, cosine-similarity retrieval.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    breadcrumb: str


def _split_long_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    
    if len(text) <= chunk_size:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    pieces: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            pieces.append(current)
        if len(para) <= chunk_size:
            current = para
        else:
            for i in range(0, len(para), chunk_size - overlap):
                pieces.append(para[i : i + chunk_size])
            current = ""
    if current:
        pieces.append(current)

    overlapped = []
    for i, piece in enumerate(pieces):
        if i > 0:
            piece = f"{pieces[i - 1][-overlap:]}\n\n{piece}"
        overlapped.append(piece)
    return overlapped


def chunk_markdown(text: str, source: str) -> list[Chunk]:
    """Structure-aware chunking: split on markdown headers, tag each section with a
    breadcrumb of its heading path, then pack oversized sections to ~CHUNK_SIZE chars."""
    matches = list(HEADER_RE.finditer(text))
    sections: list[tuple[str, str]] = []  # (breadcrumb, body)

    if not matches:
        body = text.strip()
        if body:
            sections.append(("", body))
    else:
        stack: list[tuple[int, str]] = []
        for i, m in enumerate(matches):
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            breadcrumb = " > ".join(t for _, t in stack)

            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                sections.append((breadcrumb, body))

    chunks: list[Chunk] = []
    for sec_idx, (breadcrumb, body) in enumerate(sections):
        for piece_idx, piece in enumerate(_split_long_text(body)):
            chunk_text = f"{breadcrumb}\n\n{piece}" if breadcrumb else piece
            chunks.append(
                Chunk(id=f"{source}::{sec_idx}::{piece_idx}", text=chunk_text, source=source, breadcrumb=breadcrumb)
            )
    return chunks


class RagIndex:
    """Chroma-backed retriever over the markdown knowledge base in data/rag."""

    def __init__(
        self,
        rag_dir: Path = RAG_DIR,
        persist_dir: Path = INDEX_DIR,
        model_name: str = EMBED_MODEL,
    ):
        self._rag_dir = rag_dir
        self._embedder = SentenceTransformer(model_name)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )
        self._sync_index()

    def _sync_index(self) -> None:
        md_files = sorted(self._rag_dir.glob("*.md"))
        file_texts = {path.name: path.read_text(encoding="utf-8") for path in md_files}
        current_hashes = {name: _file_hash(text) for name, text in file_texts.items()}

        existing = self._collection.get()
   
        existing_hashes = {m["source"]: m.get("file_hash") for m in existing["metadatas"]}
        if existing["ids"] and existing_hashes == current_hashes:
            return  # index already matches what's on disk

        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])

        all_chunks = [
            chunk for name, text in file_texts.items() for chunk in chunk_markdown(text, name)
        ]
        if not all_chunks:
            return

        embeddings = self._embedder.encode([c.text for c in all_chunks], normalize_embeddings=True).tolist()
        self._collection.add(
            ids=[c.id for c in all_chunks],
            embeddings=embeddings,
            documents=[c.text for c in all_chunks],
            metadatas=[
                {"source": c.source, "breadcrumb": c.breadcrumb, "file_hash": current_hashes[c.source]}
                for c in all_chunks
            ],
        )

    def query(self, text: str, k: int = 3) -> list[dict]:
        query_embedding = self._embedder.encode([QUERY_INSTRUCTION + text], normalize_embeddings=True).tolist()
        results = self._collection.query(query_embeddings=query_embedding, n_results=k)
        if not results["documents"][0]:
            return []
        return [
            {"text": doc, "source": meta["source"], "score": 1 - distance}
            for doc, meta, distance in zip(
                results["documents"][0], results["metadatas"][0], results["distances"][0]
            )
        ]
