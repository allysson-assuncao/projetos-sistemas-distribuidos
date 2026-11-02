"""
test_atuador.py — Testes unitários do cache LRU de deduplicação do atuador.
"""

import pytest
from estufa import config
from estufa.atuador import _is_duplicado, _dedup_cache


@pytest.fixture(autouse=True)
def limpar_cache():
    """Limpa o cache LRU antes e após cada teste."""
    _dedup_cache.clear()
    yield
    _dedup_cache.clear()


class TestDeduplicacaoLRU:
    def test_novo_comando_id_nao_e_duplicado(self):
        """Um identificador inédito deve ser aceito na primeira chamada."""
        assert _is_duplicado("uuid-novo-123") is False

    def test_mesmo_comando_id_e_duplicado(self):
        """O mesmo identificador enviado duas vezes deve ser descartado na segunda vez."""
        _is_duplicado("uuid-repetido-456")
        assert _is_duplicado("uuid-repetido-456") is True

    def test_ids_diferentes_nao_sao_duplicados(self):
        """Identificadores distintos devem ser processados de forma independente."""
        assert _is_duplicado("uuid-a") is False
        assert _is_duplicado("uuid-b") is False
        assert _is_duplicado("uuid-c") is False

    def test_sem_id_nunca_e_duplicado(self):
        """Comandos sem comando_id (string vazia) devem ser sempre processados."""
        assert _is_duplicado("") is False
        assert _is_duplicado("") is False

    def test_cache_evicao_quando_cheio(self):
        """Ao atingir DEDUP_CACHE_SIZE, a entrada menos recentemente usada é removida."""
        for i in range(config.DEDUP_CACHE_SIZE):
            _is_duplicado(f"uuid-{i:04d}")

        assert len(_dedup_cache) == config.DEDUP_CACHE_SIZE

        _is_duplicado("uuid-novo-apos-cheio")
        assert len(_dedup_cache) == config.DEDUP_CACHE_SIZE

        assert _is_duplicado("uuid-0000") is False

    def test_lru_atualiza_posicao_ao_ser_acessado(self):
        """Consultar uma chave já existente renova sua posição no cache LRU."""
        for i in range(config.DEDUP_CACHE_SIZE):
            _is_duplicado(f"uuid-{i:04d}")

        _is_duplicado("uuid-0000")
        _is_duplicado("uuid-novo-refresh-test")

        assert _is_duplicado("uuid-0000") is True

    def test_tres_publicacoes_simultaneas_do_mesmo_comando(self):
        """Simula as 3 réplicas publicando o mesmo comando_id: apenas a primeira é aceita."""
        shared_id = "uuid-middleware-gerado-xyz"

        result_ctrl1 = _is_duplicado(shared_id)
        result_ctrl2 = _is_duplicado(shared_id)
        result_ctrl3 = _is_duplicado(shared_id)

        assert result_ctrl1 is False
        assert result_ctrl2 is True
        assert result_ctrl3 is True
