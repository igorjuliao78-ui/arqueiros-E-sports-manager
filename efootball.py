"""Admin-only eFootball player lab and tactical planning endpoints.

The module reuses the application's SQLAlchemy Base, engine and session factory.
Attribute values are stored as entered/imported; no undocumented game formula is assumed.
"""
import json
import io
import re
import unicodedata
from PIL import Image
import pytesseract
from fastapi import UploadFile, File, Form
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Request, Depends
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column


def register_efootball(app, Base, engine, SessionLocal, Player, auth, get_db, log):
    class PlayerBuild(Base):
        __tablename__ = "efootball_player_builds"
        id: Mapped[int] = mapped_column(primary_key=True)
        player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
        name: Mapped[str] = mapped_column(String(100), default="Build principal")
        position: Mapped[str] = mapped_column(String(30), default="")
        booster: Mapped[str] = mapped_column(String(80), default="")
        overall: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        progression: Mapped[str] = mapped_column(Text, default="{}")
        attributes: Mapped[str] = mapped_column(Text, default="{}")
        notes: Mapped[str] = mapped_column(Text, default="")
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    class SquadPlan(Base):
        __tablename__ = "efootball_squad_plans"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column(String(100))
        formation: Mapped[str] = mapped_column(String(30))
        playstyle: Mapped[str] = mapped_column(String(60), default="")
        lineup: Mapped[str] = mapped_column(Text, default="[]")
        notes: Mapped[str] = mapped_column(Text, default="")
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    Base.metadata.create_all(engine)

    def build_dict(row, player_name=""):
        return {
            "id": row.id, "player_id": row.player_id, "player_name": player_name,
            "name": row.name, "position": row.position, "booster": row.booster,
            "overall": row.overall, "progression": json.loads(row.progression or "{}"),
            "attributes": json.loads(row.attributes or "{}"), "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @app.get("/api/efootball/players")
    def efootball_players(s=Depends(get_db), _: bool = Depends(auth)):
        rows = s.query(Player).filter(Player.active.is_(True)).order_by(Player.name).all()
        return [{"id": p.id, "name": p.name, "nickname": p.nickname, "position": p.position}
                for p in rows]

    @app.get("/api/efootball/builds")
    def list_builds(player_id: Optional[int] = None, s=Depends(get_db), _: bool = Depends(auth)):
        q = s.query(PlayerBuild).order_by(PlayerBuild.created_at.desc(), PlayerBuild.id.desc())
        if player_id:
            q = q.filter(PlayerBuild.player_id == player_id)
        rows = q.limit(200).all()
        names = {p.id: p.name for p in s.query(Player).all()}
        return [build_dict(row, names.get(row.player_id, "Jogador removido")) for row in rows]

    @app.post("/api/efootball/builds")
    async def save_build(request: Request, s=Depends(get_db), _: bool = Depends(auth)):
        data = await request.json()
        player = s.get(Player, int(data.get("player_id") or 0))
        if not player or not player.active:
            raise HTTPException(400, "Selecione um jogador ativo do elenco.")
        name = str(data.get("name") or "Build principal").strip()[:100]
        position = str(data.get("position") or player.position or "").strip()[:30]
        booster = str(data.get("booster") or "").strip()[:80]
        overall = data.get("overall")
        if overall in ("", None):
            overall = None
        else:
            overall = int(overall)
            if not 40 <= overall <= 110:
                raise HTTPException(400, "Overall deve ficar entre 40 e 110.")
        progression = data.get("progression") or {}
        attributes = data.get("attributes") or {}
        if not isinstance(progression, dict) or not isinstance(attributes, dict):
            raise HTTPException(400, "Progressão e atributos devem ser objetos.")
        clean_progression = {}
        for key, value in progression.items():
            value = int(value)
            if value < 0 or value > 99:
                raise HTTPException(400, "Cada categoria de progressão deve ficar entre 0 e 99.")
            clean_progression[str(key)[:30]] = value
        clean_attributes = {}
        for key, value in attributes.items():
            value = int(value)
            if value < 0 or value > 120:
                raise HTTPException(400, "Atributos devem ficar entre 0 e 120.")
            clean_attributes[str(key)[:40]] = value
        row = PlayerBuild(
            player_id=player.id, name=name, position=position, booster=booster,
            overall=overall, progression=json.dumps(clean_progression, ensure_ascii=False),
            attributes=json.dumps(clean_attributes, ensure_ascii=False),
            notes=str(data.get("notes") or "")[:2000],
        )
        s.add(row)
        log(s, "efootball.build.created", f"{player.name}: {name}")
        s.commit()
        return build_dict(row, player.name)

    @app.delete("/api/efootball/builds/{build_id}")
    def delete_build(build_id: int, s=Depends(get_db), _: bool = Depends(auth)):
        row = s.get(PlayerBuild, build_id)
        if not row:
            raise HTTPException(404, "Build não encontrada.")
        log(s, "efootball.build.deleted", f"build={build_id}; player={row.player_id}")
        s.delete(row)
        s.commit()
        return {"ok": True}

    @app.get("/api/efootball/squad-plans")
    def list_squad_plans(s=Depends(get_db), _: bool = Depends(auth)):
        rows = s.query(SquadPlan).order_by(SquadPlan.created_at.desc()).limit(100).all()
        return [{
            "id": row.id, "name": row.name, "formation": row.formation,
            "playstyle": row.playstyle, "lineup": json.loads(row.lineup or "[]"),
            "notes": row.notes, "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in rows]

    @app.post("/api/efootball/squad-plans")
    async def save_squad_plan(request: Request, s=Depends(get_db), _: bool = Depends(auth)):
        data = await request.json()
        name = str(data.get("name") or "").strip()
        formation = str(data.get("formation") or "").strip()
        lineup = data.get("lineup") or []
        if not name or not formation:
            raise HTTPException(400, "Informe o nome do plano e a formação.")
        if not isinstance(lineup, list) or len(lineup) > 18:
            raise HTTPException(400, "A escalação deve conter até 18 posições.")
        valid_ids = {p.id for p in s.query(Player).filter(Player.active.is_(True)).all()}
        cleaned = []
        for slot in lineup:
            if not isinstance(slot, dict):
                continue
            pid = int(slot.get("player_id") or 0)
            if pid and pid not in valid_ids:
                raise HTTPException(400, "A escalação contém jogador inativo ou inexistente.")
            cleaned.append({
                "slot": str(slot.get("slot") or "")[:30],
                "player_id": pid or None,
                "role": str(slot.get("role") or "")[:40],
            })
        row = SquadPlan(name=name[:100], formation=formation[:30],
                        playstyle=str(data.get("playstyle") or "")[:60],
                        lineup=json.dumps(cleaned, ensure_ascii=False),
                        notes=str(data.get("notes") or "")[:2000])
        s.add(row)
        log(s, "efootball.squad_plan.created", f"{name}: {formation}")
        s.commit()
        return {"ok": True, "id": row.id}

    @app.delete("/api/efootball/squad-plans/{plan_id}")
    def delete_squad_plan(plan_id: int, s=Depends(get_db), _: bool = Depends(auth)):
        row = s.get(SquadPlan, plan_id)
        if not row:
            raise HTTPException(404, "Plano tático não encontrado.")
        log(s, "efootball.squad_plan.deleted", row.name)
        s.delete(row)
        s.commit()
        return {"ok": True}

    @app.post("/api/efootball/import-image")
    async def import_player_image(
        image: UploadFile = File(...),
        player_id: int = Form(...),
        s=Depends(get_db),
        _: bool = Depends(auth),
    ):
        """OCR helper for eFHUB-like player screens. Returns a draft for admin review, never saves silently."""
        player = s.get(Player, player_id)
        if not player or not player.active:
            raise HTTPException(400, "Selecione um jogador ativo.")
        if image.content_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise HTTPException(400, "Envie uma imagem PNG, JPG ou WEBP.")
        raw = await image.read()
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(413, "A imagem deve ter no máximo 8 MB.")
        try:
            picture = Image.open(io.BytesIO(raw)).convert("RGB")
            text = pytesseract.image_to_string(picture, lang="por")
        except Exception as exc:
            raise HTTPException(422, "Não foi possível ler a imagem. Verifique o OCR do servidor: " + str(exc)[:160])
        def norm(value):
            value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
            return re.sub(r"[^a-z0-9]+", " ", value).strip()
        aliases = {
            "offensive_awareness": ["talento ofensivo", "consciencia ofensiva"],
            "ball_control": ["controle de bola"],
            "dribbling": ["drible"],
            "tight_possession": ["conducao firme"],
            "low_pass": ["passe rasteiro"],
            "lofted_pass": ["passe alto"],
            "finishing": ["finalizacao"],
            "heading": ["cabeceio"],
            "set_piece_taking": ["cobranca de bola parada", "cobranca de falta"],
            "curl": ["curva"],
            "defensive_awareness": ["talento defensivo", "consciencia defensiva"],
            "tackling": ["desarme"],
            "defensive_engagement": ["dedicacao defensiva"],
            "speed": ["velocidade"],
            "acceleration": ["aceleracao"],
            "kicking_power": ["forca do chute"],
            "jump": ["salto"],
            "physical_contact": ["contato fisico"],
            "balance": ["equilibrio"],
            "stamina": ["resistencia"],
            "goalkeeping": ["talento de goleiro"],
            "gk_catching": ["alcance do goleiro", "defesa do goleiro"],
            "gk_reflexes": ["reflexos do goleiro"],
            "gk_reach": ["alcance"],
        }
        parsed = {}
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            normalized = norm(line)
            numbers = re.findall(r"(?<![a-z])\d{1,3}(?![a-z])", normalized)
            if not numbers:
                continue
            value = int(numbers[-1])
            if value > 120:
                continue
            for key, labels in aliases.items():
                if any(norm(label) in normalized for label in labels):
                    parsed[key] = value
                    break
        return {
            "ok": True, "player_id": player.id, "player_name": player.name,
            "attributes": parsed, "raw_text": text[:6000],
            "review_required": True,
            "message": "Rascunho de OCR. Confira os valores e salve a build manualmente.",
        }

    @app.get("/api/efootball/recommendations")
    def tactical_recommendations(position: str, s=Depends(get_db), _: bool = Depends(auth)):
        """Transparent heuristic: rank saved builds by requested position and selected attributes."""
        pos = position.strip().upper()[:12]
        weights = {
            "CF": {"finishing": 3, "offensive_awareness": 3, "speed": 2, "ball_control": 1},
            "SS": {"ball_control": 2, "dribbling": 2, "passing": 2, "finishing": 2},
            "LWF": {"speed": 3, "acceleration": 3, "dribbling": 3, "ball_control": 1},
            "RWF": {"speed": 3, "acceleration": 3, "dribbling": 3, "ball_control": 1},
            "AMF": {"passing": 3, "ball_control": 3, "dribbling": 2, "offensive_awareness": 1},
            "CMF": {"passing": 3, "stamina": 2, "ball_control": 2, "defensive_awareness": 1},
            "DMF": {"defensive_awareness": 3, "ball_winning": 3, "physical_contact": 2, "stamina": 1},
            "LB": {"speed": 2, "stamina": 3, "defensive_awareness": 2, "passing": 1},
            "RB": {"speed": 2, "stamina": 3, "defensive_awareness": 2, "passing": 1},
            "CB": {"defensive_awareness": 3, "ball_winning": 3, "physical_contact": 2, "jump": 1},
            "GK": {"goalkeeping": 3, "reflexes": 3, "reach": 2, "catching": 2},
        }.get(pos, {"speed": 1, "passing": 1, "ball_control": 1})
        rows = s.query(PlayerBuild).order_by(PlayerBuild.created_at.desc()).all()
        names = {p.id: p.name for p in s.query(Player).all()}
        ranked = []
        for row in rows:
            attrs = json.loads(row.attributes or "{}")
            if not attrs:
                continue
            score = sum(float(attrs.get(key, 0)) * weight for key, weight in weights.items()) / sum(weights.values())
            ranked.append({
                "build_id": row.id, "player_id": row.player_id,
                "player_name": names.get(row.player_id, "Jogador removido"),
                "build_name": row.name, "position": row.position, "requested_position": pos,
                "score": round(score, 1), "overall": row.overall, "booster": row.booster,
                "weights_used": weights,
            })
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return {"position": pos, "method": "heurística transparente baseada nos atributos cadastrados; não representa fórmula oficial do jogo", "recommendations": ranked[:10]}
