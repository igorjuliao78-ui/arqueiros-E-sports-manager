import os, io, json, secrets, re, unicodedata, difflib
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
import pytesseract
from PIL import Image

URL=os.getenv("DATABASE_URL","sqlite:///./arqueiros.db")
if URL.startswith("postgres://"): URL=URL.replace("postgres://","postgresql+psycopg2://",1)
if URL.startswith("postgresql://"): URL=URL.replace("postgresql://","postgresql+psycopg2://",1)
engine=create_engine(URL,connect_args={"check_same_thread":False} if URL.startswith("sqlite") else {},pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)
ROSTER=["Jesus「ΔΩŘ」","Carlos","CDS","SM7","Jackson","Rony","Julião","Wellinson","Guiih S.","Jefferson","Marinhoox","Diogo Lima","Miquéias","Eltom Pereira","Joab Junior","Ezequiel","Brunno Bass","Davi","Trinity","Adriel","Vitor","Pereira","Léo","Mateus","Gustavo"]
class Base(DeclarativeBase): pass
class Player(Base):
 __tablename__="players"
 id:Mapped[int]=mapped_column(primary_key=True)
 name:Mapped[str]=mapped_column(String(100))
 nickname:Mapped[str]=mapped_column(String(100),default="")
 position:Mapped[str]=mapped_column(String(50),default="")
 team:Mapped[str]=mapped_column(String(100),default="")
 active:Mapped[bool]=mapped_column(Boolean,default=True)
class Competition(Base):
 __tablename__="competitions"
 id:Mapped[int]=mapped_column(primary_key=True)
 name:Mapped[str]=mapped_column(String(120))
 kind:Mapped[str]=mapped_column(String(40),default="Liga")
 season:Mapped[str]=mapped_column(String(40),default="")
class Match(Base):
 __tablename__="matches"
 id:Mapped[int]=mapped_column(primary_key=True)
 competition_id:Mapped[Optional[int]]=mapped_column(ForeignKey("competitions.id"),nullable=True)
 home:Mapped[str]=mapped_column(String(100))
 away:Mapped[str]=mapped_column(String(100))
 home_score:Mapped[Optional[int]]=mapped_column(Integer,nullable=True)
 away_score:Mapped[Optional[int]]=mapped_column(Integer,nullable=True)
 status:Mapped[str]=mapped_column(String(30),default="Pendente")
 created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class MatchPlayerStat(Base):
 __tablename__="match_player_stats"
 id:Mapped[int]=mapped_column(primary_key=True)
 match_id:Mapped[int]=mapped_column(ForeignKey("matches.id"))
 player_name:Mapped[str]=mapped_column(String(100))
 opponent_name:Mapped[str]=mapped_column(String(100),default="")
 goals_for:Mapped[Optional[int]]=mapped_column(Integer,nullable=True)
 goals_against:Mapped[Optional[int]]=mapped_column(Integer,nullable=True)
class Discipline(Base):
 __tablename__="discipline"
 id:Mapped[int]=mapped_column(primary_key=True)
 player:Mapped[str]=mapped_column(String(100))
 reason:Mapped[str]=mapped_column(Text)
 sanction:Mapped[str]=mapped_column(String(120),default="")
class Recruit(Base):
 __tablename__="recruitment"
 id:Mapped[int]=mapped_column(primary_key=True)
 nickname:Mapped[str]=mapped_column(String(100))
 position:Mapped[str]=mapped_column(String(50),default="")
 contact:Mapped[str]=mapped_column(String(120),default="")
 status:Mapped[str]=mapped_column(String(30),default="Novo")
class Audit(Base):
 __tablename__="audit"
 id:Mapped[int]=mapped_column(primary_key=True)
 actor:Mapped[str]=mapped_column(String(80))
 action:Mapped[str]=mapped_column(String(100))
 detail:Mapped[str]=mapped_column(Text,default="")
 created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
Base.metadata.create_all(engine)
with SessionLocal() as s:
 existing={p.name.casefold() for p in s.query(Player).all()}
 for player_name in ROSTER:
  if player_name.casefold() not in existing:
   s.add(Player(name=player_name))
 s.commit()
app=FastAPI(title="Arqueiros Manager",version="1.0.0")
os.makedirs("static",exist_ok=True)
app.mount("/static",StaticFiles(directory="static"),name="static")
templates=Jinja2Templates(directory="templates")
TOKEN=os.getenv("ADMIN_PANEL_TOKEN","")
BOT=os.getenv("TELEGRAM_BOT_TOKEN","")
ADMINS={x.strip() for x in os.getenv("TELEGRAM_ADMIN_IDS","").split(",") if x.strip()}
HOOK=os.getenv("TELEGRAM_WEBHOOK_SECRET","")
def get_db():
 s=SessionLocal()
 try: yield s
 finally: s.close()
def auth(request:Request):
 if not TOKEN: raise HTTPException(503,"Configure ADMIN_PANEL_TOKEN.")
 supplied=request.query_params.get("token") or request.headers.get("x-admin-token","")
 if not secrets.compare_digest(supplied,TOKEN): raise HTTPException(401,"Acesso não autorizado.")
 return True
def log(s,action,detail=""):
 s.add(Audit(actor="admin",action=action,detail=str(detail)[:2000]))
def ranking(s):
 table={}
 for m in s.query(Match).filter(Match.status=="Aprovado").all():
  for team,gf,ga in [(m.home,m.home_score,m.away_score),(m.away,m.away_score,m.home_score)]:
   t=table.setdefault(team,{"team":team,"J":0,"V":0,"E":0,"D":0,"GP":0,"GC":0,"SG":0,"PTS":0})
   t["J"]+=1;t["GP"]+=gf;t["GC"]+=ga
   if gf>ga:t["V"]+=1;t["PTS"]+=3
   elif gf==ga:t["E"]+=1;t["PTS"]+=1
   else:t["D"]+=1
   t["SG"]=t["GP"]-t["GC"]
 return sorted(table.values(),key=lambda x:(-x["PTS"],-x["SG"],-x["GP"],x["team"]))
def dashboard(s):
 return {"players":s.query(Player).filter(Player.active.is_(True)).count(),"competitions":s.query(Competition).count(),"approved":s.query(Match).filter(Match.status=="Aprovado").count(),"pending":s.query(Match).filter(Match.status=="Pendente").count(),"ranking":ranking(s)}
@app.get("/health")
def health(): return {"status":"ok","service":"Arqueiros Manager"}
@app.get("/",response_class=HTMLResponse)
def home(request:Request,token:str=""):
 if not TOKEN or not secrets.compare_digest(token,TOKEN):
  return HTMLResponse("<h2>Arqueiros Manager</h2><p>Painel protegido. Configure ADMIN_PANEL_TOKEN e acesse /?token=SEU_TOKEN.</p>",status_code=401)
 with SessionLocal() as s:
  return templates.TemplateResponse("index.html",{"request":request,"token":token,"data":dashboard(s),"players":s.query(Player).order_by(Player.name).all(),"comps":s.query(Competition).all(),"matches":s.query(Match).order_by(Match.id.desc()).limit(40).all(),"audits":s.query(Audit).order_by(Audit.id.desc()).limit(15).all()})
@app.get("/api/dashboard")
def api_dashboard(s:Session=Depends(get_db),_:bool=Depends(auth)): return dashboard(s)
@app.post("/api/players")
async def add_player(request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json()
 if not d.get("name","").strip(): raise HTTPException(400,"Nome obrigatório")
 p=Player(name=d["name"].strip(),nickname=d.get("nickname",""),position=d.get("position",""),team=d.get("team",""))
 s.add(p);log(s,"player.created",p.name);s.commit();return {"ok":True,"id":p.id}
@app.post("/api/competitions")
async def add_comp(request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json()
 if not d.get("name","").strip():raise HTTPException(400,"Nome obrigatório")
 c=Competition(name=d["name"],kind=d.get("kind","Liga"),season=d.get("season",""))
 s.add(c);log(s,"competition.created",c.name);s.commit();return {"ok":True,"id":c.id}
@app.post("/api/matches")
async def add_match(request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json()
 if not d.get("home") or not d.get("away") or d["home"]==d["away"]:raise HTTPException(400,"Informe equipes diferentes")
 m=Match(home=d["home"],away=d["away"],home_score=int(d["home_score"]),away_score=int(d["away_score"]),competition_id=d.get("competition_id") or None)
 s.add(m);log(s,"match.submitted",m.home+" x "+m.away);s.commit();return {"ok":True,"id":m.id}
@app.post("/api/matches/{mid}/{action}")
def match_action(mid:int,action:str,s:Session=Depends(get_db),_:bool=Depends(auth)):
 if action not in ("approve","reject"):raise HTTPException(400,"Ação inválida")
 m=s.get(Match,mid)
 if not m:raise HTTPException(404,"Partida não encontrada")
 m.status="Aprovado" if action=="approve" else "Rejeitado";log(s,"match."+m.status.lower(),mid);s.commit();return {"ok":True}
@app.post("/api/discipline")
async def add_discipline(request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json()
 if not d.get("player") or not d.get("reason"):raise HTTPException(400,"Informe jogador e motivo")
 s.add(Discipline(player=d["player"],reason=d["reason"],sanction=d.get("sanction","")));log(s,"discipline.created",d["player"]);s.commit();return {"ok":True}
@app.post("/api/recruitment")
async def add_recruit(request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json()
 if not d.get("nickname"):raise HTTPException(400,"Nick obrigatório")
 s.add(Recruit(nickname=d["nickname"],position=d.get("position",""),contact=d.get("contact","")));log(s,"recruit.created",d["nickname"]);s.commit();return {"ok":True}
@app.get("/api/export")
def export(s:Session=Depends(get_db),_:bool=Depends(auth)):
 return {"players":[{"name":p.name,"nickname":p.nickname,"position":p.position,"team":p.team,"active":p.active} for p in s.query(Player).all()],"competitions":[{"name":c.name,"kind":c.kind,"season":c.season} for c in s.query(Competition).all()],"matches":[{"home":m.home,"away":m.away,"home_score":m.home_score,"away_score":m.away_score,"status":m.status} for m in s.query(Match).all()],"exported_at":datetime.now(timezone.utc).isoformat()}
@app.get("/api/cards/ranking.png")
def card(s:Session=Depends(get_db),_:bool=Depends(auth)):
 rows=ranking(s)[:10];fig,ax=plt.subplots(figsize=(9,max(3,1+len(rows)*.5)));fig.patch.set_facecolor("#111827");ax.set_facecolor("#111827")
 if rows:
  bars=ax.barh([r["team"] for r in rows][::-1],[r["PTS"] for r in rows][::-1],color="#d9a441");ax.bar_label(bars,color="white",padding=4)
 else:ax.text(.5,.5,"Sem resultados aprovados",ha="center",color="white",transform=ax.transAxes)
 ax.set_title("ARQUEIROS E-SPORTS | RANKING",color="white");ax.tick_params(colors="white");ax.set_xlabel("Pontos",color="white")
 for sp in ax.spines.values():sp.set_visible(False)
 fig.tight_layout();buf=io.BytesIO();fig.savefig(buf,format="png",dpi=150,facecolor=fig.get_facecolor());plt.close(fig);buf.seek(0);return StreamingResponse(buf,media_type="image/png")
def card_image(title,lines):
 fig,ax=plt.subplots(figsize=(10,max(3,1+len(lines)*.42)));fig.patch.set_facecolor("#101827");ax.set_facecolor("#101827");ax.axis("off")
 ax.text(.05,.94,title,transform=ax.transAxes,color="#f2c66d",fontsize=19,fontweight="bold",va="top")
 y=.82
 for line in lines:ax.text(.06,y,str(line),transform=ax.transAxes,color="white",fontsize=12,va="top",wrap=True);y-=.075
 fig.tight_layout(pad=1.5);buf=io.BytesIO();fig.savefig(buf,format="png",dpi=150,facecolor=fig.get_facecolor());plt.close(fig);buf.seek(0);return buf
def send(chat,text,menu=False):
 if not BOT:return
 buf=card_image("ARQUEIROS E-SPORTS",str(text).splitlines() or [" "])
 requests.post("https://api.telegram.org/bot"+BOT+"/sendPhoto",data={"chat_id":chat,"caption":"🏹 "+str(text)[:900]},files={"photo":("arqueiros.png",buf.getvalue(),"image/png")},timeout=30).raise_for_status()
 if menu:
  payload={"chat_id":chat,"text":"🏹 Menu de opções","reply_markup":{"keyboard":[[{"text":"📊 Estatísticas"},{"text":"👥 Jogadores"}],[{"text":"⏳ Pendentes"},{"text":"🏆 Ranking"}],[{"text":"➕ Adicionar jogador"},{"text":"📥 Cadastrar elenco"}],[{"text":"❔ Ajuda"},{"text":"🏹 Menu"}]],"resize_keyboard":True}}
  requests.post("https://api.telegram.org/bot"+BOT+"/sendMessage",json=payload,timeout=15).raise_for_status()
def normalize_name(value):
 value=unicodedata.normalize("NFKD",value).encode("ascii","ignore").decode().casefold()
 return re.sub(r"[^a-z0-9]","",value)
def parse_duel_ocr(text):
 lines=[re.sub(r"\\s+"," ",x).strip() for x in text.splitlines() if x.strip()];scores=[];stats=[];team="Equipe adversária"
 for line in lines:
  m=re.search(r"CL[AÃ]O?\\s*:?\\s*(\\d+)",line,re.I)
  if m:scores.append(int(m.group(1)))
  t=re.search(r"ARQUEIROS\\s+E-SPORTS\\s*[x×]\\s*(.+)",line,re.I)
  if t:team=t.group(1).strip()
  m=re.match(r"^\\s*\\d+\\s*[➤>».-]?\\s*(.+?)\\s+(?:(\\d+)\\s*[x×]\\s*(\\d+)|[x×])\\s*(.*)$",line,re.I)
  if m:
   player=m.group(1).strip(" •➤».-")
   if normalize_name(player) not in ("titulares","placar","cla","federacaomng"):
    stats.append({"player":player,"gf":int(m.group(2)) if m.group(2) else None,"ga":int(m.group(3)) if m.group(3) else None,"opponent":(m.group(4) or "").strip()})
 return {"team":team,"scores":scores,"stats":stats}
def process_duel_photo(chat,file_id):
 try:
  meta=requests.get("https://api.telegram.org/bot"+BOT+"/getFile",params={"file_id":file_id},timeout=20).json()
  if not meta.get("ok"):raise ValueError("Imagem não localizada")
  path=meta["result"]["file_path"];raw=requests.get("https://api.telegram.org/file/bot"+BOT+"/"+path,timeout=30).content
  text=pytesseract.image_to_string(Image.open(io.BytesIO(raw)).convert("RGB"),lang="por+eng",config="--psm 6")
  parsed=parse_duel_ocr(text)
  if not parsed["stats"]:send(chat,"Não consegui reconhecer os jogadores e placares. Envie uma imagem nítida mostrando toda a descrição.");return
  with SessionLocal() as s:
   m=Match(home="ARQUEIROS E-SPORTS",away=parsed["team"],home_score=parsed["scores"][0] if len(parsed["scores"])>0 else None,away_score=parsed["scores"][1] if len(parsed["scores"])>1 else None,status="Pendente");s.add(m);s.flush()
   known={normalize_name(p.name):p.name for p in s.query(Player).filter(Player.active.is_(True)).all()};unmatched=[]
   for row in parsed["stats"]:
    best=difflib.get_close_matches(normalize_name(row["player"]),list(known),n=1,cutoff=.78)
    if best:row["player"]=known[best[0]]
    else:unmatched.append(row["player"])
    s.add(MatchPlayerStat(match_id=m.id,player_name=row["player"],opponent_name=row["opponent"],goals_for=row["gf"],goals_against=row["ga"]))
   log(s,"duel.ocr.pending",f"#{m.id}");s.commit();mid=m.id
  lines=[f"CONFRONTO #{mid} — {parsed['team']}",f"Placar dos clãs: {parsed['scores'][0] if len(parsed['scores'])>0 else '?'} x {parsed['scores'][1] if len(parsed['scores'])>1 else '?'}","Jogadores:"]
  for row in parsed["stats"]:lines.append(f"{row['player']} — "+(f"{row['gf']} x {row['ga']}" if row["gf"] is not None and row["ga"] is not None else "PENDENTE"))
  if unmatched:lines.append("Conferir nomes: "+", ".join(unmatched))
  lines.append(f"Para confirmar: /aprovar {mid} | descartar: /rejeitar {mid}");send(chat,"\\n".join(lines),menu=True)
 except Exception as e:send(chat,"Falha na leitura da imagem. Tente novamente com mais nitidez. "+str(e)[:120])
PLAYER_ADD_STATE=set()
ROSTER=["Jesus「ΔΩŘ」","Carlos","CDS","SM7","Jackson","Rony","Julião","Wellinson","Guiih S.","Jefferson","Marinhoox","Diogo Lima","Miquéias","Eltom Pereira","Joab Junior","Ezequiel","Brunno Bass","Davi","Trinity","Adriel","Vitor","Pereira","Léo","Mateus","Gustavo"]
@app.post("/telegram/webhook")
async def telegram(request:Request,x_telegram_bot_api_secret_token:Optional[str]=Header(default=None)):
 if HOOK and not secrets.compare_digest(x_telegram_bot_api_secret_token or "",HOOK):raise HTTPException(403,"Webhook inválido")
 update=await request.json()
 if update.get("callback_query"):
  cq=update["callback_query"];cqchat=cq.get("message",{}).get("chat",{}).get("id");cquid=str(cq.get("from",{}).get("id",""));data=cq.get("data","")
  if cquid in ADMINS and data.startswith(("approve_duel:","reject_duel:")):
   action,mid=data.split(":");mid=int(mid)
   with SessionLocal() as s:
    m=s.get(Match,mid)
    if m and m.status=="Pendente":m.status="Aprovado" if action=="approve_duel" else "Rejeitado";log(s,"match."+m.status.lower(),mid);s.commit();send(cqchat,f"Confronto #{mid} {m.status.lower()}.",menu=True)
  requests.post("https://api.telegram.org/bot"+BOT+"/answerCallbackQuery",json={"callback_query_id":cq["id"]},timeout=10)
  return {"ok":True}
 msg=update.get("message",{});user=msg.get("from",{});chat=msg.get("chat",{}).get("id");uid=str(user.get("id",""));raw_text=msg.get("text","").strip();parts=raw_text.split()
 if not chat:return {"ok":True}
 cmd=raw_text.split("@")[0].lower() if raw_text.startswith("/") else raw_text
 cmd={"📊 Estatísticas":"/stats","👥 Jogadores":"/jogadores","⏳ Pendentes":"/pendentes","🏆 Ranking":"/ranking","➕ Adicionar jogador":"/addplayer","📥 Cadastrar elenco":"/addroster","❔ Ajuda":"/help","🏹 Menu":"/menu"}.get(cmd,cmd)
 # /id e /start são públicos para facilitar a configuração inicial; os demais comandos exigem autorização.
 if cmd=="/id":
  send(chat,f"Seu ID do Telegram é: {uid}\nEnvie esse número ao administrador para liberar o acesso.")
  return {"ok":True}
 if cmd=="/start":
  if uid in ADMINS:
   send(chat,"🏹 ARQUEIROS E-SPORTS MANAGER\nEscolha uma opção nos botões abaixo.",menu=True)
  else:
   send(chat,"🏹 ARQUEIROS E-SPORTS MANAGER\nPara liberar comandos administrativos, envie seu ID ao responsável. Use /id para consultar seu ID.")
  return {"ok":True}
 if uid not in ADMINS:
  send(chat,"Acesso restrito. Use /id e peça ao administrador para liberar seu usuário.")
  return {"ok":True}
 if msg.get("photo"):
  if uid not in ADMINS:send(chat,"Acesso restrito.");return {"ok":True}
  process_duel_photo(chat,msg["photo"][-1]["file_id"]);return {"ok":True}
 if uid in PLAYER_ADD_STATE and not cmd.startswith("/"):
  name=msg.get("text","").strip()
  if not name:
   send(chat,"Envie o nome ou apelido do jogador.")
   return {"ok":True}
  with SessionLocal() as s:
   exists=s.query(Player).filter(Player.name.ilike(name)).first()
   if exists:
    out=f"⚠️ {name} já está cadastrado."
   else:
    p=Player(name=name)
    s.add(p);log(s,"player.created.telegram",name);s.commit()
    out=f"✅ Jogador {name} cadastrado com sucesso!"
  PLAYER_ADD_STATE.discard(uid)
  send(chat,out,menu=True)
  return {"ok":True}
 if cmd=="/addplayer":
  PLAYER_ADD_STATE.add(uid)
  send(chat,"➕ Adicionar jogador\nAgora envie o nome ou apelido do jogador.")
  return {"ok":True}
 if cmd=="/addroster":
  added=[];skipped=[]
  with SessionLocal() as s:
   existing={p.name.casefold() for p in s.query(Player).all()}
   for name in ROSTER:
    if name.casefold() in existing:
     skipped.append(name)
    else:
     s.add(Player(name=name));added.append(name)
   if added:
    log(s,"roster.imported",", ".join(added));s.commit()
  out=f"📥 Cadastro do elenco concluído!\nAdicionados: {len(added)}\nJá existentes: {len(skipped)}\nTotal na lista: {len(ROSTER)}"
  if skipped:out+="\n\nJá estavam cadastrados: "+", ".join(skipped)
  send(chat,out,menu=True)
  return {"ok":True}
 if cmd=="/menu":
  send(chat,"🏹 Menu principal. Escolha uma opção:",menu=True)
  return {"ok":True}
 with SessionLocal() as s:
  d=dashboard(s)
  if cmd in ("/help","/comandos"):
   out="🏹 ARQUEIROS MANAGER\nUse os botões do menu ou os comandos:\n/stats - resumo geral\n/jogadores - lista de jogadores ativos\n/pendentes - resultados aguardando aprovação\n/aprovar ID - aprova resultado\n/rejeitar ID - rejeita resultado\n/ranking - classificação\n/menu - abrir botões"
  elif cmd=="/stats":out=f"Jogadores: {d['players']}\nCompetições: {d['competitions']}\nPartidas aprovadas: {d['approved']}\nPendentes: {d['pending']}"
  elif cmd=="/jogadores":
   rows=s.query(Player).filter(Player.active.is_(True)).order_by(Player.name).all();lines=[]
   for p in rows:
    games=s.query(MatchPlayerStat).join(Match,Match.id==MatchPlayerStat.match_id).filter(MatchPlayerStat.player_name==p.name,Match.status=="Aprovado").all()
    played=[x for x in games if x.goals_for is not None and x.goals_against is not None]
    lines.append(f"• {p.name} — {len(played)} jogos | {sum(x.goals_for or 0 for x in played)} gols | {sum(x.goals_against or 0 for x in played)} sofridos")
   out="\\n".join(lines) or "Nenhum jogador cadastrado."
  elif cmd=="/pendentes":
   rows=s.query(Match).filter(Match.status=="Pendente").order_by(Match.id).all()
   out="\n".join(f"#{m.id} {m.home} {m.home_score} x {m.away_score} {m.away}" for m in rows) or "Nenhum resultado pendente."
  elif cmd in ("/aprovar","/rejeitar"):
   if len(parts)!=2 or not parts[1].isdigit():out=f"Uso: {cmd} ID (consulte /pendentes)"
   else:
    m=s.get(Match,int(parts[1]))
    if not m:out="Resultado não encontrado."
    elif m.status!="Pendente":out=f"Esse resultado já está: {m.status}."
    else:
     m.status="Aprovado" if cmd=="/aprovar" else "Rejeitado"
     log(s,"match."+m.status.lower(),m.id);s.commit()
     out=f"Resultado #{m.id} {m.status.lower()} com sucesso."
  elif cmd=="/ranking":out="\n".join(f"{i}. {r['team']} — {r['PTS']} pts" for i,r in enumerate(d["ranking"],1)) or "Sem resultados aprovados."
  else:out="Comando não reconhecido. Use /help."
 send(chat,out,menu=True);return {"ok":True}
