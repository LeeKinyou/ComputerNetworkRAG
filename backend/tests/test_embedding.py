from app import embedding


def test_cache_key_is_stable_and_text_sensitive():
    assert embedding.cache_key("chunk-1", "三次握手") == embedding.cache_key("chunk-1", "三次握手")
    assert embedding.cache_key("chunk-1", "三次握手") != embedding.cache_key("chunk-1", "四次挥手")


def test_remote_embedding_requires_all_three_fields(monkeypatch):
    monkeypatch.setattr(embedding.settings, "embedding_base_url", "https://api.example.com/v1")
    monkeypatch.setattr(embedding.settings, "embedding_model", "bge-m3")
    monkeypatch.setattr(embedding.settings, "embedding_api_key", "")
    assert not embedding.enabled()


def test_remote_embedding_enabled_when_complete(monkeypatch):
    monkeypatch.setattr(embedding.settings, "embedding_base_url", "https://api.example.com/v1/")
    monkeypatch.setattr(embedding.settings, "embedding_model", "bge-m3")
    monkeypatch.setattr(embedding.settings, "embedding_api_key", "sk-test")
    assert embedding.enabled()
    assert embedding.endpoint() == "https://api.example.com/v1/embeddings"


def test_hash_backend_remains_default():
    from app.retrieval import VECTOR_DIM, embed

    vector = embed("TCP 三次握手")
    assert len(vector) == VECTOR_DIM
    assert any(abs(value) > 0 for value in vector)
