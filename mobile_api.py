import base64, hashlib, hmac, json, os, secrets, time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, Session

from app import (
    Base, engine, SessionLocal, get_db, TOKEN, Player, Competition, Match,
    MatchPlayerStat, Title, Notice, Discipline, Recruit, Audit, dashboard,
    player_metrics, ranking, log, match_approval_error
)

router = APIRouter(prefix="/api/mobile", tags=["Aplicativo Android"])

AUTH_SECRET = os.getenv("MOBILE_AUTH_SECRET") or TOKEN
TOKEN_TTL = 60 * 60 * 24 * 14


class MobileUser(Base):
    __tablename__ = "mobile_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="member")
    player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


MobileUser.__table__.create(bind=engine, checkfirst=True)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _password_hash(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240000)
    return _b64(salt) + "$" + _b64(derived)


def _password_ok(password: str, encoded: str) -> bool:
    try:
        salt_s, _ = encoded.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_s + "=" * (-len(salt_s) % 4))
        return hmac.compare_digest(_password_hash(password, salt), encoded)
    except Exception:
        return False


def _issue_token(user_id: int, username: str, role: str, player_id=None) -> str:
    if not AUTH_SECRET:
        raise HTTPException(503, "Configure ADMIN_PANEL_TOKEN ou MOBILE_AUTH_SECRET.")
    payload = {"sub": user_id, "username": username, "role": role,
               "player_id": player_id, "exp": int(time.time()) + TOKEN_TTL}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return body + "." + signature


def _decode_token(token: str):
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(401, "Sessão inválida ou expirada. Entre novamente.")


def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Autenticação necessária.")
    return _decode_token(authorization.split(" ", 1)[1].strip())


def admin_only(user=Depends(current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Ação disponível somente para administradores.")
    return user


def _player(p):
    return {"id": p.id, "name": p.name, "nickname": p.nickname, "position": p.position,
            "team": p.team, "active": p.active, "status": p.status or ("Ativo" if p.active else "Desligado"),
            "telegram_chat_id": p.telegram_chat_id}


def _competition(c):
    return {"id": c.id, "name": c.name, "kind": c.kind, "season": c.season}


def _match(m, s):
    comp = s.get(Competition, m.competition_id) if m.competition_id else None
    return {"id": m.id, "competition_id": m.competition_id, "competition": comp.name if comp else None,
            "home": m.home, "away": m.away, "home_score": m.home_score,
            "away_score": m.away_score, "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None}


def _title(t, s):
    p = s.get(Player, t.player_id) if t.player_id else None
    c = s.get(Competition, t.competition_id) if t.competition_id else None
    return {"id": t.id, "name": t.name, "season": t.season, "notes": t.notes,
            "player_id": t.player_id, "player": p.name if p else None,
            "competition_id": t.competition_id, "competition": c.name if c else None,
            "won_at": t.won_at.isoformat() if t.won_at else None}


@router.post("/auth/login")
async def mobile_login(request: Request, s: Session = Depends(get_db)):
    d = await request.json()
    username = str(d.get("username", "")).strip()
    password = str(d.get("password", ""))
    if not username or not password:
        raise HTTPException(400, "Informe usuário e senha.")
    if username.casefold() == "admin" and TOKEN and hmac.compare_digest(password, TOKEN):
        token = _issue_token(0, "admin", "admin")
        return {"access_token": token, "token_type": "bearer",
                "user": {"username": "admin", "role": "admin", "name": "Administrador"}}
    user = s.query(MobileUser).filter(MobileUser.username.ilike(username), MobileUser.active.is_(True)).first()
    if not user or not _password_ok(password, user.password_hash):
        raise HTTPException(401, "Usuário ou senha incorretos.")
    player = s.get(Player, user.player_id) if user.player_id else None
    token = _issue_token(user.id, user.username, user.role, user.player_id)
    return {"access_token": token, "token_type": "bearer",
            "user": {"username": user.username, "role": user.role,
                     "name": player.name if player else user.username, "player_id": user.player_id}}


@router.get("/me")
def mobile_me(user=Depends(current_user), s: Session = Depends(get_db)):
    player = s.get(Player, user.get("player_id")) if user.get("player_id") else None
    return {"username": user.get("username"), "role": user.get("role"),
            "name": player.name if player else user.get("username"),
            "player_id": user.get("player_id")}


@router.get("/bootstrap")
def mobile_bootstrap(user=Depends(current_user), s: Session = Depends(get_db)):
    is_admin = user.get("role") == "admin"
    players = [p for p in s.query(Player).order_by(Player.name).all()
               if (p.name or "").strip().casefold() not in {"cancelar", "❌ cancelar"}]
    comps = s.query(Competition).order_by(Competition.name).all()
    matches = s.query(Match).order_by(Match.created_at.desc(), Match.id.desc()).limit(200).all()
    titles = s.query(Title).order_by(Title.won_at.desc()).all()
    notices = s.query(Notice).order_by(Notice.created_at.desc()).all()
    result = {
        "user": mobile_me(user, s),
        "dashboard": dashboard(s),
        "players": [_player(p) for p in players],
        "competitions": [_competition(c) for c in comps],
        "matches": [_match(m, s) for m in matches],
        "titles": [_title(t, s) for t in titles],
        "notices": [{"id": n.id, "title": n.title, "body": n.body,
                     "created_at": n.created_at.isoformat() if n.created_at else None} for n in notices],
        "rankings": ranking(s),
        "admin": is_admin
    }
    if is_admin:
        result["discipline"] = [{"id": x.id, "player": x.player, "reason": x.reason, "sanction": x.sanction}
                                for x in s.query(Discipline).order_by(Discipline.id.desc()).all()]
        result["recruitment"] = [{"id": x.id, "nickname": x.nickname, "position": x.position,
                                  "contact": x.contact, "status": x.status}
                                 for x in s.query(Recruit).order_by(Recruit.id.desc()).all()]
        result["audit"] = [{"id": x.id, "actor": x.actor, "action": x.action, "detail": x.detail,
                            "created_at": x.created_at.isoformat() if x.created_at else None}
                           for x in s.query(Audit).order_by(Audit.id.desc()).limit(100).all()]
        result["users"] = [{"id": x.id, "username": x.username, "role": x.role,
                            "player_id": x.player_id, "active": x.active}
                           for x in s.query(MobileUser).order_by(MobileUser.username).all()]
    return result


@router.get("/players/{pid}/stats")
def mobile_player_stats(pid: int, competition_id: Optional[int] = None,
                        user=Depends(current_user), s: Session = Depends(get_db)):
    p = s.get(Player, pid)
    if not p:
        raise HTTPException(404, "Jogador não encontrado.")
    return {"player": _player(p), "stats": player_metrics(s, p, competition_id)}


@router.post("/users")
async def mobile_create_user(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    username = str(d.get("username", "")).strip()
    password = str(d.get("password", ""))
    role = str(d.get("role", "member"))
    player_id = d.get("player_id") or None
    if len(username) < 3 or len(password) < 8:
        raise HTTPException(400, "Usuário deve ter 3 caracteres e senha no mínimo 8.")
    if role not in ("admin", "member"):
        raise HTTPException(400, "Perfil inválido.")
    if s.query(MobileUser).filter(MobileUser.username.ilike(username)).first():
        raise HTTPException(409, "Esse usuário já existe.")
    if player_id and not s.get(Player, int(player_id)):
        raise HTTPException(404, "Jogador não encontrado.")
    row = MobileUser(username=username, password_hash=_password_hash(password),
                     role=role, player_id=int(player_id) if player_id else None)
    s.add(row)
    log(s, "mobile.user.created", username + " (" + role + ")")
    s.commit()
    return {"ok": True, "id": row.id}


@router.put("/users/{uid}/active")
async def mobile_user_active(uid: int, request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    row = s.get(MobileUser, uid)
    if not row:
        raise HTTPException(404, "Usuário não encontrado.")
    row.active = bool(d.get("active"))
    log(s, "mobile.user.status", row.username + ": " + str(row.active))
    s.commit()
    return {"ok": True}


@router.post("/players")
async def mobile_add_player(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    name = str(d.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "Nome obrigatório.")
    p = Player(name=name, nickname=str(d.get("nickname", "")), position=str(d.get("position", "")),
               team=str(d.get("team", "")), telegram_chat_id=str(d.get("telegram_chat_id", "")).strip() or None)
    s.add(p); log(s, "player.created.mobile", name); s.commit()
    return {"ok": True, "id": p.id}


@router.put("/players/{pid}")
async def mobile_update_player(pid: int, request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json(); p = s.get(Player, pid)
    if not p: raise HTTPException(404, "Jogador não encontrado.")
    old = p.name
    for key in ("name", "nickname", "position", "team", "telegram_chat_id"):
        if key in d: setattr(p, key, str(d[key]).strip())
    if not p.name: raise HTTPException(400, "Nome obrigatório.")
    if old != p.name:
        s.query(MatchPlayerStat).filter(MatchPlayerStat.player_name == old).update({MatchPlayerStat.player_name: p.name})
    log(s, "player.updated.mobile", old + " -> " + p.name); s.commit()
    return {"ok": True}


@router.put("/players/{pid}/status")
async def mobile_player_status(pid: int, request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json(); status = str(d.get("status", "")).strip()
    if status not in ("Ativo", "Reserva", "Afastado", "Desligado"):
        raise HTTPException(400, "Status inválido.")
    p = s.get(Player, pid)
    if not p: raise HTTPException(404, "Jogador não encontrado.")
    p.status = status; p.active = status != "Desligado"
    log(s, "player.status.mobile", p.name + ": " + status); s.commit()
    return {"ok": True}


@router.post("/competitions")
async def mobile_add_competition(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json(); name = str(d.get("name", "")).strip()
    if not name: raise HTTPException(400, "Nome obrigatório.")
    c = Competition(name=name, kind=str(d.get("kind", "Liga")), season=str(d.get("season", "")))
    s.add(c); log(s, "competition.created.mobile", name); s.commit()
    return {"ok": True, "id": c.id}


@router.put("/competitions/{cid}")
async def mobile_update_competition(cid: int, request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json(); c = s.get(Competition, cid)
    if not c: raise HTTPException(404, "Competição não encontrada.")
    c.name = str(d.get("name", c.name)).strip(); c.kind = str(d.get("kind", c.kind))
    c.season = str(d.get("season", c.season)); log(s, "competition.updated.mobile", c.name); s.commit()
    return {"ok": True}


@router.delete("/competitions/{cid}")
def mobile_delete_competition(cid: int, user=Depends(admin_only), s: Session = Depends(get_db)):
    c = s.get(Competition, cid)
    if not c: raise HTTPException(404, "Competição não encontrada.")
    s.query(Match).filter(Match.competition_id == cid).update({Match.competition_id: None})
    s.query(Title).filter(Title.competition_id == cid).update({Title.competition_id: None})
    log(s, "competition.deleted.mobile", c.name); s.delete(c); s.commit()
    return {"ok": True}


@router.post("/matches")
async def mobile_add_match(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    home = str(d.get("home", "")).strip(); away = str(d.get("away", "")).strip()
    if not home or not away or home == away: raise HTTPException(400, "Informe equipes diferentes.")
    try: hs, aw = int(d["home_score"]), int(d["away_score"])
    except Exception: raise HTTPException(400, "Informe os dois placares.")
    if hs < 0 or aw < 0: raise HTTPException(400, "Placar inválido.")
    cid = d.get("competition_id") or None
    m = Match(home=home, away=away, home_score=hs, away_score=aw, competition_id=cid)
    s.add(m); log(s, "match.submitted.mobile", home + " x " + away); s.commit()
    return {"ok": True, "id": m.id}


@router.post("/matches/{mid}/{action}")
def mobile_match_action(mid: int, action: str, user=Depends(admin_only), s: Session = Depends(get_db)):
    if action not in ("approve", "reject"): raise HTTPException(400, "Ação inválida.")
    m = s.get(Match, mid)
    if not m: raise HTTPException(404, "Confronto não encontrado.")
    if m.status != "Pendente": raise HTTPException(400, "Confronto não está pendente.")
    if action == "approve":
        error = match_approval_error(s, m)
        if error: raise HTTPException(400, error)
    m.status = "Aprovado" if action == "approve" else "Rejeitado"
    log(s, "match." + m.status.lower() + ".mobile", mid); s.commit()
    return {"ok": True}


@router.post("/titles")
async def mobile_add_title(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json(); name = str(d.get("name", "")).strip()
    if not name: raise HTTPException(400, "Nome do título obrigatório.")
    t = Title(name=name, competition_id=d.get("competition_id") or None,
              season=str(d.get("season", "")), notes=str(d.get("notes", "")),
              player_id=d.get("player_id") or None)
    s.add(t); log(s, "title.won.mobile", name); s.commit()
    return {"ok": True, "id": t.id}


@router.post("/discipline")
async def mobile_add_discipline(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    if not d.get("player") or not d.get("reason"): raise HTTPException(400, "Informe jogador e motivo.")
    row = Discipline(player=str(d["player"]), reason=str(d["reason"]), sanction=str(d.get("sanction", "")))
    s.add(row); log(s, "discipline.created.mobile", row.player); s.commit()
    return {"ok": True}


@router.post("/recruitment")
async def mobile_add_recruit(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json(); nickname = str(d.get("nickname", "")).strip()
    if not nickname: raise HTTPException(400, "Nick obrigatório.")
    row = Recruit(nickname=nickname, position=str(d.get("position", "")),
                  contact=str(d.get("contact", "")), status="Novo")
    s.add(row); log(s, "recruit.created.mobile", nickname); s.commit()
    return {"ok": True}


@router.post("/notices")
async def mobile_add_notice(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json(); title = str(d.get("title", "")).strip(); body = str(d.get("body", "")).strip()
    if not title or not body: raise HTTPException(400, "Título e mensagem são obrigatórios.")
    row = Notice(title=title, body=body); s.add(row); log(s, "notice.created.mobile", title); s.commit()
    team_chat = os.getenv("TEAM_CHAT_ID", "").strip()
    bot = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if team_chat and bot:
        import requests
        try:
            requests.post("https://api.telegram.org/bot" + bot + "/sendMessage",
                          data={"chat_id": team_chat, "text": "📢 " + title + "\n\n" + body},
                          timeout=12).raise_for_status()
        except Exception:
            pass
    return {"ok": True, "id": row.id}


@router.delete("/notices/{nid}")
def mobile_delete_notice(nid: int, user=Depends(admin_only), s: Session = Depends(get_db)):
    row = s.get(Notice, nid)
    if not row: raise HTTPException(404, "Comunicado não encontrado.")
    log(s, "notice.deleted.mobile", row.title); s.delete(row); s.commit()
    return {"ok": True}


@router.get("/reports/full.pdf")
def mobile_full_report(user=Depends(admin_only)):
    from app import build_full_report
    s = SessionLocal()
    try:
        buf = build_full_report(s)
        from fastapi.responses import StreamingResponse
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": "attachment; filename=arqueiros-relatorio-geral.pdf"})
    finally:
        s.close()
