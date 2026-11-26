"""eFootball build calculator and tactical-plan persistence for Arqueiros Manager.

Progression cost and category mapping are versioned as game-reference rules. Role optimization
is an internal, transparent heuristic; it is not Konami's Overall Rating formula.
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from PIL import Image
import io
import re
import unicodedata
import pytesseract
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


CATEGORY_STATS = {
    "SHO": ("finishing", "set_piece_taking", "curl"),
    "PAS": ("low_pass", "lofted_pass"),
    "DRI": ("dribbling", "ball_control", "tight_possession"),
    "DEX": ("offensive_awareness", "acceleration", "balance"),
    "LBS": ("kicking_power", "speed", "stamina"),
    "AERIAL": ("heading", "jump", "physical_contact"),
    "DEF": ("defensive_awareness", "tackling", "aggression", "defensive_engagement"),
    "GK1": ("goalkeeping_awareness", "jump"),
    "GK2": ("goalkeeping_parrying", "goalkeeping_reach"),
    "GK3": ("goalkeeping_catching", "goalkeeping_reflexes"),
}
CATEGORY_LABELS = {
    "SHO": "Chute", "PAS": "Passe", "DRI": "Drible", "DEX": "Destreza",
    "LBS": "Membros inferiores", "AERIAL": "Força aérea", "DEF": "Defesa",
    "GK1": "Goleiro 1", "GK2": "Goleiro 2", "GK3": "Goleiro 3",
}
POSITION_WEIGHTS = {
    "CF": {"finishing": 3, "offensive_awareness": 3, "kicking_power": 2, "speed": 2, "acceleration": 2, "heading": 1},
    "SS": {"ball_control": 2, "dribbling": 2, "low_pass": 2, "finishing": 2, "offensive_awareness": 2, "acceleration": 1},
    "LWF": {"speed": 3, "acceleration": 3, "dribbling": 3, "ball_control": 2, "tight_possession": 2, "finishing": 1},
    "RWF": {"speed": 3, "acceleration": 3, "dribbling": 3, "ball_control": 2, "tight_possession": 2, "finishing": 1},
    "AMF": {"low_pass": 3, "lofted_pass": 2, "ball_control": 3, "dribbling": 2, "offensive_awareness": 2, "tight_possession": 2},
    "CMF": {"low_pass": 3, "lofted_pass": 2, "stamina": 2, "ball_control": 2, "defensive_awareness": 1, "speed": 1},
    "DMF": {"defensive_awareness": 3, "tackling": 3, "aggression": 2, "defensive_engagement": 2, "low_pass": 1, "stamina": 2},
    "LB": {"speed": 2, "acceleration": 2, "stamina": 3, "defensive_awareness": 2, "tackling": 2, "low_pass": 1},
    "RB": {"speed": 2, "acceleration": 2, "stamina": 3, "defensive_awareness": 2, "tackling": 2, "low_pass": 1},
    "CB": {"defensive_awareness": 3, "tackling": 3, "aggression": 2, "defensive_engagement": 2, "physical_contact": 2, "jump": 1},
    "GK": {"goalkeeping_awareness": 3, "goalkeeping_parrying": 3, "goalkeeping_catching": 2, "goalkeeping_reflexes": 3, "goalkeeping_reach": 2, "jump": 1},
}
STAT_ALIASES = {
    "talento ofensivo": "offensive_awareness", "consciencia ofensiva": "offensive_awareness",
    "controle de bola": "ball_control", "drible": "dribbling", "conducao firme": "tight_possession",
    "passe rasteiro": "low_pass", "passe alto": "lofted_pass", "finalizacao": "finishing",
    "cabeceio": "heading", "cobranca de bola parada": "set_piece_taking", "curva": "curl",
    "talento defensivo": "defensive_awareness", "desarme": "tackling",
    "dedicacao defensiva": "defensive_engagement", "agressividade": "aggression",
    "velocidade": "speed", "aceleracao": "acceleration", "forca do chute": "kicking_power",
    "salto": "jump", "contato fisico": "physical_contact", "equilibrio": "balance",
    "resistencia": "stamina", "talento de goleiro": "goalkeeping_awareness",
    "defesa do goleiro": "goalkeeping_parrying", "alcance do goleiro": "goalkeeping_reach",
    "reflexos do goleiro": "goalkeeping_reflexes", "defesa": "goalkeeping_catching",
}
ALL_STATS = sorted({stat for stats in CATEGORY_STATS.values() for stat in stats})


def progression_points_for_level(level: int) -> int:
    """Two progression points per gained level, with level 1 as the starting level."""
    return max(0, (int(level) - 1) * 2)


def progression_cost(category_points: int) -> int:
    """1 PP for CP 1-4, 2 for 5-8, 3 for 9-12, 4 for 13-16, and so on."""
    points = max(0, int(category_points))
    return sum((index // 4) + 1 for index in range(points))


def normalize_category_points(value):
    if not isinstance(value, dict):
        raise ValueError("Progressão deve ser um objeto com categorias.")
    result = {key: 0 for key in CATEGORY_STATS}
    aliases = {"SHOOTING": "SHO", "PASSING": "PAS", "DRIBBLING": "DRI",
               "DEXTERITY": "DEX", "LOWER_BODY": "LBS", "AERIAL_STRENGTH": "AERIAL",
               "DEFENDING": "DEF", "GK_AWARENESS": "GK1", "GK_PARRYING": "GK2",
               "GK_CATCHING": "GK3"}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip().upper()
        key = aliases.get(key, key)
        if key not in CATEGORY_STATS:
            raise ValueError(f"Categoria desconhecida: {raw_key}")
        number = int(raw_value)
        if number < 0 or number > 40:
            raise ValueError("Cada categoria deve ficar entre 0 e 40 CP.")
        result[key] = number
    return result


def normalize_stats(value, minimum=40, maximum=99):
    if not isinstance(value, dict):
        raise ValueError("Atributos devem ser um objeto JSON.")
    result = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip().lower()
        if key not in ALL_STATS:
            key = STAT_ALIASES.get(_ascii(key), key)
        if key not in ALL_STATS:
            raise ValueError(f"Atributo desconhecido: {raw_key}")
        number = int(raw_value)
        if number < minimum or number > maximum:
            raise ValueError(f"{raw_key}: atributo deve ficar entre {minimum} e {maximum}.")
        result[key] = number
    return result


def _ascii(value):
    return unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower().strip()


def calculate_build(base_stats, category_points, level, booster_effects=None):
    base = normalize_stats(base_stats, minimum=1, maximum=99) if base_stats else {}
    allocation = normalize_category_points(category_points or {})
    available = progression_points_for_level(level)
    spent = sum(progression_cost(v) for v in allocation.values())
    if spent > available:
        raise ValueError(f"Distribuição usa {spent} PP, mas o nível {level} disponibiliza {available} PP.")
    progression = dict(base)
    for category, count in allocation.items():
        for stat in CATEGORY_STATS[category]:
            if stat in progression:
                progression[stat] = min(99, progression[stat] + count)
    boosts = normalize_stats(booster_effects or {}, minimum=0, maximum=20) if booster_effects else {}
    final = {stat: min(120, value + boosts.get(stat, 0)) for stat, value in progression.items()}
    return {
        "level": int(level), "available_pp": available, "spent_pp": spent,
        "remaining_pp": available - spent, "category_points": allocation,
        "category_costs": {key: progression_cost(value) for key, value in allocation.items()},
        "base_stats": base, "progression_stats": progression,
        "booster_effects": boosts, "final_stats": final,
        "notes": [
            "Cada nível ganho concede 2 PP; o nível 1 começa com 0 PP.",
            "Cada CP aumenta os atributos da categoria em +1, limitado a 99 antes do booster.",
            "Boosters informados são aplicados depois da progressão, com teto de 120.",
            "O cálculo de Overall Rating não é reproduzido: a Konami não publica a fórmula completa.",
        ],
    }


def optimize_allocation(base_stats, level, position, booster_effects=None):
    """Greedy role-fit allocation; a transparent squad heuristic, not an OVR optimizer."""
    base = normalize_stats(base_stats, minimum=1, maximum=99)
    boosts = normalize_stats(booster_effects or {}, minimum=0, maximum=20) if booster_effects else {}
    weights = POSITION_WEIGHTS.get(str(position or "").upper(), POSITION_WEIGHTS["CMF"])
    budget = progression_points_for_level(level)
    allocation = {key: 0 for key in CATEGORY_STATS}
    spent = 0
    while True:
        choices = []
        for category, stats in CATEGORY_STATS.items():
            cost = progression_cost(allocation[category] + 1) - progression_cost(allocation[category])
            if spent + cost > budget:
                continue
            marginal = 0.0
            for stat in stats:
                if stat not in base:
                    continue
                current = min(99, base[stat] + allocation[category] + boosts.get(stat, 0))
                if current < 99:
                    weight = float(weights.get(stat, 0))
                    # Diminishing returns are deliberately simple and visible.
                    marginal += weight * (1.0 / (1.0 + max(0, current - 70) / 12.0))
            if marginal > 0:
                choices.append((marginal / cost, category, cost))
        if not choices:
            break
        _, chosen, cost = max(choices, key=lambda item: (item[0], item[1]))
        allocation[chosen] += 1
        spent += cost
    result = calculate_build(base, allocation, level, boosts)
    stats = result["final_stats"]
    denominator = sum(weights.values()) or 1
    result["role_fit_score"] = round(sum(stats.get(k, 0) * v for k, v in weights.items()) / denominator, 2)
    result["optimization"] = "Heurística de adequação à posição; não otimiza nem prevê o Overall Rating oficial."
    result["position"] = str(position or "").upper()
    return result


def register_efootball(app, Base, engine, Player, auth, get_db, log):
    class PlayerBuild(Base):
        __tablename__ = "efootball_player_builds"
        id: Mapped[int] = mapped_column(primary_key=True)
        player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True, index=True)
        card_name: Mapped[str] = mapped_column(String(120), default="")
        card_type: Mapped[str] = mapped_column(String(60), default="")
        name: Mapped[str] = mapped_column(String(100), default="Build principal")
        position: Mapped[str] = mapped_column(String(30), default="")
        booster: Mapped[str] = mapped_column(String(100), default="")
        level: Mapped[int] = mapped_column(Integer, default=1)
        max_level: Mapped[int] = mapped_column(Integer, default=30)
        overall: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        progression: Mapped[str] = mapped_column(Text, default="{}")
        attributes: Mapped[str] = mapped_column(Text, default="{}")
        booster_effects: Mapped[str] = mapped_column(Text, default="{}")
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

    def build_dict(row, player_name=None):
        base = json.loads(row.attributes or "{}")
        progression = json.loads(row.progression or "{}")
        boosts = json.loads(row.booster_effects or "{}")
        try:
            calc = calculate_build(base, progression, row.level, boosts)
        except ValueError as exc:
            calc = {"error": str(exc)}
        return {
            "id": row.id, "player_id": row.player_id, "player_name": player_name or row.card_name,
            "card_name": row.card_name, "card_type": row.card_type, "name": row.name,
            "position": row.position, "booster": row.booster, "level": row.level,
            "max_level": row.max_level, "overall": row.overall, "progression": progression,
            "attributes": base, "booster_effects": boosts, "calculation": calc,
            "notes": row.notes, "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def list_builds_logic(player_id, s):
        q = s.query(PlayerBuild).order_by(PlayerBuild.created_at.desc(), PlayerBuild.id.desc())
        if player_id:
            q = q.filter(PlayerBuild.player_id == player_id)
        rows = q.limit(300).all()
        names = {p.id: p.name for p in s.query(Player).all()}
        return [build_dict(row, names.get(row.player_id) if row.player_id else row.card_name) for row in rows]

    def save_build_logic(data, s):
        player_id = data.get("player_id")
        player = s.get(Player, int(player_id)) if player_id not in (None, "", 0, "0") else None
        if player_id not in (None, "", 0, "0") and (not player or not player.active):
            raise HTTPException(400, "Selecione um jogador ativo do elenco.")
        card_name = str(data.get("card_name") or (player.name if player else "")).strip()[:120]
        if not card_name:
            raise HTTPException(400, "Informe o nome do jogador do eFootball ou vincule alguém do elenco.")
        level = int(data.get("level") or 1)
        max_level = int(data.get("max_level") or 30)
        if not 1 <= max_level <= 60 or not 1 <= level <= max_level:
            raise HTTPException(400, "Nível deve ficar entre 1 e o nível máximo informado (até 60).")
        name = str(data.get("name") or "Build principal").strip()[:100]
        position = str(data.get("position") or "").strip().upper()[:30]
        booster = str(data.get("booster") or "").strip()[:100]
        card_type = str(data.get("card_type") or "").strip()[:60]
        overall = data.get("overall")
        if overall not in ("", None):
            overall = int(overall)
            if not 40 <= overall <= 110:
                raise HTTPException(400, "Overall deve ficar entre 40 e 110.")
        else:
            overall = None
        try:
            progression = normalize_category_points(data.get("progression") or {})
            attributes = normalize_stats(data.get("attributes") or {}, minimum=1, maximum=99)
            boosts = normalize_stats(data.get("booster_effects") or {}, minimum=0, maximum=20) if data.get("booster_effects") else {}
            calculation = calculate_build(attributes, progression, level, boosts)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))
        row = PlayerBuild(
            player_id=player.id if player else None, card_name=card_name, card_type=card_type,
            name=name, position=position, booster=booster, level=level, max_level=max_level,
            overall=overall, progression=json.dumps(progression, ensure_ascii=False),
            attributes=json.dumps(attributes, ensure_ascii=False),
            booster_effects=json.dumps(boosts, ensure_ascii=False),
            notes=str(data.get("notes") or "")[:2000],
        )
        s.add(row)
        log(s, "efootball.build.created", f"{card_name}: {name}; {calculation['spent_pp']}/{calculation['available_pp']} PP")
        s.commit()
        return build_dict(row, player.name if player else card_name)

    def save_squad_logic(data, s):
        name = str(data.get("name") or "").strip()
        formation = str(data.get("formation") or "").strip()
        lineup = data.get("lineup") or []
        if not name or not formation:
            raise HTTPException(400, "Informe o nome do plano e a formação.")
        if not isinstance(lineup, list) or len(lineup) > 18:
            raise HTTPException(400, "A escalação deve conter até 18 posições.")
        valid_ids = {p.id for p in s.query(Player).filter(Player.active.is_(True)).all()}
        cleaned, seen = [], set()
        for slot in lineup:
            if not isinstance(slot, dict):
                continue
            pid = int(slot.get("player_id") or 0)
            if pid and pid not in valid_ids:
                raise HTTPException(400, "A escalação contém jogador inativo ou inexistente.")
            if pid and pid in seen:
                raise HTTPException(400, "Um jogador não pode ocupar duas posições na mesma escalação.")
            if pid:
                seen.add(pid)
            cleaned.append({"slot": str(slot.get("slot") or "")[:30],
                            "player_id": pid or None, "role": str(slot.get("role") or "")[:40]})
        row = SquadPlan(name=name[:100], formation=formation[:30],
                        playstyle=str(data.get("playstyle") or "")[:60],
                        lineup=json.dumps(cleaned, ensure_ascii=False),
                        notes=str(data.get("notes") or "")[:2000])
        s.add(row)
        log(s, "efootball.squad_plan.created", f"{name}: {formation}")
        s.commit()
        return {"ok": True, "id": row.id}

    def list_squads_logic(s):
        rows = s.query(SquadPlan).order_by(SquadPlan.created_at.desc()).limit(100).all()
        return [{"id": row.id, "name": row.name, "formation": row.formation,
                 "playstyle": row.playstyle, "lineup": json.loads(row.lineup or "[]"),
                 "notes": row.notes, "created_at": row.created_at.isoformat() if row.created_at else None}
                for row in rows]

    def delete_build_logic(build_id, s):
        row = s.get(PlayerBuild, build_id)
        if not row:
            raise HTTPException(404, "Build não encontrada.")
        log(s, "efootball.build.deleted", f"build={build_id}; card={row.card_name}")
        s.delete(row)
        s.commit()
        return {"ok": True}

    def delete_squad_logic(plan_id, s):
        row = s.get(SquadPlan, plan_id)
        if not row:
            raise HTTPException(404, "Plano tático não encontrado.")
        log(s, "efootball.squad_plan.deleted", row.name)
        s.delete(row)
        s.commit()
        return {"ok": True}

    @app.get("/api/efootball/players")
    def efootball_players(s=Depends(get_db), _: bool = Depends(auth)):
        return [{"id": p.id, "name": p.name, "nickname": p.nickname, "position": p.position}
                for p in s.query(Player).filter(Player.active.is_(True)).order_by(Player.name).all()]

    @app.get("/api/efootball/builds")
    def list_builds(player_id: Optional[int] = None, s=Depends(get_db), _: bool = Depends(auth)):
        return list_builds_logic(player_id, s)

    @app.post("/api/efootball/builds")
    async def save_build(request: Request, s=Depends(get_db), _: bool = Depends(auth)):
        return save_build_logic(await request.json(), s)

    @app.delete("/api/efootball/builds/{build_id}")
    def delete_build(build_id: int, s=Depends(get_db), _: bool = Depends(auth)):
        return delete_build_logic(build_id, s)

    @app.post("/api/efootball/simulate")
    async def simulate(request: Request, _: bool = Depends(auth)):
        data = await request.json()
        try:
            return calculate_build(data.get("attributes") or {}, data.get("progression") or {},
                                   int(data.get("level") or 1), data.get("booster_effects") or {})
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/efootball/optimize")
    async def optimize(request: Request, _: bool = Depends(auth)):
        data = await request.json()
        try:
            return optimize_allocation(data.get("attributes") or {}, int(data.get("level") or 1),
                                       data.get("position") or "CMF", data.get("booster_effects") or {})
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/efootball/squad-plans")
    def list_squad_plans(s=Depends(get_db), _: bool = Depends(auth)):
        return list_squads_logic(s)

    @app.post("/api/efootball/squad-plans")
    async def save_squad_plan(request: Request, s=Depends(get_db), _: bool = Depends(auth)):
        return save_squad_logic(await request.json(), s)

    @app.delete("/api/efootball/squad-plans/{plan_id}")
    def delete_squad_plan(plan_id: int, s=Depends(get_db), _: bool = Depends(auth)):
        return delete_squad_logic(plan_id, s)

    @app.post("/api/efootball/import-image")
    async def import_player_image(image: UploadFile = File(...), card_name: str = Form(""),
                                  player_id: Optional[int] = Form(None),
                                  _: bool = Depends(auth)):
        if image.content_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise HTTPException(400, "Envie uma imagem PNG, JPG ou WEBP.")
        raw = await image.read()
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(413, "A imagem deve ter no máximo 8 MB.")
        try:
            picture = Image.open(io.BytesIO(raw)).convert("RGB")
            text = pytesseract.image_to_string(picture, lang="por+eng")
        except Exception as exc:
            raise HTTPException(422, "Não foi possível ler a imagem. Verifique o OCR do servidor: " + str(exc)[:160])
        parsed = {}
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            normalized = _ascii(line)
            numbers = re.findall(r"(?<![a-z])\d{1,3}(?![a-z])", normalized)
            if not numbers:
                continue
            value = int(numbers[-1])
            if value > 120:
                continue
            for label, key in STAT_ALIASES.items():
                if label in normalized:
                    parsed[key] = min(99, value)
                    break
        return {"ok": True, "card_name": card_name, "player_id": player_id,
                "attributes": parsed, "raw_text": text[:6000], "review_required": True,
                "message": "Rascunho de OCR. Confira os valores e salve a build manualmente."}

    return PlayerBuild, SquadPlan


def register_efootball_mobile(router, PlayerBuild, SquadPlan, get_db, admin_only, log):
    """Register equivalent endpoints protected by the Android app's Bearer admin session."""
    def _build_dict(row, player_name=None):
        base = json.loads(row.attributes or "{}")
        progression = json.loads(row.progression or "{}")
        boosts = json.loads(row.booster_effects or "{}")
        try:
            calc = calculate_build(base, progression, row.level, boosts)
        except ValueError as exc:
            calc = {"error": str(exc)}
        return {"id": row.id, "player_id": row.player_id, "player_name": player_name or row.card_name,
                "card_name": row.card_name, "card_type": row.card_type, "name": row.name,
                "position": row.position, "booster": row.booster, "level": row.level,
                "max_level": row.max_level, "overall": row.overall, "progression": progression,
                "attributes": base, "booster_effects": boosts, "calculation": calc,
                "notes": row.notes, "created_at": row.created_at.isoformat() if row.created_at else None}

    @router.get("/efootball/builds")
    def mobile_list_builds(player_id: Optional[int] = None, s=Depends(get_db), _: bool = Depends(admin_only)):
        rows = s.query(PlayerBuild).order_by(PlayerBuild.created_at.desc(), PlayerBuild.id.desc()).limit(300).all()
        names = {p.id: p.name for p in s.query(__import__("app").Player).all()}
        return [_build_dict(row, names.get(row.player_id) if row.player_id else row.card_name)
                for row in rows if not player_id or row.player_id == player_id]

    @router.post("/efootball/builds")
    async def mobile_save_build(request: Request, s=Depends(get_db), _: bool = Depends(admin_only)):
        data = await request.json()
        # Reuse the browser endpoint's validated service logic through its stored handler.
        handler = next(route.endpoint for route in app_routes if route.path == "/api/efootball/builds" and route.methods == {"POST"})
        return handler

    @router.post("/efootball/simulate")
    async def mobile_simulate(request: Request, _: bool = Depends(admin_only)):
        data = await request.json()
        try:
            return calculate_build(data.get("attributes") or {}, data.get("progression") or {},
                                   int(data.get("level") or 1), data.get("booster_effects") or {})
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))
