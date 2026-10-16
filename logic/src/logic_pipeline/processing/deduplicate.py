"""Deduplication module with exact SHA-256 and near-duplicate Jaccard similarity."""

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from logic_pipeline.provenance import compute_sha256, ProvenanceMetadata
from logic_pipeline.logging_config import get_logger

logger = get_logger("processing.deduplicate")


@dataclass
class DeduplicationResult:
    unique_records: List[Dict[str, Any]] = field(default_factory=list)
    exact_duplicates_count: int = 0
    near_duplicates_count: int = 0
    merged_provenance_count: int = 0


class Deduplicator:
    """Manages exact and near-duplicate detection."""

    def __init__(self, near_duplicate_threshold: float = 0.95, flag_only: bool = True):
        self.near_duplicate_threshold = near_duplicate_threshold
        self.flag_only = flag_only
        self.exact_hashes: Set[str] = set()
        self.record_shingles: List[Tuple[str, Set[str], Dict[str, Any]]] = []

    def _get_shingles(self, text: str, k: int = 2) -> Set[str]:
        """Extracts token shingles combining unigrams and bigrams for robust similarity."""
        words = re.findall(r"\b[A-Za-z0-9_]+\b", text.lower())
        if len(words) < 2:
            return set(words)
        shingles = set(words)
        for i in range(len(words) - 1):
            shingles.add(f"{words[i]} {words[i+1]}")
        return shingles

    def _jaccard_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        """Calculates Jaccard similarity coefficient between two sets."""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union > 0 else 0.0

    def process_records(self, records: List[Dict[str, Any]]) -> DeduplicationResult:
        """Deduplicates a list of records, preserving provenance on merges."""
        result = DeduplicationResult()
        seen_exact: Dict[str, Dict[str, Any]] = {}

        for rec in records:
            content = rec.get("normalized_content") or rec.get("raw_content") or str(rec)
            h = compute_sha256(content)

            # Exact duplicate check
            if h in seen_exact:
                result.exact_duplicates_count += 1
                # Merge provenance
                existing = seen_exact[h]
                if "provenance" in existing and "provenance" in rec:
                    p1 = ProvenanceMetadata.from_dict(existing["provenance"])
                    p2 = ProvenanceMetadata.from_dict(rec["provenance"])
                    p1.merge_with(p2)
                    existing["provenance"] = p1.to_dict()
                    result.merged_provenance_count += 1
                continue

            # Near duplicate check (for reasonably sized texts > 50 chars)
            is_near_dup = False
            if len(content) > 50 and self.near_duplicate_threshold < 1.0:
                shingles = self._get_shingles(content)
                for existing_id, existing_shingles, existing_rec in self.record_shingles:
                    sim = self._jaccard_similarity(shingles, existing_shingles)
                    if sim >= self.near_duplicate_threshold:
                        # Found near duplicate
                        result.near_duplicates_count += 1
                        rec["near_duplicate_of"] = existing_id
                        if not self.flag_only:
                            is_near_dup = True
                            # Merge provenance into existing
                            if "provenance" in existing_rec and "provenance" in rec:
                                p1 = ProvenanceMetadata.from_dict(existing_rec["provenance"])
                                p2 = ProvenanceMetadata.from_dict(rec["provenance"])
                                p1.merge_with(p2)
                                existing_rec["provenance"] = p1.to_dict()
                                result.merged_provenance_count += 1
                            break

                if not is_near_dup:
                    rec_id = str(rec.get("record_id") or h[:12])
                    self.record_shingles.append((rec_id, shingles, rec))

            if not is_near_dup:
                seen_exact[h] = rec
                result.unique_records.append(rec)

        return result
