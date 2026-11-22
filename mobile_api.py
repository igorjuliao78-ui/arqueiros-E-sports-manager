import base64, hashlib, hmac, json, os, secrets, time, io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, Session

from app import (
    Base, engine, SessionLocal, get_db, TOKEN, Player, Competition, Match,
    MatchPlayerStat, Title, Notice, Discipline, Recruit, Audit, dashboard,
    player_metrics, ranking, log, match_approval_error,
    extract_duel_text, parse_duel_ocr, normalize_name
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

class PlayerGame(Base):
    __tablename__ = "player_games"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    opponent: Mapped[str] = mapped_column(String(120), default="")
    competition_id: Mapped[Optional[int]] = mapped_column(ForeignKey("competitions.id"), nullable=True)
    goals_for: Mapped[int] = mapped_column(Integer, default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    evidence_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Pendente")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class FederationFixture(Base):
    __tablename__ = "federation_fixtures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[Optional[int]] = mapped_column(ForeignKey("competitions.id"), nullable=True)
    round_name: Mapped[str] = mapped_column(String(80), default="")
    match_format: Mapped[str] = mapped_column(String(10), default="3x3")
    opponent: Mapped[str] = mapped_column(String(120))
    score_for: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_against: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lineup: Mapped[str] = mapped_column(Text, default="")
    evidence_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Pendente")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

PlayerGame.__table__.create(bind=engine, checkfirst=True)
FederationFixture.__table__.create(bind=engine, checkfirst=True)

class PlayerAlias(Base):
    __tablename__ = "player_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    alias: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class MobileImportFingerprint(Base):
    __tablename__ = "mobile_import_fingerprints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))


PlayerAlias.__table__.create(bind=engine, checkfirst=True)
MobileImportFingerprint.__table__.create(bind=engine, checkfirst=True)


class PlayerPerformance(Base):
    __tablename__ = "player_performance_totals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    competition_id: Mapped[int] = mapped_column(Integer, default=0)
    period: Mapped[str] = mapped_column(String(7), default="")
    games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    conceded: Mapped[int] = mapped_column(Integer, default=0)

PlayerPerformance.__table__.create(bind=engine, checkfirst=True)


def _store_performance(s, player_id, competition_id, goals_for, goals_against, goals, assists, created_at=None):
    period = (created_at or datetime.utcnow()).strftime("%Y-%m")
    cid = int(competition_id or 0)
    row = s.query(PlayerPerformance).filter_by(
        player_id=player_id, competition_id=cid, period=period
    ).first()
    if row is None:
        row = PlayerPerformance(player_id=player_id, competition_id=cid, period=period)
        s.add(row)
    # Older rows may contain NULL counters despite the model defaults.
    # Normalize every counter before incrementing so one legacy row cannot
    # prevent the whole mobile bootstrap from loading.
    for field in ("games", "wins", "draws", "losses", "goals", "assists", "conceded"):
        setattr(row, field, int(getattr(row, field, 0) or 0))
    gf, ga = int(goals_for or 0), int(goals_against or 0)
    scored, assisted = int(goals or 0), int(assists or 0)
    row.games += 1
    if gf > ga:
        row.wins += 1
    elif gf == ga:
        row.draws += 1
    else:
        row.losses += 1
    row.goals += scored
    row.assists += assisted
    row.conceded += ga


def _migrate_approved_player_games(s):
    old_rows = s.query(PlayerGame).filter(PlayerGame.status == "Aprovado").all()
    if not old_rows:
        return
    for row in old_rows:
        _store_performance(s, row.player_id, row.competition_id, row.goals_for,
                           row.goals_against, row.goals, row.assists, row.created_at)
        # Keep the original match record for the player's historical timeline.
        # "Consolidado" prevents the next bootstrap from adding these totals twice.
        row.status = "Consolidado"
    s.commit()




def _player_performance(s, player, month=None, competition_id=None):
    q = s.query(PlayerPerformance).filter(PlayerPerformance.player_id == player.id)
    if competition_id is not None:
        q = q.filter(PlayerPerformance.competition_id == int(competition_id))
    legacy_q = s.query(MatchPlayerStat).join(Match, Match.id == MatchPlayerStat.match_id).filter(
        MatchPlayerStat.player_name == player.name, Match.status == "Aprovado",
        MatchPlayerStat.goals_for.isnot(None), MatchPlayerStat.goals_against.isnot(None))
    if competition_id is not None:
        legacy_q = legacy_q.filter(Match.competition_id == int(competition_id))
    if month:
        q = q.filter(PlayerPerformance.period == month[0].strftime("%Y-%m"))
        legacy_q = legacy_q.filter(Match.created_at >= month[0], Match.created_at < month[1])
    rows = q.all()
    legacy = legacy_q.all()
    games = sum(x.games for x in rows) + len(legacy)
    wins = sum(x.wins for x in rows) + sum(x.goals_for > x.goals_against for x in legacy)
    draws = sum(x.draws for x in rows) + sum(x.goals_for == x.goals_against for x in legacy)
    losses = sum(x.losses for x in rows) + sum(x.goals_for < x.goals_against for x in legacy)
    goals = sum(x.goals for x in rows) + sum(x.goals_for for x in legacy)
    conceded = sum(x.conceded for x in rows) + sum(x.goals_against for x in legacy)
    assists = sum(x.assists for x in rows)
    return {"games": games, "wins": wins, "draws": draws, "losses": losses,
            "goals": goals, "conceded": conceded, "goal_difference": goals - conceded,
            "assists": assists, "points": wins * 3 + draws,
            "win_rate": round(wins * 100 / games, 1) if games else 0}


def _performance_payload(s):
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    month = (start, end)
    players = s.query(Player).all()
    ranking_rows = []
    monthly_rows = []
    for p in players:
        total = _player_performance(s, p)
        monthly = _player_performance(s, p, month)
        ranking_rows.append({"player_id": p.id, "name": p.name, **total})
        if monthly["games"]:
            monthly_rows.append({"player_id": p.id, "name": p.name, **monthly})
    ranking_rows.sort(key=lambda x: (-x["points"], -x["goals"], -x["assists"], -x["win_rate"], x["name"]))
    monthly_rows.sort(key=lambda x: (-x["points"], -x["goals"], -x["assists"], -x["win_rate"], x["name"]))
    fixtures = s.query(FederationFixture).order_by(FederationFixture.created_at.desc()).limit(100).all()
    competitions = {x.id: x.name for x in s.query(Competition).all()}
    # Team performance is counted per approved team confrontation, not once per player.
    team_matches = s.query(Match).filter(
        Match.status == "Aprovado",
        Match.home_score.isnot(None), Match.away_score.isnot(None)
    ).all()
    team_totals = {
        "games": len(team_matches),
        "wins": sum(x.home_score > x.away_score for x in team_matches),
        "draws": sum(x.home_score == x.away_score for x in team_matches),
        "losses": sum(x.home_score < x.away_score for x in team_matches),
        "goals": sum(x.home_score or 0 for x in team_matches),
        "conceded": sum(x.away_score or 0 for x in team_matches),
        "assists": sum(row.get("assists", 0) for row in ranking_rows),
    }
    team_totals["goal_difference"] = team_totals["goals"] - team_totals["conceded"]
    team_totals["points"] = team_totals["wins"] * 3 + team_totals["draws"]
    team_totals["win_rate"] = round(team_totals["wins"] * 100 / team_totals["games"], 1) if team_totals["games"] else 0
    team_totals["player_appearances"] = sum(row.get("games", 0) for row in ranking_rows)
    return {
        "player_ranking": ranking_rows,
        "team_player_performance": team_totals,
        "mvp_month": monthly_rows[0] if monthly_rows else None,
        "player_games": [{"id": x.id, "player_id": x.player_id, "player": s.get(Player, x.player_id).name if s.get(Player, x.player_id) else "",
                          "opponent": x.opponent, "competition": competitions.get(x.competition_id, ""),
                          "goals_for": x.goals_for, "goals_against": x.goals_against, "goals": x.goals,
                          "assists": x.assists, "status": x.status, "created_at": x.created_at.isoformat(),
                          "evidence_url": x.evidence_url} for x in s.query(PlayerGame).filter(PlayerGame.status == "Pendente").order_by(PlayerGame.created_at.desc()).limit(100).all()],
        "federation_fixtures": [{"id": x.id, "competition": competitions.get(x.competition_id, ""),
                                 "round": x.round_name, "format": x.match_format, "opponent": x.opponent,
                                 "score_for": x.score_for, "score_against": x.score_against,
                                 "lineup": x.lineup, "status": x.status, "evidence_url": x.evidence_url,
                                 "created_at": x.created_at.isoformat()} for x in fixtures]
    }



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
    _migrate_approved_player_games(s)
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
        **_performance_payload(s),
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
    stats = player_metrics(s, p, competition_id)
    games = s.query(PlayerGame).filter(
        PlayerGame.player_id == pid,
        PlayerGame.status.in_(["Aprovado", "Consolidado"])
    )
    if competition_id:
        games = games.filter(PlayerGame.competition_id == competition_id)
    rows = games.order_by(PlayerGame.created_at.desc()).all()
    stats["individual_games"] = [{"id": x.id, "opponent": x.opponent, "goals_for": x.goals_for,
        "goals_against": x.goals_against, "goals": x.goals, "assists": x.assists,
        "created_at": x.created_at.isoformat()} for x in rows]
    stats["performance"] = _player_performance(s, p, competition_id=competition_id)
    return {"player": _player(p), "stats": stats}


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
                                 headers={"Content-Disposition": "attachment; filename=arqueiros-relatorio-geral.pdf",
                                          "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})
    finally:
        s.close()



def _parse_mobile_print_rows(text: str, team_side: str):
    import re
    rows = []
    pending_players = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip(" \t•")
        line = re.sub(r"^\d+\s*(?:[º°])?\s*[.)➤>»:-]\s*", "", line)

        # Official WhatsApp description format: PLAYER | 2 x 1
        scored = re.match(r"^(.+?)\s*\|\s*(\d+)\s*[x×]\s*(\d+)\s*$", line, re.I)
        if scored:
            player_name = scored.group(1).strip(" •➤».-:")
            if player_name:
                rows.append({"detected_name": player_name, "opponent": "",
                             "goals_for": int(scored.group(2)),
                             "goals_against": int(scored.group(3))})
            continue

        # Pending players are visible in the review but never enter statistics.
        pending = re.match(r"^(.+?)\s*\|\s*(?:PENDENTE|AGUARDANDO|NÃO\s+INFORMADO)\s*$", line, re.I)
        if pending:
            player_name = pending.group(1).strip(" •➤».-:")
            if player_name:
                pending_players.append(player_name)
            continue

        # Also accept a direct matchup line, where both player names are shown.
        duel = re.match(r"^\s*(?:\d+\s*(?:[º°])?\s*[.)➤>»:-]?\s*)?(.+?)\s+(\d+)\s*[x×]\s*(\d+)(?:\s+(.+))?$", line, re.I)
        if not duel:
            continue
        left = duel.group(1).strip(" •➤».-:")
        right = (duel.group(4) or "").strip(" •➤».-:")
        player_name, opponent = (left, right) if team_side == "first" else (right, left)
        if player_name:
            rows.append({"detected_name": player_name, "opponent": opponent,
                         "goals_for": int(duel.group(2)) if team_side == "first" else int(duel.group(3)),
                         "goals_against": int(duel.group(3)) if team_side == "first" else int(duel.group(2))})
    return rows, pending_players

@router.post("/matches/image/preview")
async def mobile_match_image_preview(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    encoded = str(d.get("image_base64", "")).strip()
    team_side = str(d.get("team_side", "first")).strip().lower()
    if team_side not in ("first", "second"):
        raise HTTPException(400, "Informe se a Arqueiros aparece primeiro ou segundo nos confrontos.")
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > 12 * 1024 * 1024:
            raise ValueError("Imagem vazia ou maior que 12 MB.")
        from PIL import Image
        image = Image.open(io.BytesIO(raw))
        image_hash = hashlib.sha256(raw).hexdigest()
        players = s.query(Player).all()
        aliases = s.query(PlayerAlias).all()
        alias_to_player = {normalize_name(p.name): p for p in players}
        alias_to_player.update({normalize_name(p.nickname): p for p in players if p.nickname})
        for alias in aliases:
            player = s.get(Player, alias.player_id)
            if player:
                alias_to_player[normalize_name(alias.alias)] = player
        roster = list({key for key in alias_to_player if key})
        text = extract_duel_text(image, roster)
        parsed = parse_duel_ocr(text, roster)
        raw_rows, pending_players = _parse_mobile_print_rows(text, team_side)
    except Exception as exc:
        raise HTTPException(400, "Não foi possível ler o print: " + str(exc)[:180])
    stats = []
    new_players = {}
    for row in raw_rows:
        key = normalize_name(row["detected_name"])
        player = alias_to_player.get(key)
        if player is None:
            matches = [(k, p) for k, p in alias_to_player.items() if k and (k in key or key in k)]
            if matches:
                player = max(matches, key=lambda item: len(item[0]))[1]
        if player is None and key:
            # A small spelling variation should match an existing nickname/name,
            # but ambiguous OCR must remain a new-player candidate for admin review.
            import difflib
            close = difflib.get_close_matches(key, list(alias_to_player.keys()), n=2, cutoff=0.82)
            if close:
                best = difflib.SequenceMatcher(None, key, close[0]).ratio()
                second = difflib.SequenceMatcher(None, key, close[1]).ratio() if len(close) > 1 else 0
                if best >= 0.82 and best - second >= 0.06:
                    player = alias_to_player[close[0]]
        stats.append({"player_id": player.id if player else None,
                      "player": player.name if player else row["detected_name"],
                      "detected_name": row["detected_name"],
                      "is_new_player": player is None,
                      "goals_for": row["goals_for"], "goals_against": row["goals_against"],
                      "opponent": row["opponent"]})
        if player is None:
            new_players[normalize_name(row["detected_name"])] = row["detected_name"]
    if not stats and not pending_players:
        raise HTTPException(422, "Não encontrei jogadores com placares individuais. Confira se o print está completo e legível.")
    scores = parsed.get("scores") or []
    has_explicit_reverse_header = bool(
        re.search(r"[^\s|]+\s*[x×]\s*\bAQR\b", text, re.I)
        or re.search(r"^(.+?)\s*[x×]\s*\bARQUEIROS\s+E-SPORTS\b", text, re.I | re.M)
    )
    if team_side == "second" and not has_explicit_reverse_header and len(scores) >= 2:
        scores = [scores[1], scores[0]]
    competition_rows = s.query(Competition).all()
    detected_competition_name = ""
    detected_competition_id = None
    for line in text.splitlines():
        clean_line = line.strip().lstrip("#").strip()
        if not clean_line:
            continue
        if clean_line.lower().startswith("competição:"):
            clean_line = clean_line.split(":", 1)[1].strip()
        for comp in competition_rows:
            comp_key = normalize_name(comp.name)
            line_key = normalize_name(clean_line)
            if comp_key and (comp_key == line_key or comp_key in line_key):
                detected_competition_name = comp.name
                detected_competition_id = comp.id
                break
        if detected_competition_id:
            break
        if not detected_competition_name:
            detected_competition_name = clean_line.lstrip("# ").strip()
    return {"team": parsed.get("team", "Equipe adversária"), "scores": scores,
            "stats": stats, "new_players": list(new_players.values()),
            "pending_players": pending_players,
            "competition_id": detected_competition_id,
            "detected_competition_name": detected_competition_name,
            "team_side": team_side, "image_sha256": image_hash,
            "recognized": len(stats),
            "note": "Novos jogadores serão cadastrados somente após a conferência e confirmação do administrador."}


@router.post("/matches/image/confirm")
async def mobile_match_image_confirm(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    team = str(d.get("team", "Equipe adversária")).strip() or "Equipe adversária"
    scores = d.get("scores") or []
    hs = int(scores[0]) if len(scores) > 0 and scores[0] is not None else None
    aw = int(scores[1]) if len(scores) > 1 and scores[1] is not None else None
    cid = d.get("competition_id") or None
    if cid and not s.get(Competition, int(cid)):
        raise HTTPException(404, "Competição não encontrada.")
    image_hash = str(d.get("image_sha256", "")).strip()
    if image_hash:
        duplicate = s.query(MobileImportFingerprint).filter_by(image_sha256=image_hash).first()
        if duplicate:
            return {"ok": True, "duplicate": True, "id": duplicate.match_id,
                    "status": "Já importado; nenhum registro duplicado foi criado."}
    stats = d.get("stats") or []
    if not stats and not d.get("pending_players"):
        raise HTTPException(400, "Nenhum jogador com placar concluído para registrar.")
    team_side = str(d.get("team_side", "first")).lower()
    if team_side not in ("first", "second"):
        raise HTTPException(400, "Lado da Arqueiros inválido.")
    if hs is None or aw is None:
        raise HTTPException(400, "O placar geral não foi reconhecido. Corrija o print ou envie uma imagem mais legível.")
    if not cid:
        raise HTTPException(400, "Selecione a competição antes de confirmar o confronto.")
    match = Match(competition_id=int(cid), home="ARQUEIROS E-SPORTS",
                  away=team, home_score=hs, away_score=aw, status="Pendente")
    s.add(match)
    s.flush()
    created_players = 0
    for item in stats:
        player_id = item.get("player_id")
        detected_name = str(item.get("detected_name") or item.get("player") or "").strip()
        player = s.get(Player, int(player_id)) if player_id else None
        if player is None:
            if not bool(item.get("is_new_player")) or not detected_name:
                raise HTTPException(400, "Jogador não reconhecido. Associe a um cadastro existente ou confirme um novo jogador.")
            existing = (s.query(Player).filter(Player.name.ilike(detected_name)).first()
                        or s.query(Player).filter(Player.nickname.ilike(detected_name)).first())
            if existing is None:
                alias = s.query(PlayerAlias).filter(PlayerAlias.alias.ilike(detected_name)).first()
                existing = s.get(Player, alias.player_id) if alias else None
            player = existing or Player(name=detected_name, nickname=detected_name, status="Ativo", active=True)
            if existing is None:
                s.add(player)
                s.flush()
                created_players += 1
                log(s, "player.created.from_match_print", detected_name)
        gf, ga = int(item["goals_for"]), int(item["goals_against"])
        if gf < 0 or ga < 0:
            raise HTTPException(400, "Placar individual inválido.")
        # Save the OCR spelling as an alias when it differs from the canonical player name.
        if normalize_name(detected_name) and normalize_name(detected_name) != normalize_name(player.name):
            alias = s.query(PlayerAlias).filter_by(alias=detected_name).first()
            if alias is None:
                s.add(PlayerAlias(player_id=player.id, alias=detected_name))
        s.add(MatchPlayerStat(match_id=match.id, player_name=player.name,
                              opponent_name=str(item.get("opponent", "")), goals_for=gf, goals_against=ga))
    if image_hash:
        s.add(MobileImportFingerprint(image_sha256=image_hash, match_id=match.id))
    s.flush()
    saved_stats = s.query(MatchPlayerStat).filter(MatchPlayerStat.match_id == match.id).all()
    unresolved = [row.player_name for row in saved_stats
                  if not s.query(Player).filter(Player.name == row.player_name).first()]
    if unresolved:
        raise HTTPException(400, "Jogador não associado ao elenco: " + ", ".join(unresolved))
    match.status = "Aprovado"
    log(s, "duel.ocr.mobile.approved", f"#{match.id} — {team}")
    s.commit()
    return {"ok": True, "id": match.id, "status": match.status,
            "players_registered": created_players}


@router.post("/player-games")
async def mobile_create_player_game(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    try:
        player_id = int(d.get("player_id")) if d.get("player_id") else None
        gf, ga = int(d.get("goals_for")), int(d.get("goals_against"))
        goals, assists = int(d.get("goals", 0)), int(d.get("assists", 0))
    except (TypeError, ValueError):
        raise HTTPException(400, "Informe jogador e placar válido.")
    player_name = str(d.get("player_name", "")).strip()
    player = s.get(Player, player_id) if player_id else s.query(Player).filter(Player.name.ilike(player_name)).first()
    if not player or not player.active:
        raise HTTPException(404, "Jogador ativo não encontrado. Selecione alguém do elenco.")
    player_id = player.id
    if min(gf, ga, goals, assists) < 0:
        raise HTTPException(400, "Estatísticas não podem ser negativas.")
    cid = d.get("competition_id") or None
    if cid and not s.get(Competition, int(cid)):
        raise HTTPException(404, "Competição não encontrada.")
    row = PlayerGame(player_id=player_id, opponent=str(d.get("opponent", "")).strip(),
                     competition_id=int(cid) if cid else None, goals_for=gf, goals_against=ga,
                     goals=goals, assists=assists, evidence_url=str(d.get("evidence_url", "")).strip() or None)
    s.add(row); log(s, "player.game.submitted", str(player_id) + " x " + row.opponent); s.commit()
    return {"ok": True, "id": row.id, "status": row.status}


@router.post("/player-games/{gid}/{action}")
def mobile_player_game_action(gid: int, action: str, user=Depends(admin_only), s: Session = Depends(get_db)):
    if action not in ("approve", "reject"):
        raise HTTPException(400, "Ação inválida.")
    row = s.get(PlayerGame, gid)
    if not row:
        raise HTTPException(404, "Jogo não encontrado.")
    if row.status != "Pendente":
        raise HTTPException(400, "Este jogo já foi analisado.")
    p = s.get(Player, row.player_id)
    if action == "approve":
        _store_performance(s, row.player_id, row.competition_id, row.goals_for,
                           row.goals_against, row.goals, row.assists, row.created_at)
        log(s, "player.game.approve", (p.name if p else str(row.player_id)) + " x " + row.opponent)
        # Preserve the approved source row; totals are consolidated exactly once.
        row.status = "Consolidado"
    else:
        log(s, "player.game.reject", (p.name if p else str(row.player_id)) + " x " + row.opponent)
        # Keep rejected submissions for auditability instead of deleting evidence.
    s.commit()
    return {"ok": True}


@router.post("/federation")
async def mobile_create_federation_fixture(request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    opponent = str(d.get("opponent", "")).strip()
    fmt = str(d.get("format", "3x3")).strip()
    if not opponent:
        raise HTTPException(400, "Informe o adversário.")
    if fmt not in ("3x3", "5x5", "6x6"):
        raise HTTPException(400, "Formato deve ser 3x3, 5x5 ou 6x6.")
    try:
        sf = int(d["score_for"]) if str(d.get("score_for", "")).strip() else None
        sa = int(d["score_against"]) if str(d.get("score_against", "")).strip() else None
    except ValueError:
        raise HTTPException(400, "Placar inválido.")
    if (sf is None) != (sa is None):
        raise HTTPException(400, "Informe os dois lados do placar.")
    if sf is not None and min(sf, sa) < 0:
        raise HTTPException(400, "Placar não pode ser negativo.")
    cid = d.get("competition_id") or None
    row = FederationFixture(competition_id=int(cid) if cid else None,
        round_name=str(d.get("round", "")).strip(), match_format=fmt, opponent=opponent,
        score_for=sf, score_against=sa, lineup=str(d.get("lineup", "")).strip(),
        evidence_url=str(d.get("evidence_url", "")).strip() or None)
    s.add(row); log(s, "federation.fixture.created", opponent + " • " + fmt); s.commit()
    return {"ok": True, "id": row.id, "status": row.status}


@router.put("/federation/{fid}")
async def mobile_update_federation_fixture(fid: int, request: Request, user=Depends(admin_only), s: Session = Depends(get_db)):
    d = await request.json()
    row = s.get(FederationFixture, fid)
    if not row:
        raise HTTPException(404, "Confronto de federação não encontrado.")
    if "score_for" in d: row.score_for = int(d["score_for"])
    if "score_against" in d: row.score_against = int(d["score_against"])
    if "lineup" in d: row.lineup = str(d["lineup"]).strip()
    if "round" in d: row.round_name = str(d["round"]).strip()
    if "evidence_url" in d: row.evidence_url = str(d["evidence_url"]).strip() or None
    log(s, "federation.fixture.updated", row.opponent); s.commit()
    return {"ok": True}


@router.post("/federation/{fid}/{action}")
def mobile_federation_action(fid: int, action: str, user=Depends(admin_only), s: Session = Depends(get_db)):
    if action not in ("approve", "reject"):
        raise HTTPException(400, "Ação inválida.")
    row = s.get(FederationFixture, fid)
    if not row:
        raise HTTPException(404, "Confronto de federação não encontrado.")
    if row.status != "Pendente":
        raise HTTPException(400, "Este confronto já foi analisado.")
    if action == "approve" and (row.score_for is None or row.score_against is None):
        raise HTTPException(400, "Informe o placar antes de aprovar.")
    row.status = "Aprovado" if action == "approve" else "Rejeitado"
    log(s, "federation.fixture." + action, row.opponent); s.commit()
    return {"ok": True}
