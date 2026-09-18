from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, Session, declarative_base
import os

security = HTTPBasic()

username_correto = os.getenv("username_correto")
password_correto = os.getenv("password_correto")

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TarefaDB(Base):
    __tablename__ = "tarefas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True)
    descricao = Column(String)
    status = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

class Tarefa(BaseModel):
    nome: str
    descricao: str
    status: bool = False


def auntenticador(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != username_correto or credentials.password != password_correto:
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos", headers={"WWW-Authenticate": "Basic"})

def session_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI(title="API Gerenciador de Tarefas", 
    description="API para gerenciamento de tarefas", 
    version="1.0.0", 
    contact={"name": "João Pedro",
             "url": "https://github.com/JoaoHardman",
             "email": "jp.hardman.l@gmail.com"})

@app.get("/tarefas")
def get_tarefas(page: int = 1, limit: int = 10, db: Session = Depends(session_db), credentials: HTTPBasicCredentials = Depends(auntenticador)):

    if page < 1 or limit < 1:
        raise HTTPException(status_code=400, detail="Parâmetros de paginação inválidos. 'page' e 'limit' devem ser maiores que 0.")

    tarefas = db.query(TarefaDB).offset((page - 1) * limit).limit(limit).all()
    total_tarefas = db.query(TarefaDB).count()

    if not tarefas:
        return {"message": "Não existem tarefas cadastradas"}

    return {"tarefas": [{"id": tarefa.id, "nome": tarefa.nome, "descricao": tarefa.descricao, "status": tarefa.status} for tarefa in tarefas], "total_tarefas": total_tarefas, "page": page, "limit": limit}   

@app.post("/tarefas")
def post_tarefas(tarefa: Tarefa, db: Session = Depends(session_db), credentials: HTTPBasicCredentials = Depends(auntenticador)):

    db_tarefa = db.query(TarefaDB).filter(TarefaDB.nome == tarefa.nome).first()
    if db_tarefa:
        raise HTTPException(status_code=400, detail="Tarefa já cadastrada!")
    nova_tarefa = TarefaDB(nome=tarefa.nome, descricao=tarefa.descricao, status=tarefa.status)
    db.add(nova_tarefa)
    db.commit()
    db.refresh(nova_tarefa)
    return {"message": "Tarefa adicionada com sucesso", "id": nova_tarefa.id}

@app.put("/tarefas/{id}")
def put_tarefas(id: int, tarefa: Tarefa, db: Session = Depends(session_db), credentials: HTTPBasicCredentials = Depends(auntenticador)):

    db_tarefa = db.query(TarefaDB).filter(TarefaDB.id == id).first()
    if not db_tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não cadastrada!")
    db_tarefa.nome = tarefa.nome
    db_tarefa.descricao = tarefa.descricao
    db_tarefa.status = tarefa.status
    db.commit()
    db.refresh(db_tarefa)
    return {"message": "Tarefa atualizada com sucesso!"}

@app.delete("/tarefas/{id}")
def delete_tarefas(id: int, db: Session = Depends(session_db), credentials: HTTPBasicCredentials = Depends(auntenticador)):

    db_tarefa = db.query(TarefaDB).filter(TarefaDB.id == id).first()
    if not db_tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não cadastrada!")
    db.delete(db_tarefa)
    db.commit()

    return {"message": "Tarefa deletada com sucesso"}