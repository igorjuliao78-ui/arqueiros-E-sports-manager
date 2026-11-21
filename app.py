import os, io, json, secrets
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

URL=os.getenv("DATABASE_URL","sqlite:///./arqueiros.db")
if URL.startswith("postgres://"): URL=URL.replace("postgres://","postgresql+psycopg://",1)
if URL.startswith("postgresql://"): URL=URL.replace("postgresql://","postgresql+psycopg://",1)
engine=create_engine(URL,connect_args={"check_same_thread":False} if URL.startswith("sqlite") else {},pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)
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
def send(chat,text):
 if BOT:requests.post("https://api.telegram.org/bot"+BOT+"/sendMessage",json={"chat_id":chat,"text":text},timeout=15).raise_for_status()
@app.post("/telegram/webhook")
async def telegram(request:Request,x_telegram_bot_api_secret_token:Optional[str]=Header(default=None)):
 if HOOK and not secrets.compare_digest(x_telegram_bot_api_secret_token or "",HOOK):raise HTTPException(403,"Webhook inválido")
 update=await request.json();msg=update.get("message",{});user=msg.get("from",{});chat=msg.get("chat",{}).get("id");uid=str(user.get("id",""));text=msg.get("text","").split()
 if not chat:return {"ok":True}
 if uid not in ADMINS:send(chat,"Acesso restrito: seu ID não está autorizado.");return {"ok":True}
 cmd=text[0].lower() if text else ""
 with SessionLocal() as s:
  d=dashboard(s)
  if cmd in ("/start","/help"):out="🏹 ARQUEIROS MANAGER\n/stats - resumo\n/jogadores - jogadores ativos\n/pendentes - resultados pendentes\n/ranking - classificação"
  elif cmd=="/stats":out=f"Jogadores: {d['players']}\nCompetições: {d['competitions']}\nPartidas aprovadas: {d['approved']}\nPendentes: {d['pending']}"
  elif cmd=="/jogadores":out=f"Jogadores ativos: {d['players']}"
  elif cmd=="/pendentes":
   rows=s.query(Match).filter(Match.status=="Pendente").all();out="\n".join(f"#{m.id} {m.home} x {m.away} ({m.home_score}:{m.away_score})" for m in rows) or "Nenhum resultado pendente."
  elif cmd=="/ranking":out="\n".join(f"{i}. {r['team']} — {r['PTS']} pts" for i,r in enumerate(d["ranking"],1)) or "Sem resultados aprovados."
  else:out="Comando não reconhecido. Use /help."
 send(chat,out);return {"ok":True}
