"""
test_atuador.py — Unit tests for the Actuator LRU deduplication cache.

Tests:
  - New comando_id is accepted and processed
  - Duplicate comando_id is rejected (LRU cache hit)
  - LRU cache eviction when capacity is exceeded
  - Commands without comando_id are always processed (no ID = no dedup)
"""

import pytest
import collections
from estufa import config
from estufa.atuador import _is_duplicado, _dedup_cache


@pytest.fixture(autouse=True)
def limpar_cache():
    """Clears the LRU cache before each test to ensure isolation."""
    _dedup_cache.clear()
    yield
    _dedup_cache.clear()


class TestDeduplicacaoLRU:
    def test_novo_comando_id_nao_e_duplicado(self):
        """A fresh UUID should not be flagged as duplicate."""
        assert _is_duplicado("uuid-novo-123") is False

    def test_mesmo_comando_id_e_duplicado(self):
        """The same UUID seen twice should be flagged as duplicate on second call."""
        _is_duplicado("uuid-repetido-456")  # First call: add to cache
        assert _is_duplicado("uuid-repetido-456") is True  # Second call: duplicate

    def test_ids_diferentes_nao_sao_duplicados(self):
        """Different UUIDs should each be processed independently."""
        assert _is_duplicado("uuid-a") is False
        assert _is_duplicado("uuid-b") is False
        assert _is_duplicado("uuid-c") is False

    def test_sem_id_nunca_e_duplicado(self):
        """Commands without comando_id (empty string) should always be processed."""
        assert _is_duplicado("") is False
        assert _is_duplicado("") is False  # Even repeated empty strings are processed

    def test_cache_evicao_quando_cheio(self):
        """When cache reaches DEDUP_CACHE_SIZE, oldest entry is evicted."""
        # Fill cache to capacity
        for i in range(config.DEDUP_CACHE_SIZE):
            _is_duplicado(f"uuid-{i:04d}")

        assert len(_dedup_cache) == config.DEDUP_CACHE_SIZE

        # Adding one more should evict the oldest (uuid-0000)
        _is_duplicado("uuid-novo-apos-cheio")
        assert len(_dedup_cache) == config.DEDUP_CACHE_SIZE

        # uuid-0000 should have been evicted — it should NOT be flagged as duplicate
        assert _is_duplicado("uuid-0000") is False

    def test_lru_atualiza_posicao_ao_ser_acessado(self):
        """Accessing an existing entry refreshes its LRU position (not evicted first)."""
        # Fill cache to capacity
        for i in range(config.DEDUP_CACHE_SIZE):
            _is_duplicado(f"uuid-{i:04d}")

        # Access uuid-0000 to refresh its LRU position
        _is_duplicado("uuid-0000")  # This marks it as "recently used"

        # Add new entry — uuid-0001 should be evicted (oldest not recently accessed)
        _is_duplicado("uuid-novo-refresh-test")

        # uuid-0000 should still be in cache (was recently accessed)
        assert _is_duplicado("uuid-0000") is True

    def test_tres_publicacoes_simultaneas_do_mesmo_comando(self):
        """
        Simulates 3 controllers publishing the same comando_id (real-world scenario).
        Only the first should be processed; the other two should be duplicates.
        """
        shared_id = "uuid-middleware-gerado-xyz"

        result_ctrl1 = _is_duplicado(shared_id)  # First: not duplicate
        result_ctrl2 = _is_duplicado(shared_id)  # Second: duplicate
        result_ctrl3 = _is_duplicado(shared_id)  # Third: duplicate

        assert result_ctrl1 is False  # Processed
        assert result_ctrl2 is True   # Discarded
        assert result_ctrl3 is True   # Discarded
