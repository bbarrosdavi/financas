"""API e site.

Duas portas de entrada, com autenticações diferentes:
- /api/v1/transaction/webhook: o celular, com `Authorization: Bearer <API_KEY>`;
- o resto de /api: o site, com cookie de sessão assinado depois da senha.
A porta fica só na rede que você escolher no docker-compose.yml (VPN, LAN).
"""

import asyncio
import hashlib
import hmac
import io
import json
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db, demo, exportar, push, servicos, sync
from app.config import settings

WEB = Path(__file__).resolve().parent.parent / "web"
COOKIE = "financas_sessao"
VALIDADE = 60 * 60 * 24 * 60   # 60 dias


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.iniciar()
    if db.demo_ativa():
        db.iniciar(db.caminho())
    tarefa = asyncio.create_task(push.worker())
    push.reenfileirar()
    try:
        yield
    finally:
        tarefa.cancel()


app = FastAPI(title="Finanças", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
def _assinar(expira: int) -> str:
    sig = hmac.new(settings.SESSION_SECRET.encode(), str(expira).encode(), hashlib.sha256).hexdigest()
    return f"{expira}.{sig}"


def sessao(request: Request) -> None:
    tok = request.cookies.get(COOKIE, "")
    try:
        expira, sig = tok.split(".", 1)
        ok = hmac.compare_digest(_assinar(int(expira)), tok) and int(expira) > time.time()
    except ValueError:
        ok = False
    if not ok:
        raise HTTPException(401, "Entre com a senha.")


def bearer(authorization: str = Header(default="")) -> None:
    tok = authorization.removeprefix("Bearer ").strip()
    if not authorization.startswith("Bearer ") or not secrets.compare_digest(tok, settings.API_KEY):
        raise HTTPException(401, "Chave inválida")


class Login(BaseModel):
    senha: str


@app.post("/api/login")
def login(body: Login, response: Response):
    if not secrets.compare_digest(body.senha, settings.WEB_PASSWORD):
        time.sleep(1)
        raise HTTPException(401, "Senha errada.")
    response.set_cookie(COOKIE, _assinar(int(time.time()) + VALIDADE), max_age=VALIDADE, httponly=True, samesite="lax")
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Celular
# ---------------------------------------------------------------------------
class Notificacao(BaseModel):
    package: str = Field(..., max_length=200)
    title: str = Field(..., max_length=500)
    text: str = Field(..., max_length=4000)
    timestamp: int | None = None


@app.post("/api/v1/transaction/webhook", status_code=202, dependencies=[Depends(bearer)])
def webhook(n: Notificacao):
    quando = datetime.fromtimestamp(n.timestamp / 1000, settings.tz) if n.timestamp else datetime.now(settings.tz)
    estado, inbox_id = push.receber(n.package, n.title, n.text, quando)
    if inbox_id is not None:
        try:
            push.fila.put_nowait(inbox_id)
        except asyncio.QueueFull:
            raise HTTPException(503, "Fila cheia, tente de novo")   # o MacroDroid repete
    return {"status": estado, "inbox_id": inbox_id}


class Sincronia(BaseModel):
    protocolo: int = 1
    cursor: int = 0
    mudancas: list[dict] = []


@app.post("/api/v1/sync", dependencies=[Depends(bearer)])
def sincronizar(body: Sincronia):
    """O app do celular manda o que mudou nele e recebe o que mudou aqui (ver app/sync.py)."""
    if body.protocolo != sync.PROTOCOLO:
        raise HTTPException(409, "Versão do app incompatível com a do servidor: atualize os dois.")
    with db.conectar_real() as con:
        r = sync.servir(con, body.cursor, body.mudancas, settings.TITULAR)
    r.pop("lancamentos")
    r["aparencia"] = _aparencia_do_dono()
    return r


def _papel_do_dono() -> Path | None:
    with db.conectar_real() as con:
        nome = db.parametro(con, "papel_de_parede", "") or ""
    f = Path(settings.PAPEIS_DIR) / Path(nome).name if nome else None
    return f if f and f.is_file() else None


def _aparencia_do_dono() -> dict:
    """A aparência da conta do dono no Apê (tema, claro ou escuro, desfoque, preferências) e o papel de parede
    dele: o app do celular passa a usar a mesma. Sem o Apê (Finanças sozinho), vai só o papel."""
    valores = {}
    ape_db = Path(settings.DATABASE_PATH).parent / "ape.db"
    if ape_db.is_file():
        try:
            c = sqlite3.connect(f"file:{ape_db}?mode=ro", uri=True)
            r = c.execute("SELECT s.value FROM app_settings s JOIN users u ON s.key = 'aparencia:' || u.id "
                          "WHERE u.username = ?", (getattr(settings, "FINANCAS_DONO", ""),)).fetchone()
            c.close()
            valores = json.loads(r[0]) if r else {}
        except (sqlite3.Error, ValueError):
            valores = {}
    f = _papel_do_dono()
    return {"valores": valores, "papel": f.name if f else "",
            "papel_versao": f"{f.stat().st_size}-{int(f.stat().st_mtime)}" if f else ""}


@app.get("/api/v1/papel", dependencies=[Depends(bearer)])
def papel_do_dono():
    """O papel de parede do dono, para o app do celular (a mesma chave da sincronização)."""
    f = _papel_do_dono()
    if not f:
        raise HTTPException(404, "Sem papel de parede.")
    return FileResponse(f)


# ---------------------------------------------------------------------------
# Site
# ---------------------------------------------------------------------------
api = Depends(sessao)


class Demo(BaseModel):
    ativo: bool


@app.get("/api/demo", dependencies=[api])
def ver_demo():
    """Dados de demonstração (app/demo.py): se estão ligados e se o banco de verdade ainda está vazio."""
    with db.conectar_real() as con:
        vazio = con.execute("SELECT 1 FROM lancamentos LIMIT 1").fetchone() is None
    return {"ativo": db.demo_ativa(), "vazio": vazio}


@app.put("/api/demo", dependencies=[api])
def mudar_demo(body: Demo):
    try:
        demo.ligar(date.today()) if body.ativo else demo.desligar()
    except ValueError as e:
        raise HTTPException(409, str(e))
    return ver_demo()


@app.get("/api/painel", dependencies=[api])
def painel(hoje: str | None = None, periodo: str | None = None):
    import re
    if periodo and not re.fullmatch(r"\d{4}(-\d{2}|-W\d{2})?", periodo):
        raise HTTPException(400, "Período é AAAA, AAAA-MM ou AAAA-Wnn.")
    with db.conectar() as con:
        return servicos.painel(con, date.fromisoformat(hoje) if hoje else None, periodo)


@app.get("/api/evolucao", dependencies=[api])
def evolucao(tipo: str = "mes", categoria: str | None = None, grupo: str | None = None, n: int = 12):
    if not categoria and not grupo:
        raise HTTPException(400, "Informe categoria ou grupo.")
    with db.conectar() as con:
        return servicos.evolucao(con, date.today(), tipo, categoria, grupo, min(max(n, 3), 36))


@app.get("/api/meses", dependencies=[api])
def meses():
    with db.conectar() as con:
        return [r[0] for r in con.execute("SELECT DISTINCT substr(data,1,7) FROM lancamentos ORDER BY 1 DESC")]


@app.get("/api/lancamentos", dependencies=[api])
def listar(mes: str | None = None, busca: str | None = None, pendentes: bool = False, categoria: str | None = None,
           de: str | None = None, ate: str | None = None):
    import re
    if any(d and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in (de, ate)):
        raise HTTPException(400, "Datas no formato AAAA-MM-DD.")
    with db.conectar() as con:
        return servicos.lancamentos(con, mes, busca, pendentes, categoria, limite=2000, de=de, ate=ate)


class Parte(BaseModel):
    valor: float
    natureza: str
    categoria: str | None = None
    pessoa: str | None = None
    meta: int | None = None
    obs: str = ""
    motivo: str = ""


class Partes(BaseModel):
    partes: list[Parte]
    lembrar: bool = False
    nota: str | None = None


@app.put("/api/lancamentos/{lid}/partes", dependencies=[api])
def definir(lid: int, body: Partes):
    with db.conectar() as con:
        try:
            return servicos.definir_partes(con, lid, [p.model_dump() for p in body.partes], body.lembrar, body.nota)
        except ValueError as e:
            raise HTTPException(400, str(e))


class Manual(BaseModel):
    data: str
    conta: str
    valor: float
    descricao: str
    contraparte: str = ""
    nota: str = ""
    partes: list[Parte] | None = None


@app.post("/api/lancamentos", dependencies=[api])
def criar(body: Manual):
    with db.conectar() as con:
        lid = servicos.inserir(con, body.conta, body.data, body.valor, body.descricao, body.contraparte, origem="manual",
                               nota=body.nota, partes=[p.model_dump() for p in body.partes] if body.partes else None)
        return {"id": lid}


@app.delete("/api/lancamentos/{lid}", dependencies=[api])
def apagar(lid: int):
    with db.conectar() as con:
        row = con.execute("SELECT origem FROM lancamentos WHERE id=?", (lid,)).fetchone()
        if not row:
            raise HTTPException(404)
        if row["origem"] not in ("manual", "push"):
            raise HTTPException(400, "Só lançamento manual ou do celular pode ser apagado; o do extrato é a fonte.")
        con.execute("DELETE FROM lancamentos WHERE id=?", (lid,))
        return {"ok": True}


@app.get("/api/vocabulario", dependencies=[api])
def vocabulario():
    with db.conectar() as con:
        return {
            "categorias": [dict(r) for r in con.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM partes p WHERE p.categoria=c.id) AS uso FROM categorias c ORDER BY ordem")],
            "pessoas": [dict(r) for r in con.execute("SELECT * FROM pessoas")],
            "metas": [dict(r) for r in con.execute("SELECT id, nome, ativa FROM metas ORDER BY ativa DESC, ordem, id")],
            "contas": [dict(r) for r in con.execute("SELECT * FROM contas")],
            "cores_grupos": json.loads(db.parametro(con, "cores_grupos", "{}") or "{}"),
        }


class SaldoReal(BaseModel):
    valor: float
    data: str


@app.get("/api/contas", dependencies=[api])
def contas():
    with db.conectar() as con:
        return servicos.saldo_contas(con)


@app.put("/api/contas/{conta}/saldo", dependencies=[api])
def saldo_real(conta: str, body: SaldoReal):
    with db.conectar() as con:
        servicos.informar_saldo(con, conta, body.valor, body.data)
        return {"ok": True}


class Categoria(BaseModel):
    nome: str = Field(..., min_length=2, max_length=60)
    grupo: str = Field(..., min_length=2, max_length=40)
    tipo: str = "gasto"
    teto: float | None = None
    fixa: bool = False


class CategoriaEdit(BaseModel):
    nome: str | None = None
    grupo: str | None = None
    cor: str | None = None
    teto: float | None = None
    fixa: bool | None = None
    orcar_por_itens: bool | None = None
    limpar_cor: bool = False
    limpar_teto: bool = False


def _slug(texto: str) -> str:
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40]


@app.post("/api/categorias", dependencies=[api])
def criar_categoria(body: Categoria):
    if body.tipo not in ("gasto", "renda"):
        raise HTTPException(400, "Tipo é gasto ou renda.")
    with db.conectar() as con:
        cid = _slug(body.nome)
        if con.execute("SELECT 1 FROM categorias WHERE id=?", (cid,)).fetchone():
            raise HTTPException(400, "Já existe uma categoria com esse nome.")
        ordem = con.execute("SELECT COALESCE(MAX(ordem),0)+1 FROM categorias").fetchone()[0]
        con.execute("INSERT INTO categorias (id, grupo, nome, tipo, teto, fixa, ordem) VALUES (?,?,?,?,?,?,?)",
                    (cid, body.grupo.strip(), body.nome.strip(), body.tipo, body.teto, int(body.fixa), ordem))
        return {"id": cid}


@app.put("/api/categorias/{cid}", dependencies=[api])
def editar_categoria(cid: str, body: CategoriaEdit):
    with db.conectar() as con:
        if not con.execute("SELECT 1 FROM categorias WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404)
        for campo in ("nome", "grupo", "cor"):
            if getattr(body, campo):
                con.execute(f"UPDATE categorias SET {campo}=? WHERE id=?", (getattr(body, campo).strip(), cid))
        if body.teto is not None or body.limpar_teto:
            con.execute("UPDATE categorias SET teto=? WHERE id=?", (None if body.limpar_teto else body.teto, cid))
        if body.fixa is not None:
            con.execute("UPDATE categorias SET fixa=? WHERE id=?", (int(body.fixa), cid))
        if body.orcar_por_itens is not None:
            con.execute("UPDATE categorias SET orcar_por_itens=? WHERE id=?", (int(body.orcar_por_itens), cid))
        if body.limpar_cor:
            con.execute("UPDATE categorias SET cor=NULL WHERE id=?", (cid,))
        return {"ok": True}


@app.delete("/api/categorias/{cid}", dependencies=[api])
def apagar_categoria(cid: str, mover_para: str | None = None):
    """Apaga a categoria. Se tiver lançamentos, eles passam para `mover_para` (mesmo tipo)."""
    with db.conectar() as con:
        orig = con.execute("SELECT tipo FROM categorias WHERE id=?", (cid,)).fetchone()
        if not orig:
            raise HTTPException(404)
        uso = con.execute("SELECT COUNT(*) FROM partes WHERE categoria=?", (cid,)).fetchone()[0]
        if uso:
            dest = con.execute("SELECT tipo FROM categorias WHERE id=?", (mover_para,)).fetchone() if mover_para else None
            if not dest or dest["tipo"] != orig["tipo"] or mover_para == cid:
                raise HTTPException(400, f"Em uso por {uso} lançamento(s): escolha outra categoria de {orig['tipo']} para recebê-los.")
            con.execute("UPDATE partes SET categoria=? WHERE categoria=?", (mover_para, cid))
            con.execute("UPDATE regras SET categoria=? WHERE categoria=?", (mover_para, cid))
            con.execute("UPDATE itens_fixos SET categoria=? WHERE categoria=?", (mover_para, cid))
        else:
            con.execute("DELETE FROM regras WHERE categoria=?", (cid,))
            con.execute("DELETE FROM itens_fixos WHERE categoria=?", (cid,))
        con.execute("DELETE FROM orcamento WHERE chave=?", (cid,))
        con.execute("DELETE FROM categorias WHERE id=?", (cid,))
        return {"ok": True, "movidos": uso}


class Meta(BaseModel):
    nome: str = Field(..., min_length=2, max_length=80)
    descricao: str = ""
    alvo: float | None = None
    data_alvo: str | None = None
    aporte_mensal: float = 0
    onde: str = ""
    ativa: bool = True


@app.get("/api/metas", dependencies=[api])
def listar_metas():
    with db.conectar() as con:
        return servicos.metas(con)


@app.post("/api/metas", dependencies=[api])
def criar_meta(body: Meta):
    with db.conectar() as con:
        cur = con.execute("INSERT INTO metas (nome, descricao, alvo, data_alvo, aporte_mensal, onde, ativa) VALUES (?,?,?,?,?,?,?)",
                          (body.nome, body.descricao, body.alvo, body.data_alvo or None, body.aporte_mensal, body.onde, int(body.ativa)))
        return {"id": cur.lastrowid}


@app.put("/api/metas/{mid}", dependencies=[api])
def editar_meta(mid: int, body: Meta):
    with db.conectar() as con:
        con.execute("UPDATE metas SET nome=?, descricao=?, alvo=?, data_alvo=?, aporte_mensal=?, onde=?, ativa=? WHERE id=?",
                    (body.nome, body.descricao, body.alvo, body.data_alvo or None, body.aporte_mensal, body.onde, int(body.ativa), mid))
        return {"ok": True}


@app.delete("/api/metas/{mid}", dependencies=[api])
def apagar_meta(mid: int):
    with db.conectar() as con:
        if con.execute("SELECT 1 FROM partes WHERE meta=?", (mid,)).fetchone():
            raise HTTPException(400, "A meta tem aportes ou resgates: desative em vez de apagar.")
        con.execute("DELETE FROM orcamento WHERE chave=?", (f"meta:{mid}",))
        con.execute("DELETE FROM metas WHERE id=?", (mid,))
        return {"ok": True}


class Orcamento(BaseModel):
    chave: str
    mes: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    valor: float | None = None
    ate_dezembro: bool = False


@app.get("/api/orcamento", dependencies=[api])
def ver_orcamento(ano: int | None = None):
    with db.conectar() as con:
        return servicos.grade_orcamento(con, ano or date.today().year)


@app.put("/api/orcamento", dependencies=[api])
def mudar_orcamento(body: Orcamento):
    with db.conectar() as con:
        existe = (con.execute("SELECT 1 FROM metas WHERE id=?", (body.chave[5:],)).fetchone() if body.chave.startswith("meta:")
                  else con.execute("SELECT 1 FROM categorias WHERE id=?", (body.chave,)).fetchone())
        if not existe:
            raise HTTPException(404, "Categoria ou meta não encontrada.")
        servicos.definir_orcamento(con, body.chave, body.mes, body.valor, body.ate_dezembro)
        return {"ok": True}


class ItemFixo(BaseModel):
    categoria: str
    nome: str = Field(..., min_length=1, max_length=80)
    valor: float
    inicio: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")
    fim: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")


def _checar_item(con, body: ItemFixo) -> None:
    c = con.execute("SELECT tipo FROM categorias WHERE id=?", (body.categoria,)).fetchone()
    if not c or c["tipo"] != "gasto":
        raise HTTPException(400, "Despesa fixa vai numa categoria de gasto.")
    if body.inicio and body.fim and body.fim < body.inicio:
        raise HTTPException(400, "O fim vem antes do início.")


@app.post("/api/itens-fixos", dependencies=[api])
def criar_item(body: ItemFixo):
    with db.conectar() as con:
        _checar_item(con, body)
        ordem = con.execute("SELECT COALESCE(MAX(ordem),0)+1 FROM itens_fixos").fetchone()[0]
        iid = con.execute("INSERT INTO itens_fixos (categoria, nome, valor, inicio, fim, ordem) VALUES (?,?,?,?,?,?)",
                          (body.categoria, body.nome.strip(), round(body.valor, 2), body.inicio, body.fim, ordem)).lastrowid
        return {"id": iid}


@app.put("/api/itens-fixos/{iid}", dependencies=[api])
def editar_item(iid: int, body: ItemFixo):
    with db.conectar() as con:
        _checar_item(con, body)
        if not con.execute("UPDATE itens_fixos SET categoria=?, nome=?, valor=?, inicio=?, fim=? WHERE id=?",
                           (body.categoria, body.nome.strip(), round(body.valor, 2), body.inicio, body.fim, iid)).rowcount:
            raise HTTPException(404)
        return {"ok": True}


@app.delete("/api/itens-fixos/{iid}", dependencies=[api])
def apagar_item(iid: int):
    with db.conectar() as con:
        con.execute("DELETE FROM itens_fixos WHERE id=?", (iid,))
        return {"ok": True}


class Evento(BaseModel):
    nome: str = Field(..., min_length=2, max_length=80)
    tipo: str
    inicio: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    fim: str | None = None
    valor: float
    ativo: bool = True


def _validar_evento(e: Evento) -> None:
    if e.tipo not in ("renda_mensal", "gasto_mensal", "entrada_unica", "saida_unica"):
        raise HTTPException(400, "Tipo de evento inválido.")
    if e.fim and e.fim < e.inicio:
        raise HTTPException(400, "O fim vem antes do início.")


@app.get("/api/eventos", dependencies=[api])
def listar_eventos():
    with db.conectar() as con:
        return [dict(r) for r in con.execute("SELECT * FROM eventos ORDER BY inicio, id")]


@app.post("/api/eventos", dependencies=[api])
def criar_evento(body: Evento):
    _validar_evento(body)
    with db.conectar() as con:
        cur = con.execute("INSERT INTO eventos (nome, tipo, inicio, fim, valor, ativo) VALUES (?,?,?,?,?,?)",
                          (body.nome, body.tipo, body.inicio, body.fim or None, body.valor, int(body.ativo)))
        return {"id": cur.lastrowid}


@app.put("/api/eventos/{eid}", dependencies=[api])
def editar_evento(eid: int, body: Evento):
    _validar_evento(body)
    with db.conectar() as con:
        con.execute("UPDATE eventos SET nome=?, tipo=?, inicio=?, fim=?, valor=?, ativo=? WHERE id=?",
                    (body.nome, body.tipo, body.inicio, body.fim or None, body.valor, int(body.ativo), eid))
        return {"ok": True}


@app.delete("/api/eventos/{eid}", dependencies=[api])
def apagar_evento(eid: int):
    with db.conectar() as con:
        con.execute("DELETE FROM eventos WHERE id=?", (eid,))
        return {"ok": True}


class Pessoa(BaseModel):
    nome: str = Field(..., min_length=2, max_length=60)
    tipo: str = "colega"
    apelido_extrato: str = ""
    sugere_entrada: str = "acerto"
    sugere_saida: str = "acerto"


@app.post("/api/pessoas", dependencies=[api])
def criar_pessoa(body: Pessoa):
    with db.conectar() as con:
        pid = _slug(body.nome)
        if con.execute("SELECT 1 FROM pessoas WHERE id=?", (pid,)).fetchone():
            raise HTTPException(400, "Já existe uma pessoa com esse nome.")
        con.execute("INSERT INTO pessoas (id, nome, tipo, apelido_extrato, sugere_entrada, sugere_saida) VALUES (?,?,?,?,?,?)",
                    (pid, body.nome.strip(), body.tipo, body.apelido_extrato.strip().upper(), body.sugere_entrada, body.sugere_saida))
        return {"id": pid}


@app.put("/api/pessoas/{pid}", dependencies=[api])
def editar_pessoa(pid: str, body: Pessoa):
    with db.conectar() as con:
        con.execute("UPDATE pessoas SET nome=?, tipo=?, apelido_extrato=?, sugere_entrada=?, sugere_saida=? WHERE id=?",
                    (body.nome.strip(), body.tipo, body.apelido_extrato.strip().upper(), body.sugere_entrada, body.sugere_saida, pid))
        return {"ok": True}


def _importar_um(nome: str, conteudo: bytes) -> dict:
    with db.conectar() as con:
        return servicos.importar(con, nome, conteudo)


@app.post("/api/importar", dependencies=[api])
async def importar(arquivos: list[UploadFile] = File(...)):
    resultados = []
    for a in arquivos:
        conteudo = await a.read()
        try:
            # Ler PDF (e o OCR da fatura do Bradesco) leva segundos: fora do laço, para o resto seguir respondendo.
            resultados.append(await asyncio.to_thread(_importar_um, a.filename or "arquivo", conteudo))
        except Exception as e:
            resultados.append({"arquivo": a.filename, "erro": str(e)})
    return resultados


@app.get("/api/importacoes", dependencies=[api])
def importacoes():
    with db.conectar() as con:
        return [dict(r) for r in con.execute("SELECT * FROM importacoes ORDER BY id DESC LIMIT 50")]


@app.get("/api/ignorados", dependencies=[api])
def ignorados():
    with db.conectar() as con:
        return [dict(r) for r in con.execute("SELECT * FROM ignorados ORDER BY id DESC LIMIT 100")]


@app.post("/api/ignorados/{iid}/resgatar", dependencies=[api])
def resgatar(iid: int):
    """Desfaz o filtro de ruído: relê o push como compra (o 'nada some em silêncio' do serviço original)."""
    from app.push_parser import forcar_compra
    with db.conectar() as con:
        row = con.execute("SELECT * FROM ignorados WHERE id=?", (iid,)).fetchone()
        if not row:
            raise HTTPException(404)
        parsed = forcar_compra(row["package"], row["title"], row["body"])
        if not parsed:
            raise HTTPException(400, "Sem valor legível nessa notificação.")
        conta = "nubank_cartao" if parsed.payment_method == "Crédito" else "nubank_conta"
        lid = servicos.inserir(con, conta, row["quando"][:10], -parsed.amount, parsed.merchant, origem="push",
                               ref=f"resgate:{iid}")
        con.execute("DELETE FROM ignorados WHERE id=?", (iid,))
        return {"id": lid}


@app.get("/api/parametros", dependencies=[api])
def parametros():
    with db.conectar() as con:
        return {r["chave"]: r["valor"] for r in con.execute("SELECT * FROM parametros")}


class Param(BaseModel):
    valor: str


@app.put("/api/parametros/{chave}", dependencies=[api])
def definir_param(chave: str, body: Param):
    if chave not in ("salario_mensal", "horizonte", "dia_renda_mes_seguinte", "renda_mes_seguinte", "taxa_ponte_picpay", "aluguel_rateio", "cores_grupos"):
        raise HTTPException(400, "Parâmetro não editável pelo site.")
    with db.conectar() as con:
        db.definir_parametro(con, chave, body.valor)
        return {"ok": True}


@app.get("/api/exportar.ods/estado", dependencies=[api])
def estado_modelo():
    motivo = exportar.ods_indisponivel()
    return {"disponivel": motivo is None, "motivo": motivo or ""}


@app.get("/api/exportar.ods", dependencies=[api])
def baixar_modelo():
    """A planilha antiga (Budget Dashboard, Planning, Tracking, Despesas Fixas) preenchida. Leva uns segundos."""
    with db.conectar() as con:
        modelo = exportar.dados_modelo(con)
    try:
        dados = exportar.planilha_modelo(modelo)
    except Exception as e:
        raise HTTPException(500, f"Não consegui gerar a planilha: {e}")
    nome = f"financas-{date.today().isoformat()}.ods"
    return Response(dados, media_type="application/vnd.oasis.opendocument.spreadsheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.get("/api/exportar.xlsx", dependencies=[api])
def baixar():
    with db.conectar() as con:
        dados = exportar.planilha(con)
    nome = f"financas-{date.today().isoformat()}.xlsx"
    return StreamingResponse(io.BytesIO(dados), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.get("/api/celular", dependencies=[api])
def celular():
    """O que o app Finanças e a macro do MacroDroid precisam, para copiar no celular já logado."""
    return {"base": settings.URL_PUBLICA, "chave": settings.API_KEY,
            "url": f"{settings.URL_PUBLICA}/api/v1/transaction/webhook", "authorization": f"Bearer {settings.API_KEY}",
            "corpo": '{"package":"{not_app_package}","title":"{not_title}","text":"{notification}"}'}


MIDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _papeis() -> Path:
    p = Path(settings.PAPEIS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


@app.get("/api/aparencia-conta", dependencies=[api])
def aparencia_conta():
    """No celular: a aparência da conta no servidor, trazida pela sincronização (vazia sem servidor)."""
    with db.conectar() as con:
        try:
            v = {r[0]: r[1] for r in con.execute(
                "SELECT chave, valor FROM sync_cliente WHERE chave IN ('aparencia', 'papel_servidor')")}
        except sqlite3.Error:
            v = {}
    return {"valores": json.loads(v.get("aparencia") or "{}"), "papel": v.get("papel_servidor", "")}


@app.get("/api/papeis", dependencies=[api])
def listar_papeis():
    with db.conectar() as con:
        atual = db.parametro(con, "papel_de_parede", "")
    return {"atual": atual, "papeis": sorted(f.name for f in _papeis().iterdir() if f.suffix.lower() in MIDIA)}


@app.post("/api/papeis", dependencies=[api])
async def enviar_papel(arquivo: UploadFile = File(...)):
    nome = Path(arquivo.filename or "papel.jpg").name
    if Path(nome).suffix.lower() not in MIDIA:
        raise HTTPException(400, "Use JPG, PNG ou WEBP.")
    dados = await arquivo.read()
    if len(dados) > 15 * 1024 * 1024:
        raise HTTPException(400, "Imagem acima de 15 MB.")
    (_papeis() / nome).write_bytes(dados)
    return {"nome": nome}


class Papel(BaseModel):
    nome: str


@app.put("/api/papeis/atual", dependencies=[api])
def escolher_papel(body: Papel):
    if body.nome and not (_papeis() / Path(body.nome).name).exists():
        raise HTTPException(404, "Papel de parede não encontrado.")
    with db.conectar() as con:
        db.definir_parametro(con, "papel_de_parede", Path(body.nome).name if body.nome else "")
    return {"ok": True}


@app.delete("/api/papeis/{nome}", dependencies=[api])
def apagar_papel(nome: str):
    (_papeis() / Path(nome).name).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/papel/{nome}", dependencies=[api])
def papel(nome: str):
    f = _papeis() / Path(nome).name
    if not f.exists() or f.suffix.lower() not in MIDIA:
        raise HTTPException(404)
    return FileResponse(f, media_type=MIDIA[f.suffix.lower()], headers={"Cache-Control": "private, max-age=604800"})


@app.get("/health")
def health():
    with db.conectar() as con:
        con.execute("SELECT 1 FROM contas LIMIT 1")
    return {"status": "ok", "fila": push.fila.qsize()}


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
