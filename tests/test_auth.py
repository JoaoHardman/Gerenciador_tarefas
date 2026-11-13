import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from main import app, Base, session_db
from dotenv import load_dotenv

load_dotenv()

@pytest.fixture
def client():
    # Cria um banco SQLite temporário em memória.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    # Cria as tabelas no banco de testes.
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )

    # Substitui a conexão original pelo banco de testes.
    def override_session_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[session_db] = override_session_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # Remove a substituição após cada teste.
        app.dependency_overrides.pop(session_db, None)
        engine.dispose()

def test_autenticacao_valida(client):
    usuario = os.environ["username_correto"]
    senha = os.environ["password_correto"]
    response = client.post("/login", json={"username": usuario, "password": senha})
    assert response.status_code == 200, "A API deveria aceitar credenciais corretas"

def test_senha_incorreta(client):
    usuario = os.environ["username_correto"]
    senha = os.environ["password_correto"]
    response = client.post("/login", json={"username": usuario, "password": senha + "_incorreta"})
    assert response.status_code == 401, "A API deveria rejeitar uma senha incorreta"
    assert response.json() == {"detail": "Usuário ou senha incorretos"}, (f"Mensagem de erro inesperada: {response.json()}")

def test_usuario_incorreto(client):
    usuario = os.environ["username_correto"]
    senha = os.environ["password_correto"]
    response = client.post("/login", json={"username": usuario + "_incorreto", "password": senha})
    assert response.status_code == 401, "A API deveria rejeitar um usuário incorreto"
    assert response.json() == {"detail": "Usuário ou senha incorretos"}, (f"Mensagem de erro inesperada: {response.json()}")

def test_sem_credenciais(client):
    response = client.post("/login", json={})
    assert response.status_code == 422, "A API deveria rejeitar requisições sem credenciais"
    assert "detail" in response.json(), "Username e password são obrigatórios"