import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:///./test_arqueiros_efootball_ci.db"
os.environ["ADMIN_PANEL_TOKEN"] = "ci-admin-secret"
os.environ["MOBILE_AUTH_SECRET"] = "ci-mobile-secret"

from fastapi.testclient import TestClient
from app import app, SessionLocal
from mobile_api import MobileUser, _password_hash

client = TestClient(app)


class EFootballApiTests(unittest.TestCase):
    def test_web_api_requires_admin_token(self):
        response = client.get("/api/efootball/builds")
        self.assertEqual(response.status_code, 401)

    def test_web_build_create_and_simulation(self):
        headers = {"x-admin-token": "ci-admin-secret"}
        payload = {
            "card_name": "Pavel Nedved CI",
            "name": "Meia versátil",
            "position": "AMF",
            "level": 3,
            "max_level": 30,
            "attributes": {"speed": 90, "stamina": 85, "kicking_power": 80},
            "progression": {"LBS": 4},
            "booster_effects": {"speed": 2},
        }
        response = client.post("/api/efootball/builds", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()
        self.assertEqual(saved["calculation"]["spent_pp"], 4)
        self.assertEqual(saved["calculation"]["available_pp"], 4)
        self.assertEqual(saved["calculation"]["final_stats"]["speed"], 96)

        simulation = client.post("/api/efootball/simulate", json=payload, headers=headers)
        self.assertEqual(simulation.status_code, 200, simulation.text)
        self.assertEqual(simulation.json()["final_stats"]["speed"], 96)

    def test_android_admin_session_can_use_efootball_api(self):
        login = client.post("/api/mobile/auth/login", json={
            "username": "admin", "password": "ci-admin-secret"
        })
        self.assertEqual(login.status_code, 200, login.text)
        token = login.json()["access_token"]
        response = client.get("/api/mobile/efootball/builds", headers={
            "Authorization": "Bearer " + token
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("builds", response.json())

    def test_member_account_cannot_login(self):
        with SessionLocal() as session:
            if not session.query(MobileUser).filter_by(username="member-ci").first():
                session.add(MobileUser(
                    username="member-ci",
                    password_hash=_password_hash("member-password"),
                    role="member",
                    active=True,
                ))
                session.commit()
        response = client.post("/api/mobile/auth/login", json={
            "username": "member-ci", "password": "member-password"
        })
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
