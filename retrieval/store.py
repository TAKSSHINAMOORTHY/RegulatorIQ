"""Columnar metadata store, boolean pre-filtering allow-masks, and compressed on-demand text blobs."""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import zstandard as zstd

from config.paths import CONFIG_DIR
from ingest.normalise import normalise_circular_no


# Load canonical topics list to establish stable bit indices
def _load_topics_list() -> List[str]:
    topics_file = CONFIG_DIR / "topics.yaml"
    if topics_file.exists():
        import yaml

        try:
            with open(topics_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return sorted(list(data.get("topics", {}).keys()))
        except Exception:
            pass
    return []


CANONICAL_TOPICS = _load_topics_list()
TOPIC_TO_BIT: Dict[str, int] = {
    topic: (1 << idx) for idx, topic in enumerate(CANONICAL_TOPICS[:62])
}

CANONICAL_ENTITIES = [
    "commercial_banks",
    "nbfcs",
    "urban_cooperative_banks",
    "payment_system_operators",
    "all_india_financial_institutions",
    "small_finance_banks",
    "payment_banks",
    "authorized_dealers",
    "housing_finance_companies",
    "credit_information_companies",
    "asset_reconstruction_companies",
]
ENTITY_TO_BIT: Dict[str, int] = {
    entity: (1 << idx) for idx, entity in enumerate(CANONICAL_ENTITIES)
}


def parse_date_to_days(date_str: Optional[str]) -> int:
    """Convert YYYY-MM-DD to integer days since 1970-01-01, or -1 if invalid."""
    if not date_str:
        return -1
    try:
        # Handle string like "2025-05-12"
        dt = datetime.strptime(date_str.strip()[:10], "%Y-%m-%d").date()
        return (dt - date(1970, 1, 1)).days
    except Exception:
        return -1


def encode_bitmask(items: List[str], mapping: Dict[str, int]) -> int:
    """Convert list of item keys into integer bitmask."""
    mask = 0
    for item in items:
        cleaned = item.strip().lower()
        if cleaned in mapping:
            mask |= mapping[cleaned]
    return mask


@dataclass
class Filters:
    """Structured search filters for pre-filtering retrieval."""

    doc_type: Optional[List[str]] = None
    is_current: Optional[bool] = None  # True, False, or None for any
    issue_date_after: Optional[str] = None  # YYYY-MM-DD
    issue_date_before: Optional[str] = None  # YYYY-MM-DD
    topics_any: Optional[List[str]] = None
    topics_all: Optional[List[str]] = None
    entities_any: Optional[List[str]] = None
    circular_no: Optional[str] = None
    doc_id: Optional[List[str]] = None


@dataclass
class Chunk:
    """Loaded chunk record with full metadata and text."""

    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    chunk_type: str
    section_path: str
    para_ref: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    doc_type: str
    title: str
    circular_no: Optional[str]
    issue_date: Optional[str]
    valid_from: Optional[str]
    valid_to: Optional[str]
    is_current: bool
    validity_confidence: str
    topics: List[str]
    applicability_entities: List[str]
    source_url: str
    token_count: int


class TextBlobStore:
    """On-demand zstandard compressed text storage with LRU caching."""

    def __init__(self, bin_path: Path, offsets_path: Path, lru_size: int = 512) -> None:
        self.bin_path = Path(bin_path)
        self.offsets_path = Path(offsets_path)
        self.offsets: np.ndarray = np.empty((0, 2), dtype=np.int64)
        if self.offsets_path.exists():
            self.offsets = np.load(self.offsets_path)
        self._dctx = zstd.ZstdDecompressor()
        self._cache: OrderedDict[int, str] = OrderedDict()
        self._max_cache = lru_size

    def get_text(self, index: int) -> str:
        """Decompress and return chunk text at the given row index."""
        if index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]

        if index < 0 or index >= len(self.offsets):
            return ""

        offset, length = self.offsets[index]
        with open(self.bin_path, "rb") as f:
            f.seek(offset)
            compressed = f.read(length)

        decompressed = self._dctx.decompress(compressed).decode("utf-8")

        # Cache with LRU eviction
        if len(self._cache) >= self._max_cache:
            self._cache.popitem(last=False)
        self._cache[index] = decompressed
        return decompressed

    @classmethod
    def create(cls, texts: List[str], bin_path: Path, offsets_path: Path) -> TextBlobStore:
        """Compress texts individually and persist offsets."""
        bin_path = Path(bin_path)
        offsets_path = Path(offsets_path)
        bin_path.parent.mkdir(parents=True, exist_ok=True)
        offsets_path.parent.mkdir(parents=True, exist_ok=True)

        cctx = zstd.ZstdCompressor(level=3)
        offsets: List[Tuple[int, int]] = []
        current_offset = 0

        with open(bin_path, "wb") as f:
            for text in texts:
                compressed = cctx.compress(text.encode("utf-8"))
                length = len(compressed)
                f.write(compressed)
                offsets.append((current_offset, length))
                current_offset += length

        offsets_arr = np.array(offsets, dtype=np.int64)
        np.save(offsets_path, offsets_arr)
        return cls(bin_path, offsets_path)


class MetadataStore:
    """Columnar metadata table using pyarrow and memory mapping."""

    def __init__(
        self,
        table: pa.Table,
        blob_store: TextBlobStore,
    ) -> None:
        self.table = table
        self.blob_store = blob_store
        self.chunk_ids: List[str] = table["chunk_id"].to_pylist()
        self._id_to_idx: Dict[str, int] = {cid: idx for idx, cid in enumerate(self.chunk_ids)}

        # Pre-extract columnar arrays for blazing-fast vectorized pre-filtering
        self._doc_types = np.array(table["doc_type"].to_pylist())
        self._is_current = np.array(table["is_current"].to_pylist(), dtype=bool)
        self._issue_days = np.array(table["issue_date_days"].to_pylist(), dtype=np.int32)
        self._topics_mask = np.array(table["topics_mask"].to_pylist(), dtype=np.int64)
        self._entities_mask = np.array(table["entities_mask"].to_pylist(), dtype=np.int64)
        self._circular_nos = np.array(table["circular_no"].to_pylist())
        self._doc_ids = np.array(table["doc_id"].to_pylist())

    def __len__(self) -> int:
        return len(self.chunk_ids)

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        """Retrieve full chunk by chunk_id."""
        idx = self._id_to_idx.get(chunk_id)
        if idx is None:
            return None
        return self.get_chunk_by_index(idx)

    def get_chunk_by_index(self, idx: int) -> Chunk:
        """Retrieve full chunk by row index."""
        row = self.table.slice(idx, 1).to_pydict()
        text = self.blob_store.get_text(idx)

        topics_json = row["topics_json"][0]
        entities_json = row["entities_json"][0]
        topics = json.loads(topics_json) if topics_json else []
        entities = json.loads(entities_json) if entities_json else []

        return Chunk(
            chunk_id=row["chunk_id"][0],
            doc_id=row["doc_id"][0],
            ordinal=row["ordinal"][0],
            text=text,
            chunk_type=row["chunk_type"][0],
            section_path=row["section_path"][0],
            para_ref=row["para_ref"][0],
            page_start=row["page_start"][0],
            page_end=row["page_end"][0],
            doc_type=row["doc_type"][0],
            title=row["title"][0],
            circular_no=row["circular_no"][0],
            issue_date=row["issue_date_str"][0],
            valid_from=row["valid_from"][0],
            valid_to=row["valid_to"][0],
            is_current=row["is_current"][0],
            validity_confidence=row["validity_confidence"][0],
            topics=topics,
            applicability_entities=entities,
            source_url=row["source_url"][0],
            token_count=row["token_count"][0],
        )

    def build_allow_mask(self, filters: Optional[Filters]) -> np.ndarray:
        """Build boolean allow-mask (shape: N) from structured filters."""
        n = len(self)
        if filters is None:
            return np.ones(n, dtype=bool)

        mask = np.ones(n, dtype=bool)

        # 1. doc_type filter
        if filters.doc_type:
            types_set = set(filters.doc_type)
            mask &= np.isin(self._doc_types, list(types_set))

        # 2. is_current filter
        if filters.is_current is not None:
            mask &= self._is_current == filters.is_current

        # 3. issue_date range
        if filters.issue_date_after:
            min_days = parse_date_to_days(filters.issue_date_after)
            if min_days >= 0:
                mask &= self._issue_days >= min_days

        if filters.issue_date_before:
            max_days = parse_date_to_days(filters.issue_date_before)
            if max_days >= 0:
                mask &= self._issue_days <= max_days

        # 4. topics_any
        if filters.topics_any:
            q_mask = encode_bitmask(filters.topics_any, TOPIC_TO_BIT)
            if q_mask > 0:
                mask &= (self._topics_mask & q_mask) > 0
            else:
                # None of the queried topics are in canonical taxonomy
                mask &= False

        # 5. topics_all
        if filters.topics_all:
            q_mask = encode_bitmask(filters.topics_all, TOPIC_TO_BIT)
            if q_mask > 0:
                mask &= (self._topics_mask & q_mask) == q_mask
            else:
                mask &= False

        # 6. entities_any
        if filters.entities_any:
            q_mask = encode_bitmask(filters.entities_any, ENTITY_TO_BIT)
            if q_mask > 0:
                mask &= (self._entities_mask & q_mask) > 0
            else:
                mask &= False

        # 7. circular_no exact match (canonicalized)
        if filters.circular_no:
            target_norm = (
                normalise_circular_no(filters.circular_no) or filters.circular_no.strip().upper()
            )
            mask &= self._circular_nos == target_norm

        # 8. doc_id in
        if filters.doc_id:
            mask &= np.isin(self._doc_ids, filters.doc_id)

        return mask

    def save(self, meta_dir: Path) -> None:
        """Save columnar metadata table and text blob store to disk."""
        meta_dir = Path(meta_dir)
        meta_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = meta_dir / "metadata.parquet"
        pq.write_table(self.table, parquet_path, compression="zstd")

    @classmethod
    def load(cls, meta_dir: Path) -> MetadataStore:
        """Load columnar metadata store via memory mapping."""
        meta_dir = Path(meta_dir)
        parquet_path = meta_dir / "metadata.parquet"
        bin_path = meta_dir / "text.bin.zst"
        offsets_path = meta_dir / "text.offsets.npy"

        if not parquet_path.exists():
            raise FileNotFoundError(f"Metadata parquet missing: {parquet_path}")

        table = pq.read_table(parquet_path, memory_map=True)
        blob_store = TextBlobStore(bin_path, offsets_path)
        return cls(table, blob_store)


def build_metadata_store_from_chunks(
    chunk_records: List[Dict[str, Any]],
    meta_dir: Path,
) -> MetadataStore:
    """Create metadata table and compressed text blob files from chunk records."""
    meta_dir = Path(meta_dir)
    meta_dir.mkdir(parents=True, exist_ok=True)

    texts: List[str] = []
    chunk_ids: List[str] = []
    doc_ids: List[str] = []
    ordinals: List[int] = []
    chunk_types: List[str] = []
    section_paths: List[str] = []
    para_refs: List[Optional[str]] = []
    page_starts: List[Optional[int]] = []
    page_ends: List[Optional[int]] = []
    doc_types: List[str] = []
    titles: List[str] = []
    circular_nos: List[str] = []
    issue_days: List[int] = []
    issue_str: List[str] = []
    valid_froms: List[Optional[str]] = []
    valid_tos: List[Optional[str]] = []
    is_currents: List[bool] = []
    validity_confs: List[str] = []
    topics_masks: List[int] = []
    entities_masks: List[int] = []
    topics_jsons: List[str] = []
    entities_jsons: List[str] = []
    source_urls: List[str] = []
    token_counts: List[int] = []

    for c in chunk_records:
        texts.append(c.get("text", ""))
        chunk_ids.append(c["chunk_id"])
        doc_ids.append(c["doc_id"])
        ordinals.append(c.get("ordinal", 0))
        chunk_types.append(c.get("chunk_type", "text"))
        section_paths.append(c.get("section_path", ""))
        para_refs.append(c.get("para_ref"))
        page_starts.append(c.get("page_start"))
        page_ends.append(c.get("page_end"))
        doc_types.append(c.get("doc_type", ""))
        titles.append(c.get("title", ""))

        cno = c.get("circular_no") or ""
        norm_cno = normalise_circular_no(cno) or cno.strip().upper()
        circular_nos.append(norm_cno)

        idate = c.get("issue_date") or ""
        issue_str.append(idate)
        issue_days.append(parse_date_to_days(idate))

        valid_froms.append(c.get("valid_from"))
        valid_tos.append(c.get("valid_to"))
        is_currents.append(bool(c.get("is_current", True)))
        validity_confs.append(c.get("validity_confidence", "medium"))

        raw_topics = c.get("topics") or []
        topics_masks.append(encode_bitmask(raw_topics, TOPIC_TO_BIT))
        topics_jsons.append(json.dumps(raw_topics))

        raw_entities = c.get("applicability_entities") or []
        entities_masks.append(encode_bitmask(raw_entities, ENTITY_TO_BIT))
        entities_jsons.append(json.dumps(raw_entities))

        source_urls.append(c.get("source_url", ""))
        token_counts.append(c.get("token_count", 0))

    # Build compressed text blob
    bin_path = meta_dir / "text.bin.zst"
    offsets_path = meta_dir / "text.offsets.npy"
    blob_store = TextBlobStore.create(texts, bin_path, offsets_path)

    # Build pyarrow Table
    table = pa.Table.from_arrays(
        [
            pa.array(chunk_ids, type=pa.string()),
            pa.array(doc_ids, type=pa.string()),
            pa.array(ordinals, type=pa.int32()),
            pa.array(chunk_types, type=pa.string()),
            pa.array(section_paths, type=pa.string()),
            pa.array(para_refs, type=pa.string()),
            pa.array(page_starts, type=pa.int32()),
            pa.array(page_ends, type=pa.int32()),
            pa.array(doc_types, type=pa.string()),
            pa.array(titles, type=pa.string()),
            pa.array(circular_nos, type=pa.string()),
            pa.array(issue_days, type=pa.int32()),
            pa.array(issue_str, type=pa.string()),
            pa.array(valid_froms, type=pa.string()),
            pa.array(valid_tos, type=pa.string()),
            pa.array(is_currents, type=pa.bool_()),
            pa.array(validity_confs, type=pa.string()),
            pa.array(topics_masks, type=pa.int64()),
            pa.array(entities_masks, type=pa.int64()),
            pa.array(topics_jsons, type=pa.string()),
            pa.array(entities_jsons, type=pa.string()),
            pa.array(source_urls, type=pa.string()),
            pa.array(token_counts, type=pa.int32()),
        ],
        names=[
            "chunk_id",
            "doc_id",
            "ordinal",
            "chunk_type",
            "section_path",
            "para_ref",
            "page_start",
            "page_end",
            "doc_type",
            "title",
            "circular_no",
            "issue_date_days",
            "issue_date_str",
            "valid_from",
            "valid_to",
            "is_current",
            "validity_confidence",
            "topics_mask",
            "entities_mask",
            "topics_json",
            "entities_json",
            "source_url",
            "token_count",
        ],
    )

    store = MetadataStore(table, blob_store)
    store.save(meta_dir)
    return store
