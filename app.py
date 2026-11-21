import os, io, json, secrets, re, unicodedata, difflib
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, String, Integer, Boolean, DateTime, ForeignKey, Text, inspect, text as sql_text
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
 photo_file_id:Mapped[Optional[str]]=mapped_column(String(255),nullable=True)
 active:Mapped[bool]=mapped_column(Boolean,default=True)
class Notice(Base):
 __tablename__="notices"
 id:Mapped[int]=mapped_column(primary_key=True)
 title:Mapped[str]=mapped_column(String(160))
 body:Mapped[str]=mapped_column(Text)
 created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Competition(Base):
 __tablename__="competitions"
 id:Mapped[int]=mapped_column(primary_key=True)
 name:Mapped[str]=mapped_column(String(120))
 kind:Mapped[str]=mapped_column(String(40),default="Liga")
 season:Mapped[str]=mapped_column(String(40),default="")
class Title(Base):
 __tablename__="titles"
 id:Mapped[int]=mapped_column(primary_key=True)
 name:Mapped[str]=mapped_column(String(120))
 competition_id:Mapped[Optional[int]]=mapped_column(ForeignKey("competitions.id"),nullable=True)
 season:Mapped[str]=mapped_column(String(40),default="")
 won_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
 notes:Mapped[str]=mapped_column(Text,default="")
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
with engine.begin() as conn:
 columns={x["name"] for x in inspect(engine).get_columns("players")}
 if "photo_file_id" not in columns: conn.execute(sql_text("ALTER TABLE players ADD COLUMN photo_file_id VARCHAR(255)"))
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
WEEKLY_TOKEN=os.getenv("WEEKLY_REPORT_TOKEN","")
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
 return {"players":s.query(Player).filter(Player.active.is_(True)).count(),"competitions":s.query(Competition).count(),"approved":s.query(Match).filter(Match.status=="Aprovado").count(),"pending":s.query(Match).filter(Match.status=="Pendente").count(),"titles":s.query(Title).count(),"ranking":ranking(s)}
@app.get("/health")
def health(): return {"status":"ok","service":"Arqueiros Manager"}
@app.get("/",response_class=HTMLResponse)
def home(request:Request,token:str=""):
 if not TOKEN or not secrets.compare_digest(token,TOKEN):
  return HTMLResponse("<h2>Arqueiros Manager</h2><p>Painel protegido. Configure ADMIN_PANEL_TOKEN e acesse /?token=SEU_TOKEN.</p>",status_code=401)
 with SessionLocal() as s:
  players=s.query(Player).order_by(Player.name).all()
  metrics={p.id:player_metrics(s,p) for p in players}
  return templates.TemplateResponse("index.html",{"request":request,"token":token,"data":dashboard(s),"players":players,"metrics":metrics,"comps":s.query(Competition).all(),"matches":s.query(Match).order_by(Match.id.desc()).limit(40).all(),"audits":s.query(Audit).order_by(Audit.id.desc()).limit(30).all(),"titles":s.query(Title).order_by(Title.won_at.desc()).all()})
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
@app.put("/api/players/{pid}")
async def update_player(pid:int,request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json();p=s.get(Player,pid)
 if not p:raise HTTPException(404,"Jogador não encontrado")
 old=p.name
 for key in ("name","nickname","position","team"):
  if key in d:setattr(p,key,str(d[key]).strip())
 if not p.name:raise HTTPException(400,"Nome obrigatório")
 if old!=p.name:s.query(MatchPlayerStat).filter(MatchPlayerStat.player_name==old).update({MatchPlayerStat.player_name:p.name})
 log(s,"player.updated",f"{old} -> {p.name}");s.commit();return {"ok":True}
@app.delete("/api/players/{pid}")
def delete_player(pid:int,s:Session=Depends(get_db),_:bool=Depends(auth)):
 p=s.get(Player,pid)
 if not p:raise HTTPException(404,"Jogador não encontrado")
 p.active=False;log(s,"player.deactivated",p.name);s.commit();return {"ok":True}
@app.put("/api/competitions/{cid}")
async def update_comp(cid:int,request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json();c=s.get(Competition,cid)
 if not c:raise HTTPException(404,"Competição não encontrada")
 c.name=d.get("name",c.name).strip();c.kind=d.get("kind",c.kind);c.season=d.get("season",c.season);log(s,"competition.updated",c.name);s.commit();return {"ok":True}
@app.delete("/api/competitions/{cid}")
def delete_comp(cid:int,s:Session=Depends(get_db),_:bool=Depends(auth)):
 c=s.get(Competition,cid)
 if not c:raise HTTPException(404,"Competição não encontrada")
 s.query(Match).filter(Match.competition_id==cid).update({Match.competition_id:None})
 s.query(Title).filter(Title.competition_id==cid).update({Title.competition_id:None})
 log(s,"competition.deleted",c.name);s.delete(c);s.commit();return {"ok":True}
@app.post("/api/titles")
async def add_title(request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json()
 if not d.get("name","").strip():raise HTTPException(400,"Nome do título obrigatório")
 t=Title(name=d["name"].strip(),competition_id=d.get("competition_id") or None,season=d.get("season",""),notes=d.get("notes",""))
 s.add(t);log(s,"title.won",t.name);s.commit();return {"ok":True,"id":t.id}
@app.delete("/api/titles/{tid}")
def delete_title(tid:int,s:Session=Depends(get_db),_:bool=Depends(auth)):
 t=s.get(Title,tid)
 if not t:raise HTTPException(404,"Título não encontrado")
 log(s,"title.deleted",t.name);s.delete(t);s.commit();return {"ok":True}
@app.get("/api/players/{pid}/stats")
def player_stats(pid:int,s:Session=Depends(get_db),_:bool=Depends(auth)):
 p=s.get(Player,pid)
 if not p:raise HTTPException(404,"Jogador não encontrado")
 return {"player":p.name,"stats":player_metrics(s,p)}
@app.get("/api/matches/{mid}/stats")
def get_match_stats(mid:int,s:Session=Depends(get_db),_:bool=Depends(auth)):
 m=s.get(Match,mid)
 if not m:raise HTTPException(404,"Confronto não encontrado")
 return {"match":{"id":m.id,"home":m.home,"away":m.away,"competition_id":m.competition_id},"stats":[{"id":x.id,"player_name":x.player_name,"opponent_name":x.opponent_name,"goals_for":x.goals_for,"goals_against":x.goals_against} for x in s.query(MatchPlayerStat).filter(MatchPlayerStat.match_id==mid).all()]}
@app.put("/api/match-stats/{sid}")
async def update_match_stat(sid:int,request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json();st=s.get(MatchPlayerStat,sid)
 if not st:raise HTTPException(404,"Estatística não encontrada")
 p=s.query(Player).filter(Player.active.is_(True),Player.name.ilike(str(d.get("player_name","")).strip())).first()
 if not p:raise HTTPException(400,"Selecione um jogador ativo cadastrado.")
 gf=d.get("goals_for");ga=d.get("goals_against")
 if gf is None or ga is None or int(gf)<0 or int(ga)<0:raise HTTPException(400,"Informe os dois placares.")
 st.player_name=p.name;st.opponent_name=str(d.get("opponent_name",st.opponent_name));st.goals_for=int(gf);st.goals_against=int(ga)
 log(s,"match.player_stat.corrected",f"match={st.match_id}; player={p.name}; {gf}x{ga}");s.commit();return {"ok":True}
@app.post("/api/matches")
async def add_match(request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json()
 if not d.get("home") or not d.get("away") or d["home"]==d["away"]:raise HTTPException(400,"Informe equipes diferentes")
 hs=int(d["home_score"]); aw=int(d["away_score"]); cid=d.get("competition_id") or None
 since=datetime.utcnow()-timedelta(hours=24)
 duplicate=s.query(Match).filter(Match.home==d["home"],Match.away==d["away"],Match.home_score==hs,Match.away_score==aw,Match.competition_id==cid,Match.created_at>=since,Match.status.in_(["Pendente","Aprovado"])).first()
 if duplicate:raise HTTPException(409,f"Possível confronto duplicado: registro #{duplicate.id} ({duplicate.status}). Confira antes de cadastrar novamente.")
 m=Match(home=d["home"],away=d["away"],home_score=hs,away_score=aw,competition_id=cid)
 s.add(m);log(s,"match.submitted",m.home+" x "+m.away);s.commit();return {"ok":True,"id":m.id}
@app.post("/api/matches/{mid}/{action}")
def match_action(mid:int,action:str,s:Session=Depends(get_db),_:bool=Depends(auth)):
 if action not in ("approve","reject"):raise HTTPException(400,"Ação inválida")
 m=s.get(Match,mid)
 if not m:raise HTTPException(404,"Partida não encontrada")
 if action=="approve" and m.home=="ARQUEIROS E-SPORTS":
  if not m.competition_id:raise HTTPException(400,"Associe uma competição antes de aprovar.")
  stats=s.query(MatchPlayerStat).filter(MatchPlayerStat.match_id==m.id).all()
  if not stats:raise HTTPException(400,"Nenhum placar individual reconhecido; envie novamente o print.")
  for st in stats:
   if st.goals_for is None or st.goals_against is None:raise HTTPException(400,"Há placar individual incompleto.")
   if not s.query(Player).filter(Player.active.is_(True),Player.name==st.player_name).first():raise HTTPException(400,"Jogador não reconhecido: "+st.player_name)
 if action=="approve" and (m.home_score is None or m.away_score is None):raise HTTPException(400,"Placar geral incompleto.")
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
@app.get("/api/competitions/{cid}/ranking")
def competition_ranking(cid:int,s:Session=Depends(get_db),_:bool=Depends(auth)):
 c=s.get(Competition,cid)
 if not c:raise HTTPException(404,"Competição não encontrada")
 table={}
 for m in s.query(Match).filter(Match.competition_id==cid,Match.status=="Aprovado").all():
  for team,gf,ga in [(m.home,m.home_score,m.away_score),(m.away,m.away_score,m.home_score)]:
   x=table.setdefault(team,{"team":team,"J":0,"V":0,"E":0,"D":0,"GP":0,"GC":0,"SG":0,"PTS":0})
   x["J"]+=1;x["GP"]+=gf or 0;x["GC"]+=ga or 0
   if gf>ga:x["V"]+=1;x["PTS"]+=3
   elif gf==ga:x["E"]+=1;x["PTS"]+=1
   else:x["D"]+=1
   x["SG"]=x["GP"]-x["GC"]
 return {"competition":c.name,"ranking":sorted(table.values(),key=lambda x:(-x["PTS"],-x["SG"],-x["GP"],x["team"]))}
@app.get("/api/reports/monthly")
def monthly_report(month:str="",s:Session=Depends(get_db),_:bool=Depends(auth)):
 try: start=datetime.strptime(month or datetime.utcnow().strftime("%Y-%m"),"%Y-%m")
 except ValueError:raise HTTPException(400,"Use mês no formato AAAA-MM")
 end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
 matches=s.query(Match).filter(Match.status=="Aprovado",Match.created_at>=start,Match.created_at<end).all()
 wins=sum(1 for m in matches if m.home=="ARQUEIROS E-SPORTS" and (m.home_score or 0)>(m.away_score or 0))
 draws=sum(1 for m in matches if m.home=="ARQUEIROS E-SPORTS" and m.home_score==m.away_score)
 losses=sum(1 for m in matches if m.home=="ARQUEIROS E-SPORTS" and (m.home_score or 0)<(m.away_score or 0))
 return {"month":start.strftime("%Y-%m"),"matches":len(matches),"wins":wins,"draws":draws,"losses":losses,"goals_for":sum(m.home_score or 0 for m in matches if m.home=="ARQUEIROS E-SPORTS"),"goals_against":sum(m.away_score or 0 for m in matches if m.home=="ARQUEIROS E-SPORTS")}
@app.get("/api/notices")
def list_notices(s:Session=Depends(get_db),_:bool=Depends(auth)):
 return [{"id":n.id,"title":n.title,"body":n.body,"created_at":n.created_at.isoformat()} for n in s.query(Notice).order_by(Notice.id.desc()).limit(30).all()]
@app.post("/api/notices")
async def create_notice(request:Request,s:Session=Depends(get_db),_:bool=Depends(auth)):
 d=await request.json();title=str(d.get("title","")).strip();body=str(d.get("body","")).strip()
 if not title or not body:raise HTTPException(400,"Informe título e comunicado")
 n=Notice(title=title,body=body);s.add(n);log(s,"notice.created",title);s.commit()
 group=os.getenv("TEAM_CHAT_ID","").strip();sent=False
 if group and BOT:
  try:requests.post("https://api.telegram.org/bot"+BOT+"/sendMessage",json={"chat_id":group,"text":"📢 "+title+"\\n\\n"+body},timeout=15).raise_for_status();sent=True
  except Exception:sent=False
 return {"ok":True,"id":n.id,"telegram_sent":sent,"message":"Comunicado salvo"+(" e enviado ao grupo." if sent else ". Configure TEAM_CHAT_ID para enviar ao grupo do Telegram.")}
@app.delete("/api/notices/{nid}")
def delete_notice(nid:int,s:Session=Depends(get_db),_:bool=Depends(auth)):
 n=s.get(Notice,nid)
 if not n:raise HTTPException(404,"Comunicado não encontrado")
 log(s,"notice.deleted",n.title);s.delete(n);s.commit();return {"ok":True}
@app.get("/api/export")
def export(s:Session=Depends(get_db),_:bool=Depends(auth)):
 return {"players":[{"name":p.name,"nickname":p.nickname,"position":p.position,"team":p.team,"active":p.active} for p in s.query(Player).all()],"competitions":[{"name":c.name,"kind":c.kind,"season":c.season} for c in s.query(Competition).all()],"matches":[{"home":m.home,"away":m.away,"home_score":m.home_score,"away_score":m.away_score,"status":m.status} for m in s.query(Match).all()],"titles":[{"name":t.name,"season":t.season,"notes":t.notes} for t in s.query(Title).all()],"exported_at":datetime.now(timezone.utc).isoformat()}
@app.get("/api/cards/ranking.png")
def card(s:Session=Depends(get_db),_:bool=Depends(auth)):
 rows=ranking(s)[:10];fig,ax=plt.subplots(figsize=(9,max(3,1+len(rows)*.5)));fig.patch.set_facecolor("#111827");ax.set_facecolor("#111827")
 if rows:
  bars=ax.barh([r["team"] for r in rows][::-1],[r["PTS"] for r in rows][::-1],color="#d9a441");ax.bar_label(bars,color="white",padding=4)
 else:ax.text(.5,.5,"Sem resultados aprovados",ha="center",color="white",transform=ax.transAxes)
 ax.set_title("ARQUEIROS E-SPORTS | RANKING",color="white");ax.tick_params(colors="white");ax.set_xlabel("Pontos",color="white")
 for sp in ax.spines.values():sp.set_visible(False)
 fig.tight_layout();buf=io.BytesIO();fig.savefig(buf,format="png",dpi=150,facecolor=fig.get_facecolor());plt.close(fig);buf.seek(0);return StreamingResponse(buf,media_type="image/png")
TEAM_RED="#b51f2b";TEAM_DARK="#09090d";TEAM_METAL="#b8b8c0"
def card_image(title,lines):
 fig,ax=plt.subplots(figsize=(10,max(3,1+len(lines)*.42)));fig.patch.set_facecolor(TEAM_DARK);ax.set_facecolor(TEAM_DARK);ax.axis("off")
 ax.add_patch(plt.Rectangle((0,0),1,.055,transform=ax.transAxes,color=TEAM_RED))
 ax.add_patch(plt.Rectangle((0,.94),1,.06,transform=ax.transAxes,color=TEAM_RED))
 ax.text(.05,.90,"🏹 ARQUEIROS E-SPORTS",transform=ax.transAxes,color=TEAM_METAL,fontsize=10,fontweight="bold",va="top")
 ax.text(.05,.80,title,transform=ax.transAxes,color="white",fontsize=19,fontweight="bold",va="top")
 y=.68;step=.62/max(len(lines),1)
 for line in lines:ax.text(.06,y,str(line),transform=ax.transAxes,color="white",fontsize=11,va="top",wrap=True);y-=step
 fig.tight_layout(pad=1.5);buf=io.BytesIO();fig.savefig(buf,format="png",dpi=150,facecolor=fig.get_facecolor());plt.close(fig);buf.seek(0);return buf
def player_metrics(s,p):
 games=s.query(MatchPlayerStat).join(Match,Match.id==MatchPlayerStat.match_id).filter(MatchPlayerStat.player_name==p.name,Match.status=="Aprovado").all()
 played=[g for g in games if g.goals_for is not None and g.goals_against is not None]
 wins=sum(g.goals_for>g.goals_against for g in played);draws=sum(g.goals_for==g.goals_against for g in played);losses=len(played)-wins-draws
 return {"games":len(played),"wins":wins,"draws":draws,"losses":losses,"goals":sum(g.goals_for or 0 for g in played),"conceded":sum(g.goals_against or 0 for g in played)}
def weekly_player_image(p,metrics):
 fig=plt.figure(figsize=(8,5),facecolor=TEAM_DARK);ax=fig.add_axes([0,0,1,1]);ax.set_facecolor(TEAM_DARK);ax.axis("off")
 ax.add_patch(plt.Rectangle((0,.94),1,.06,color=TEAM_RED,transform=ax.transAxes))
 ax.add_patch(plt.Rectangle((0,0),1,.035,color=TEAM_RED,transform=ax.transAxes))
 # Avatar ilustrado: inicial do jogador quando não há foto cadastrada.
 avatar=None
 if p.photo_file_id:
  try:
   meta=requests.get("https://api.telegram.org/bot"+BOT+"/getFile",params={"file_id":p.photo_file_id},timeout=15).json()
   if meta.get("ok"):
    path=meta["result"]["file_path"];raw=requests.get("https://api.telegram.org/file/bot"+BOT+"/"+path,timeout=20).content
    avatar=Image.open(io.BytesIO(raw)).convert("RGB")
  except Exception: avatar=None
 if avatar is not None:
  ia=fig.add_axes([.36,.52,.28,.38]);ia.imshow(avatar);ia.axis("off")
 else:
  ax.add_patch(plt.Circle((.5,.70),.14,color="#292930",transform=ax.transAxes,ec=TEAM_METAL,lw=2))
  ax.text(.5,.70,(p.name[:1] or "?").upper(),ha="center",va="center",color="white",fontsize=38,fontweight="bold",transform=ax.transAxes)
 ax.text(.5,.46,p.name.upper(),ha="center",color="white",fontsize=22,fontweight="bold",transform=ax.transAxes)
 ax.text(.5,.38,"DESEMPENHO INDIVIDUAL",ha="center",color=TEAM_METAL,fontsize=11,transform=ax.transAxes)
 labels=[("JOGOS",metrics["games"]),("VITÓRIAS",metrics["wins"]),("EMPATES",metrics["draws"]),("DERROTAS",metrics["losses"]),("GOLS MARCADOS",metrics["goals"]),("GOLS SOFRIDOS",metrics["conceded"])]
 for i,(label,value) in enumerate(labels):
  x=.18+(i%3)*.32;y=.25-(i//3)*.12
  ax.text(x,y,label,ha="center",color=TEAM_METAL,fontsize=9,transform=ax.transAxes)
  ax.text(x,y-.055,str(value),ha="center",color="white",fontsize=18,fontweight="bold",transform=ax.transAxes)
 ax.text(.5,.06,"ARQUEIROS E-SPORTS  •  RELATÓRIO SEMANAL",ha="center",color=TEAM_RED,fontsize=10,fontweight="bold",transform=ax.transAxes)
 buf=io.BytesIO();fig.savefig(buf,format="png",dpi=160,facecolor=fig.get_facecolor());plt.close(fig);buf.seek(0);return buf
@app.post("/internal/weekly-cards")
def weekly_cards(x_weekly_token:Optional[str]=Header(default=None)):
 if not WEEKLY_TOKEN or not secrets.compare_digest(x_weekly_token or "",WEEKLY_TOKEN):raise HTTPException(403,"Token de relatório inválido")
 if not BOT or not ADMINS:raise HTTPException(503,"Configure o bot e os administradores")
 sent=0
 with SessionLocal() as s:
  players=s.query(Player).filter(Player.active.is_(True)).order_by(Player.name).all()
  cards=[(p.name,weekly_player_image(p,player_metrics(s,p))) for p in players]
 for admin in ADMINS:
  for name,buf in cards:
   requests.post("https://api.telegram.org/bot"+BOT+"/sendPhoto",data={"chat_id":admin,"caption":"🏹 Relatório semanal — "+name},files={"photo":(f"player-{name}.png",buf.getvalue(),"image/png")},timeout=30).raise_for_status()
   sent+=1
 return {"ok":True,"players":len(cards),"cards_sent":sent}

def send(chat,text,menu=False,keyboard=None):
 if not BOT:return
 buf=card_image("ARQUEIROS E-SPORTS",str(text).splitlines() or [" "])
 requests.post("https://api.telegram.org/bot"+BOT+"/sendPhoto",data={"chat_id":chat,"caption":"🏹 "+str(text)[:900]},files={"photo":("arqueiros.png",buf.getvalue(),"image/png")},timeout=30).raise_for_status()
 keyboard=keyboard or ([[{"text":"📊 Estatísticas"},{"text":"👥 Jogadores"}],[{"text":"⏳ Pendentes"},{"text":"🏆 Ranking"}],[{"text":"➕ Adicionar jogador"},{"text":"🏅 Adicionar competição"}],[{"text":"✏️ Editar jogador"},{"text":"🗑️ Excluir jogador"}],[{"text":"📋 Competições"},{"text":"🪪 Card do jogador"}],[{"text":"❔ Ajuda"},{"text":"⬅️ Fechar menu"}]] if menu else [[{"text":"🏹 MENU"}]])
 payload={"chat_id":chat,"text":"🏹 Menu aberto. Escolha uma opção:" if menu else "🏹 Toque em MENU para abrir as opções.","reply_markup":{"keyboard":keyboard,"resize_keyboard":True,"is_persistent":True}}
 requests.post("https://api.telegram.org/bot"+BOT+"/sendMessage",json=payload,timeout=15).raise_for_status()
def normalize_name(value):
 value=unicodedata.normalize("NFKD",value).encode("ascii","ignore").decode().casefold()
 return re.sub(r"[^a-z0-9]","",value)
def parse_duel_ocr(text):
 lines=[re.sub(r"\s+"," ",x).strip() for x in text.splitlines() if x.strip()]
 scores=[];stats=[];team="Equipe adversária"
 for line in lines:
  m=re.search(r"CL[ÃA]O?\s*:?\s*(\d+)\b",line,re.I)
  if m:scores.append(int(m.group(1)))
  t=re.search(r"ARQUEIROS\s+E-SPORTS\s*[x×]\s*(.+)",line,re.I)
  if t:team=t.group(1).strip()
  # Aceita jogador com ou sem numeração: "1. ALVIN 1 x 1 ADV".
  m=re.match(r"^\s*(?:\d+\s*[.)➤>»:-]?\s*)?(.+?)\s+(\d+)\s*[x×]\s*(\d+)(?:\s+(.+))?$",line,re.I)
  if m:
   player=m.group(1).strip(" •➤».-:")
   if normalize_name(player) not in ("titulares","placar","cla","federacaomng","arquieroseports"):
    stats.append({"player":player,"gf":int(m.group(2)),"ga":int(m.group(3)),"opponent":(m.group(4) or "").strip()})
 return {"team":team,"scores":scores,"stats":stats}
def process_duel_photo(chat,file_id):
 try:
  meta=requests.get("https://api.telegram.org/bot"+BOT+"/getFile",params={"file_id":file_id},timeout=20).json()
  if not meta.get("ok"):raise ValueError("Imagem não localizada")
  path=meta["result"]["file_path"];raw=requests.get("https://api.telegram.org/file/bot"+BOT+"/"+path,timeout=30).content
  text=pytesseract.image_to_string(Image.open(io.BytesIO(raw)).convert("RGB"),lang="por+eng",config="--psm 6")
  parsed=parse_duel_ocr(text)
  if not parsed["stats"]:
   send(chat,"Não consegui reconhecer jogadores e placares individuais. Envie um print nítido com a descrição completa.");return
  with SessionLocal() as s:
   comps=s.query(Competition).order_by(Competition.id.desc()).all()
   comp=None
   m=Match(competition_id=comp.id if comp else None,home="ARQUEIROS E-SPORTS",away=parsed["team"],home_score=parsed["scores"][0] if len(parsed["scores"])>0 else None,away_score=parsed["scores"][1] if len(parsed["scores"])>1 else None,status="Pendente")
   s.add(m);s.flush()
   known={normalize_name(p.name):p.name for p in s.query(Player).filter(Player.active.is_(True)).all()}
   unmatched=[]
   for row in parsed["stats"]:
    key=normalize_name(row["player"])
    if key in known:row["player"]=known[key]
    else:
     best=difflib.get_close_matches(key,list(known),n=1,cutoff=.82)
     if best:row["player"]=known[best[0]]
     else:unmatched.append(row["player"])
    s.add(MatchPlayerStat(match_id=m.id,player_name=row["player"],opponent_name=row["opponent"],goals_for=row["gf"],goals_against=row["ga"]))
   log(s,"duel.ocr.pending",f"#{m.id}");s.commit();mid=m.id
  lines=[f"CONFRONTO #{mid} — {parsed['team']}",f"Placar dos clãs: {parsed['scores'][0] if len(parsed['scores'])>0 else '?'} x {parsed['scores'][1] if len(parsed['scores'])>1 else '?'}","Jogadores:"]
  for row in parsed["stats"]:lines.append(f"{row['player']} — {row['gf']} x {row['ga']}")
  if unmatched:lines.append("NOMES NÃO RECONHECIDOS: "+", ".join(unmatched)+" — não aprove até corrigir.")
  if comp:lines.append("Competição associada: "+comp.name)
  elif len(comps)>1:
   COMPETITION_PICK_STATE[str(chat)]=mid
   lines.append("Qual competição corresponde a este confronto? Responda com o nome exatamente como aparece no cadastro.")
  elif len(comps)==1:
   COMPETITION_PICK_STATE[str(chat)]=mid
   lines.append("Confirme a competição deste confronto respondendo exatamente: "+comps[0].name)
  else:
   COMPETITION_PICK_STATE[str(chat)]=mid
   lines.append("Ainda não há competição cadastrada. Use 🏅 Adicionar competição; depois informe o nome dela para associar este confronto.")
  lines.append(f"Para aprovar: /aprovar {mid} | rejeitar: /rejeitar {mid}")
  send(chat,"\n".join(lines),menu=True)
 except Exception as e:
  send(chat,"Falha na leitura da imagem. Tente novamente com mais nitidez. "+str(e)[:120])
PLAYER_ADD_STATE={}
PLAYER_EDIT_STATE={}
PLAYER_CARD_STATE=set()
COMPETITION_ADD_STATE=set()
COMPETITION_PICK_STATE={}
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
 cmd={"📊 Estatísticas":"/stats","👥 Jogadores":"/jogadores","⏳ Pendentes":"/pendentes","🏆 Ranking":"/ranking","➕ Adicionar jogador":"/addplayer","🏅 Adicionar competição":"/addcompetition","✏️ Editar jogador":"/editplayer","🗑️ Excluir jogador":"/deleteplayer","📋 Competições":"/competitions","🪪 Card do jogador":"/playercard","❔ Ajuda":"/help","🏹 Menu":"/menu","🏹 MENU":"/menu","⬅️ Fechar menu":"/closemenu","📷 Alterar foto":"/foto","🗑️ Retirar da equipe":"/excluir","⏭️ Pular foto":"/pular","❌ Cancelar":"/cancelar","✅ Confirmar exclusão":"EXCLUIR"}.get(cmd,cmd)
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
  state=PLAYER_ADD_STATE.get(uid) or PLAYER_EDIT_STATE.get(uid)
  if state and state.get("action")=="photo":
   with SessionLocal() as s:
    p=s.get(Player,state["player_id"])
    if p:p.photo_file_id=msg["photo"][-1]["file_id"];log(s,"player.photo.updated",p.name);s.commit();out=f"Foto de {p.name} atualizada!"
    else:out="Jogador não encontrado."
   PLAYER_ADD_STATE.pop(uid,None);PLAYER_EDIT_STATE.pop(uid,None);send(chat,out,menu=True);return {"ok":True}
  process_duel_photo(chat,msg["photo"][-1]["file_id"]);return {"ok":True}
 if uid in PLAYER_ADD_STATE:
  state=PLAYER_ADD_STATE[uid];value=raw_text.strip()
  if state.get("action")=="name" and value and not value.startswith("/"):
   with SessionLocal() as s:
    exists=s.query(Player).filter(Player.name.ilike(value)).first()
    if exists:PLAYER_ADD_STATE.pop(uid,None);send(chat,f"⚠️ {value} já está cadastrado.",menu=True)
    else:
     p=Player(name=value);s.add(p);log(s,"player.created.telegram",value);s.commit();PLAYER_ADD_STATE[uid]={"action":"photo","player_id":p.id}
     send(chat,f"Jogador {value} cadastrado. Envie a foto ou escolha pular para usar o ícone padrão.",menu=True,keyboard=[[{"text":"⏭️ Pular foto"}],[{"text":"❌ Cancelar"}]])
   return {"ok":True}
  if state.get("action")=="photo" and value=="/pular":
   PLAYER_ADD_STATE.pop(uid,None);send(chat,"Cadastro concluído. O jogador ficará com ícone até receber uma foto.",menu=True);return {"ok":True}
 if uid in PLAYER_CARD_STATE and cmd=="/cancelar":
  PLAYER_CARD_STATE.discard(uid);send(chat,"Solicitação de card cancelada.",menu=True);return {"ok":True}
 if uid in PLAYER_CARD_STATE and raw_text and not raw_text.startswith("/"):
  with SessionLocal() as s:
   p=s.query(Player).filter(Player.name.ilike(raw_text.strip()),Player.active.is_(True)).first()
   if not p:
    send(chat,"Não encontrei esse jogador ativo. Confira o nome e tente novamente, ou toque em ❌ Cancelar.",menu=True,keyboard=[[{"text":"❌ Cancelar"}]])
    return {"ok":True}
   metrics=player_metrics(s,p);buf=weekly_player_image(p,metrics);name=p.name
  requests.post("https://api.telegram.org/bot"+BOT+"/sendPhoto",data={"chat_id":chat,"caption":"🏹 Card individual — "+name},files={"photo":("arqueiros-"+str(name)+".png",buf.getvalue(),"image/png")},timeout=30).raise_for_status()
  PLAYER_CARD_STATE.discard(uid);send(chat,"Card de "+name+" enviado.",menu=True);return {"ok":True}
 if uid in PLAYER_EDIT_STATE:
  state=PLAYER_EDIT_STATE[uid];value=raw_text.strip()
  if state.get("action")=="lookup" and value and not value.startswith("/"):
   with SessionLocal() as s:
    p=s.query(Player).filter(Player.name.ilike(value),Player.active.is_(True)).first()
    if not p:send(chat,"Não encontrei esse jogador. Digite o nome novamente ou /cancelar.");return {"ok":True}
    PLAYER_EDIT_STATE[uid]={"action":"selected","player_id":p.id};send(chat,f"Selecionado: {p.name}. Escolha uma opção ou digite o novo nome:",menu=True,keyboard=[[{"text":"📷 Alterar foto"},{"text":"🗑️ Retirar da equipe"}],[{"text":"❌ Cancelar"}]])
   return {"ok":True}
  if state.get("action")=="selected":
   with SessionLocal() as s:
    p=s.get(Player,state["player_id"])
    if not p:PLAYER_EDIT_STATE.pop(uid,None);send(chat,"Jogador não encontrado.",menu=True);return {"ok":True}
    if value=="/foto":PLAYER_EDIT_STATE[uid]={"action":"photo","player_id":p.id};send(chat,f"Envie a nova foto de {p.name}.")
    elif value=="/excluir":PLAYER_EDIT_STATE[uid]={"action":"delete_confirm","player_id":p.id};send(chat,f"Confirme a retirada de {p.name}:",menu=True,keyboard=[[{"text":"✅ Confirmar exclusão"}],[{"text":"❌ Cancelar"}]])
    elif value=="/cancelar":PLAYER_EDIT_STATE.pop(uid,None);send(chat,"Edição cancelada.",menu=True)
    elif value and not value.startswith("/"):
     old=p.name;p.name=value;s.query(MatchPlayerStat).filter(MatchPlayerStat.player_name==old).update({MatchPlayerStat.player_name:value});log(s,"player.renamed",old+" -> "+value);s.commit();PLAYER_EDIT_STATE.pop(uid,None);send(chat,f"Jogador atualizado: {value}.",menu=True)
   return {"ok":True}
  if state.get("action")=="delete_confirm":
   if value.upper()=="EXCLUIR":
    with SessionLocal() as s:
     p=s.get(Player,state["player_id"]);p.active=False;log(s,"player.deactivated",p.name);s.commit();name=p.name
    PLAYER_EDIT_STATE.pop(uid,None);send(chat,f"{name} foi retirado da equipe. O histórico de estatísticas foi preservado.",menu=True)
   else:send(chat,"Digite EXCLUIR para confirmar ou /cancelar.")
   return {"ok":True}
 if str(chat) in COMPETITION_PICK_STATE and raw_text and not raw_text.startswith("/") and uid in ADMINS:
  with SessionLocal() as s:
   comp=s.query(Competition).filter(Competition.name.ilike(raw_text.strip())).first()
   mid=COMPETITION_PICK_STATE[str(chat)]
   m=s.get(Match,mid)
   if comp and m and m.status=="Pendente":
    m.competition_id=comp.id;log(s,"match.competition.assigned",f"#{mid}: {comp.name}");s.commit()
    COMPETITION_PICK_STATE.pop(str(chat),None)
    send(chat,f"Competição {comp.name} associada ao confronto #{mid}. Agora confira os jogadores e os placares antes de aprovar com /aprovar {mid}.",menu=True)
   else:
    send(chat,"Não encontrei essa competição cadastrada. Confira o nome ou use 🏅 Adicionar competição.",menu=True)
  return {"ok":True}
 if uid in COMPETITION_ADD_STATE and raw_text and not raw_text.startswith("/"):
  with SessionLocal() as s:
   comp=Competition(name=raw_text.strip(),kind="Competição");s.add(comp);log(s,"competition.created.telegram",comp.name);s.commit();name=comp.name
  COMPETITION_ADD_STATE.discard(uid)
  pending_id=COMPETITION_PICK_STATE.get(str(chat))
  if pending_id:
   with SessionLocal() as s:
    m=s.get(Match,pending_id)
    if m and m.status=="Pendente":m.competition_id=s.query(Competition).filter(Competition.name==name).first().id;s.commit()
   COMPETITION_PICK_STATE.pop(str(chat),None)
   send(chat,f"Competição {name} cadastrada e associada ao confronto #{pending_id}. Confira os dados e aprove com /aprovar {pending_id}.",menu=True)
  else:send(chat,f"Competição {name} cadastrada!",menu=True)
  return {"ok":True}
 if cmd=="/cancelar":
  PLAYER_ADD_STATE.pop(uid,None);PLAYER_EDIT_STATE.pop(uid,None);PLAYER_CARD_STATE.discard(uid);COMPETITION_ADD_STATE.discard(uid);send(chat,"Operação cancelada.",menu=True);return {"ok":True}
 if cmd=="/addplayer":
  PLAYER_ADD_STATE[uid]={"action":"name"};send(chat,"➕ Adicionar jogador\nEnvie o nome do jogador.");return {"ok":True}
 if cmd=="/addcompetition":
  COMPETITION_ADD_STATE.add(uid);send(chat,"🏅 Adicionar competição\nEnvie o nome da competição.");return {"ok":True}
 if cmd=="/playercard":
  if uid not in ADMINS:
   send(chat,"Apenas administradores podem solicitar cards individuais.")
   return {"ok":True}
  PLAYER_CARD_STATE.add(uid);send(chat,"🪪 Card do jogador\nDigite o nome do jogador para gerar o card atualizado.",menu=True,keyboard=[[{"text":"❌ Cancelar"}]]);return {"ok":True}
 if cmd=="/editplayer":
  PLAYER_EDIT_STATE[uid]={"action":"lookup"};send(chat,"✏️ Editar jogador\nDigite o nome atual do jogador.");return {"ok":True}
 if cmd=="/deleteplayer":
  PLAYER_EDIT_STATE[uid]={"action":"lookup"};send(chat,"🗑️ Excluir jogador\nDigite o nome do jogador que deseja retirar da equipe.");return {"ok":True}
 if cmd=="/competitions":
  with SessionLocal() as s:
   rows=s.query(Competition).order_by(Competition.name).all()
   out="\n".join(f"• {x.name} ({x.kind})" for x in rows) or "Nenhuma competição cadastrada."
  send(chat,out,menu=True);return {"ok":True}
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
 if cmd=="/closemenu":
  send(chat,"Menu recolhido. Use o botão fixo 🏹 MENU para abrir as opções.")
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
    wins=sum(1 for x in played if x.goals_for>x.goals_against);draws=sum(1 for x in played if x.goals_for==x.goals_against);losses=len(played)-wins-draws
    lines.append(f"• {p.name} — {len(played)} jogos | {wins}V {draws}E {losses}D | {sum(x.goals_for or 0 for x in played)} gols | {sum(x.goals_against or 0 for x in played)} sofridos")
   out="\n".join(lines) or "Nenhum jogador cadastrado."
  elif cmd=="/pendentes":
   rows=s.query(Match).filter(Match.status=="Pendente").order_by(Match.id).all()
   out="\n".join(f"#{m.id} {m.home} {m.home_score} x {m.away_score} {m.away}" for m in rows) or "Nenhum resultado pendente."
  elif cmd in ("/aprovar","/rejeitar"):
   if len(parts)!=2 or not parts[1].isdigit():out=f"Uso: {cmd} ID (consulte /pendentes)"
   else:
    m=s.get(Match,int(parts[1]))
    if not m:out="Resultado não encontrado."
    elif m.status!="Pendente":out=f"Esse resultado já está: {m.status}."
    elif cmd=="/aprovar" and (m.home_score is None or m.away_score is None):out="Não é possível aprovar: o placar geral dos dois clãs precisa estar preenchido na descrição."
    elif cmd=="/aprovar" and not m.competition_id:out="Não é possível aprovar: falta associar este confronto a uma competição."
    elif cmd=="/aprovar" and s.query(MatchPlayerStat).filter(MatchPlayerStat.match_id==m.id).count()==0:out="Não é possível aprovar: nenhum placar individual foi reconhecido."
    elif cmd=="/aprovar" and any(not s.query(Player).filter(Player.active.is_(True),Player.name==st.player_name).first() for st in s.query(MatchPlayerStat).filter(MatchPlayerStat.match_id==m.id).all()):out="Não é possível aprovar: há jogador não reconhecido. Corrija o nome antes de confirmar."
    else:
     m.status="Aprovado" if cmd=="/aprovar" else "Rejeitado"
     log(s,"match."+m.status.lower(),m.id);s.commit()
     out=f"Resultado #{m.id} {m.status.lower()} com sucesso."
  elif cmd=="/ranking":out="\n".join(f"{i}. {r['team']} — {r['PTS']} pts" for i,r in enumerate(d["ranking"],1)) or "Sem resultados aprovados."
  else:out="Comando não reconhecido. Use /help."
 send(chat,out,menu=True);return {"ok":True}
