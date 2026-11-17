"""Rooktest: de Streamlit-app start zonder fouten (zonder bestand en met wachtwoord)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_start_zonder_fouten():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("Nog geen bestand" in i.value for i in at.info)


def test_wachtwoord_blokkeert_toegang():
    at = AppTest.from_file(APP, default_timeout=30)
    at.secrets["APP_WACHTWOORD"] = "geheim"
    at.run()
    assert not at.exception
    assert not at.info  # hoofdscherm niet zichtbaar
    at.text_input[0].input("fout")
    at.button[0].click().run()
    assert any("Onjuist" in e.value for e in at.error)
    at.text_input[0].input("geheim")
    at.button[0].click().run()
    assert any("Nog geen bestand" in i.value for i in at.info)
