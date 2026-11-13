from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, Session, declarative_base
import os
import asyncio
from dotenv import load_dotenv
import redis
import json
from celery_app import celery_app
from celery.result import AsyncResult
from tasks import soma, fatorial
from kafka_producer import enviar_mensagem

load_dotenv()

security = HTTPBasic()

username_correto = os.getenv("username_correto")
password_correto = os.getenv("password_correto")

DATABASE_URL = os.getenv("DATABASE_URL")

redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Login(BaseModel):
    username: str
    password: str

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

def salvar_tarefa_cache(tarefa_id: int, tarefa: TarefaDB):
    redis_client.set(f"tarefa:{tarefa_id}", json.dumps(tarefa.model_dump()))

def deletar_tarefa_cache(tarefa_id: int):
    redis_client.delete(f"tarefa:{tarefa_id}")



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

@app.get("/calcular/resultado/{task_id}")
def get_resultado(task_id: str):
    resultado = AsyncResult(task_id, app=celery_app)
    if resultado.state == 'PENDING':
        return {"task_id": task_id, "status": "Pendente"}
    elif resultado.state == 'STARTED':
        return {"task_id": task_id, "status": "Em andamento"}
    elif resultado.state == 'SUCCESS':
        return {"task_id": task_id, "status": "Concluída", "resultado": resultado.result}
    elif resultado.state == 'FAILURE':
        return {"task_id": task_id, "status": "Falha", "erro": str(resultado.result)}
    else:
        return {"task_id": task_id, "status": str(resultado.state)}

@app.post("/login")
def login(dados: Login):
    if dados.username == username_correto and dados.password == password_correto:
        return {"message": "Login bem-sucedido"}
    elif dados.username is None or dados.password is None:
        raise HTTPException(status_code=422, detail="Username e password são obrigatórios")
    else:
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")

@app.post("/calcular/soma")
def calcular_soma(a: int, b: int):
    task = soma.delay(a=a, b=b)
    return {"task_id": task.id, "status": "Tarefa de soma enviada para execução"}

@app.post("/calcular/fatorial")
def calcular_fatorial(n: int):
    task = fatorial.delay(n=n)
    return {"task_id": task.id, "status": "Tarefa de fatorial enviada para execução"}


@app.get("/debug/redis")
async def mostrar_tarefas_cache():
    tarefas_cache = []
    for chave in redis_client.keys("tarefa:*"):
        valor = redis_client.get(chave)
        tarefas_cache.append({"chave": chave, "valor": json.loads(valor)})
    return tarefas_cache

@app.get("/tarefas")
async def get_tarefas(page: int = 1, limit: int = 10, db: Session = Depends(session_db), credentials: HTTPBasicCredentials = Depends(auntenticador)):

    if page < 1 or limit < 1:
        raise HTTPException(status_code=400, detail="Parâmetros de paginação inválidos. 'page' e 'limit' devem ser maiores que 0.")

    tarefas = db.query(TarefaDB).offset((page - 1) * limit).limit(limit).all()
    total_tarefas = db.query(TarefaDB).count()

    if not tarefas:
        return {"message": "Não existem tarefas cadastradas"}

    return {"tarefas": [{"id": tarefa.id, "nome": tarefa.nome, "descricao": tarefa.descricao, "status": tarefa.status} for tarefa in tarefas], "total_tarefas": total_tarefas, "page": page, "limit": limit}   

@app.post("/tarefas")
async def post_tarefas(tarefa: Tarefa, db: Session = Depends(session_db), credentials: HTTPBasicCredentials = Depends(auntenticador)):

    db_tarefa = db.query(TarefaDB).filter(TarefaDB.nome == tarefa.nome).first()
    if db_tarefa:
        raise HTTPException(status_code=400, detail="Tarefa já cadastrada!")
    nova_tarefa = TarefaDB(nome=tarefa.nome, descricao=tarefa.descricao, status=tarefa.status)
    db.add(nova_tarefa)
    db.commit()
    db.refresh(nova_tarefa)
    salvar_tarefa_cache(nova_tarefa.id, tarefa)
    enviar_mensagem("tarefas", {"acao": "adicionar", "tarefa": tarefa.model_dump()})
    return {"message": "Tarefa adicionada com sucesso", "id": nova_tarefa.id}

@app.put("/tarefas/{id}")
async def put_tarefas(id: int, tarefa: Tarefa, db: Session = Depends(session_db), credentials: HTTPBasicCredentials = Depends(auntenticador)):

    db_tarefa = db.query(TarefaDB).filter(TarefaDB.id == id).first()
    if not db_tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não cadastrada!")
    db_tarefa.nome = tarefa.nome
    db_tarefa.descricao = tarefa.descricao
    db_tarefa.status = tarefa.status
    db.commit()
    db.refresh(db_tarefa)
    salvar_tarefa_cache(db_tarefa.id, tarefa)
    return {"message": "Tarefa atualizada com sucesso!"}

@app.delete("/tarefas/{id}")
async def delete_tarefas(id: int, db: Session = Depends(session_db), credentials: HTTPBasicCredentials = Depends(auntenticador)):

    db_tarefa = db.query(TarefaDB).filter(TarefaDB.id == id).first()
    if not db_tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não cadastrada!")
    db.delete(db_tarefa)
    db.commit()
    deletar_tarefa_cache(id)

    return {"message": "Tarefa deletada com sucesso"}