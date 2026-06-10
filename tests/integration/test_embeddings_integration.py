"""Integration tests for cerebra/storage/embeddings.py — loads the real model.

These tests require sentence-transformers and the mxbai-embed-large-v1 weights
(~1.5 GB, downloaded to HuggingFace cache on first run).

Run all:   python -m pytest tests/integration/test_embeddings_integration.py
Skip all:  python -m pytest -m "not integration"
"""

from __future__ import annotations

import numpy as np
import pytest

from cerebra.storage.embeddings import _DIMENSIONS, embed


@pytest.mark.integration
class TestEmbedRealModel:
    def test_output_shape(self) -> None:
        vecs = embed(["hello world"])
        assert vecs.shape == (1, _DIMENSIONS)

    def test_batch_shape(self) -> None:
        texts = ["first sentence", "second sentence", "third sentence"]
        vecs = embed(texts)
        assert vecs.shape == (len(texts), _DIMENSIONS)

    def test_output_dtype(self) -> None:
        vecs = embed(["hello world"])
        assert vecs.dtype == np.float32

    def test_deterministic(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        v1 = embed([text])
        v2 = embed([text])
        np.testing.assert_array_equal(v1, v2)

    def test_vectors_normalized(self) -> None:
        vecs = embed(["hello world", "another sentence"])
        norms = np.linalg.norm(vecs, axis=1)
        # float32 accumulation over 1024 dims permits ~1e-3 deviation
        np.testing.assert_allclose(norms, 1.0, atol=1e-3)
