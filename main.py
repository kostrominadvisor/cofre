# -*- coding: utf-8 -*-
"""
MEU COFRE - App mobile em Python (Kivy + KivyMD)
Organizador geral: Comidas, Plantas, Assinaturas, Afazeres, Artesanato, Lembretes.
Permite salvar itens manualmente ou colando um link (YouTube, Instagram, TikTok,
Facebook), buscando automaticamente thumbnail/título/descrição quando possível.

Como rodar:
    pip install -r requirements.txt
    python main.py

Empacotar para Android (depois de testar no PC):
    pip install buildozer
    buildozer init
    buildozer -v android debug
"""

import json
import os
import re
import sqlite3
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from kivy.animation import Animation
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.metrics import dp

from kivymd.app import MDApp
from kivymd.uix.dialog import MDDialog
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.list import OneLineListItem
from kivymd.uix.snackbar import Snackbar

# --------------------------------------------------------------------------
# CONFIG GERAL
# --------------------------------------------------------------------------

CATEGORIAS = ["Comidas", "Plantas", "Assinaturas", "Afazeres", "Artesanato", "Lembretes"]

CATEGORIA_ICONE = {
    "Comidas": "food-drumstick",
    "Plantas": "flower",
    "Assinaturas": "credit-card-outline",
    "Afazeres": "checkbox-marked-outline",
    "Artesanato": "scissors-cutting",
    "Lembretes": "bell-outline",
}

CATEGORIA_COR = {
    "Comidas": (0.95, 0.55, 0.25, 1),
    "Plantas": (0.30, 0.75, 0.40, 1),
    "Assinaturas": (0.35, 0.55, 0.95, 1),
    "Afazeres": (0.85, 0.30, 0.45, 1),
    "Artesanato": (0.75, 0.45, 0.85, 1),
    "Lembretes": (0.95, 0.80, 0.20, 1),
}

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meu_cofre.db")


# --------------------------------------------------------------------------
# BANCO DE DADOS
# --------------------------------------------------------------------------

class Database:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._criar_tabela()

    def _criar_tabela(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                titulo TEXT NOT NULL,
                descricao TEXT,
                url TEXT,
                thumbnail TEXT,
                origem TEXT,
                feito INTEGER DEFAULT 0,
                criado_em REAL
            )
        """)
        self.conn.commit()

    def adicionar(self, categoria, titulo, descricao="", url="", thumbnail="", origem=""):
        cur = self.conn.execute(
            "INSERT INTO itens (categoria, titulo, descricao, url, thumbnail, origem, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (categoria, titulo, descricao, url, thumbnail, origem, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def listar(self, categoria=None, busca=""):
        query = "SELECT * FROM itens"
        cond = []
        params = []
        if categoria:
            cond.append("categoria = ?")
            params.append(categoria)
        if busca:
            cond.append("(titulo LIKE ? OR descricao LIKE ?)")
            params.extend([f"%{busca}%", f"%{busca}%"])
        if cond:
            query += " WHERE " + " AND ".join(cond)
        query += " ORDER BY criado_em DESC"
        return self.conn.execute(query, params).fetchall()

    def alternar_feito(self, item_id):
        row = self.conn.execute("SELECT feito FROM itens WHERE id=?", (item_id,)).fetchone()
        novo = 0 if row["feito"] else 1
        self.conn.execute("UPDATE itens SET feito=? WHERE id=?", (novo, item_id))
        self.conn.commit()

    def remover(self, item_id):
        self.conn.execute("DELETE FROM itens WHERE id=?", (item_id,))
        self.conn.commit()


# --------------------------------------------------------------------------
# BUSCADOR DE METADADOS DE LINKS (YouTube / Instagram / TikTok / Facebook)
# --------------------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
}


def identificar_origem(url):
    dominio = urlparse(url).netloc.lower()
    if "youtube" in dominio or "youtu.be" in dominio:
        return "YouTube"
    if "instagram" in dominio:
        return "Instagram"
    if "tiktok" in dominio:
        return "TikTok"
    if "facebook" in dominio or "fb.watch" in dominio:
        return "Facebook"
    return "Link"


def buscar_metadados(url):
    """
    Retorna dict: {titulo, descricao, thumbnail, origem}
    Usa oEmbed oficial do YouTube (mais confiável) e Open Graph (og:) para
    Instagram/TikTok/Facebook. Se a rede bloquear o acesso sem login,
    o link ainda é salvo, só sem thumbnail/descrição.
    """
    origem = identificar_origem(url)
    resultado = {"titulo": url, "descricao": "", "thumbnail": "", "origem": origem}

    try:
        if origem == "YouTube":
            resp = requests.get(
                "https://www.youtube.com/oembed",
                params={"url": url, "format": "json"},
                headers=HEADERS, timeout=8,
            )
            if resp.ok:
                data = resp.json()
                resultado["titulo"] = data.get("title", url)
                resultado["descricao"] = f"Por {data.get('author_name', '')}"
                resultado["thumbnail"] = data.get("thumbnail_url", "")
                return resultado

        if origem == "TikTok":
            resp = requests.get(
                "https://www.tiktok.com/oembed", params={"url": url},
                headers=HEADERS, timeout=8,
            )
            if resp.ok:
                data = resp.json()
                resultado["titulo"] = data.get("title", url)
                resultado["descricao"] = f"Por {data.get('author_name', '')}"
                resultado["thumbnail"] = data.get("thumbnail_url", "")
                return resultado

        # Fallback genérico via Open Graph (Instagram, Facebook, outros sites)
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.ok:
            soup = BeautifulSoup(resp.text, "html.parser")

            def meta(prop):
                tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
                return tag["content"].strip() if tag and tag.get("content") else ""

            resultado["titulo"] = meta("og:title") or (soup.title.string if soup.title else url)
            resultado["descricao"] = meta("og:description")
            resultado["thumbnail"] = meta("og:image")
    except Exception:
        # Rede indisponível, bloqueio de bot, ou site exige login: mantemos o link puro.
        pass

    return resultado


# --------------------------------------------------------------------------
# INTERFACE (KV) - tema escuro, abas, busca, cards e animações
# --------------------------------------------------------------------------

KV = """
#:import dp kivy.metrics.dp

<ItemCard>:
    orientation: "vertical"
    size_hint_y: None
    height: self.minimum_height
    padding: dp(12)
    spacing: dp(6)
    md_bg_color: 0.11, 0.11, 0.13, 1
    radius: [dp(16)]
    opacity: 0

    MDBoxLayout:
        size_hint_y: None
        height: dp(90) if root.thumbnail else 0
        spacing: dp(10)

        AsyncImage:
            source: root.thumbnail if root.thumbnail else ""
            size_hint_x: None
            width: dp(120) if root.thumbnail else 0
            allow_stretch: True
            keep_ratio: True
            radius: [dp(12)]

    MDLabel:
        text: root.titulo
        bold: True
        theme_text_color: "Custom"
        text_color: 1, 1, 1, 1
        font_style: "Subtitle1"
        size_hint_y: None
        height: self.texture_size[1]

    MDLabel:
        text: root.descricao
        theme_text_color: "Custom"
        text_color: 0.75, 0.75, 0.78, 1
        font_style: "Caption"
        size_hint_y: None
        height: self.texture_size[1] if root.descricao else 0

    MDBoxLayout:
        size_hint_y: None
        height: dp(30)
        spacing: dp(8)

        MDLabel:
            text: root.origem
            theme_text_color: "Custom"
            text_color: root.cor_categoria
            font_style: "Caption"
            bold: True

        Widget:

        MDIconButton:
            icon: "check-circle-outline" if not root.feito else "check-circle"
            theme_text_color: "Custom"
            text_color: (0.3, 0.85, 0.4, 1) if root.feito else (0.6, 0.6, 0.6, 1)
            on_release: root.on_toggle(root.item_id) if root.on_toggle else None
            opacity: 1 if root.mostrar_check else 0
            disabled: not root.mostrar_check

        MDIconButton:
            icon: "trash-can-outline"
            theme_text_color: "Custom"
            text_color: 0.7, 0.3, 0.3, 1
            on_release: root.on_remove(root.item_id) if root.on_remove else None


MDScreen:
    md_bg_color: 0, 0, 0, 1

    MDBoxLayout:
        orientation: "vertical"

        MDTopAppBar:
            title: "Meu Cofre"
            md_bg_color: 0.05, 0.05, 0.06, 1
            specific_text_color: 1, 1, 1, 1
            elevation: 0
            right_action_items: [["magnify", lambda x: app.alternar_busca()]]

        MDTextField:
            id: campo_busca
            hint_text: "Buscar por titulo ou descricao..."
            icon_right: "magnify"
            mode: "rectangle"
            size_hint_y: None
            height: 0
            opacity: 0
            padding: [dp(16), dp(8), dp(16), 0]
            on_text: app.buscar(self.text)

        MDTabs:
            id: abas
            background_color: 0.05, 0.05, 0.06, 1
            text_color_normal: 0.6, 0.6, 0.65, 1
            text_color_active: 1, 1, 1, 1
            indicator_color: 0.2, 0.85, 0.65, 1

    MDFloatingActionButton:
        id: fab
        icon: "plus"
        md_bg_color: 0.2, 0.85, 0.65, 1
        pos_hint: {"right": 0.95, "y": 0.04}
        on_release: app.abrir_dialogo_adicionar()
"""


# --------------------------------------------------------------------------
# WIDGETS
# --------------------------------------------------------------------------

class ItemCard(BoxLayout):
    item_id = None
    titulo = StringProperty("")
    descricao = StringProperty("")
    thumbnail = StringProperty("")
    origem = StringProperty("")
    feito = BooleanProperty(False)
    mostrar_check = BooleanProperty(False)
    cor_categoria = ListProperty([1, 1, 1, 1])
    on_toggle = None
    on_remove = None

    def animar_entrada(self):
        Animation(opacity=1, d=0.35, t="out_quad").start(self)


# --------------------------------------------------------------------------
# APP PRINCIPAL
# --------------------------------------------------------------------------

class MeuCofreApp(MDApp):
    busca_visivel = False
    categoria_selecionada = StringProperty(CATEGORIAS[0])
    link_dialog = None
    add_dialog = None
    menu_categoria = None

    def build(self):
        self.title = "Meu Cofre"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Teal"
        Window.clearcolor = (0, 0, 0, 1)

        self.db = Database()
        self.root_widget = Builder.load_string(KV)
        self._montar_abas()
        return self.root_widget

    # ---------------- ABAS / LISTAS ----------------

    def _montar_abas(self):
        from kivymd.uix.tab import MDTabsBase
        from kivymd.uix.floatlayout import FloatLayout
        from kivymd.uix.scrollview import MDScrollView
        from kivymd.uix.boxlayout import MDBoxLayout

        class Aba(FloatLayout, MDTabsBase):
            pass

        abas_widget = self.root_widget.ids.abas
        self.listas = {}

        for cat in CATEGORIAS:
            aba = Aba(title=cat, icon=CATEGORIA_ICONE[cat])
            scroll = MDScrollView()
            lista = MDBoxLayout(orientation="vertical", spacing=dp(10),
                                 padding=dp(12), size_hint_y=None)
            lista.bind(minimum_height=lista.setter("height"))
            scroll.add_widget(lista)
            aba.add_widget(scroll)
            abas_widget.add_widget(aba)
            self.listas[cat] = lista

        self.atualizar_todas_listas()

    def atualizar_todas_listas(self, busca=""):
        for cat in CATEGORIAS:
            self._atualizar_lista(cat, busca)

    def _atualizar_lista(self, categoria, busca=""):
        container = self.listas[categoria]
        container.clear_widgets()
        registros = self.db.listar(categoria=categoria, busca=busca)

        if not registros:
            item_vazio = OneLineListItem(text="Nada por aqui ainda. Toque em + para adicionar.")
            container.add_widget(item_vazio)
            return

        mostrar_check = categoria == "Afazeres"
        for r in registros:
            card = ItemCard()
            card.item_id = r["id"]
            card.titulo = r["titulo"]
            card.descricao = r["descricao"] or ""
            card.thumbnail = r["thumbnail"] or ""
            card.origem = r["origem"] or categoria
            card.feito = bool(r["feito"])
            card.mostrar_check = mostrar_check
            card.cor_categoria = CATEGORIA_COR[categoria]
            card.on_toggle = self.alternar_feito
            card.on_remove = self.remover_item
            container.add_widget(card)
            card.animar_entrada()

    def alternar_feito(self, item_id):
        self.db.alternar_feito(item_id)
        self.atualizar_todas_listas(self.root_widget.ids.campo_busca.text)

    def remover_item(self, item_id):
        self.db.remover(item_id)
        self.atualizar_todas_listas(self.root_widget.ids.campo_busca.text)

    # ---------------- BUSCA ----------------

    def alternar_busca(self):
        campo = self.root_widget.ids.campo_busca
        self.busca_visivel = not self.busca_visivel
        altura = dp(56) if self.busca_visivel else 0
        opacidade = 1 if self.busca_visivel else 0
        Animation(height=altura, opacity=opacidade, d=0.25, t="out_quad").start(campo)
        if not self.busca_visivel:
            campo.text = ""

    def buscar(self, texto):
        self.atualizar_todas_listas(texto)

    # ---------------- ADICIONAR ITEM ----------------

    def abrir_dialogo_adicionar(self):
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.button import MDRaisedButton, MDFlatButton
        from kivymd.uix.textfield import MDTextField

        Animation(icon="close", d=0.15).start(self.root_widget.ids.fab) \
            if hasattr(self.root_widget.ids.fab, "icon") else None

        self.categoria_selecionada = CATEGORIAS[0]

        conteudo = MDBoxLayout(orientation="vertical", spacing=dp(12),
                                size_hint_y=None, height=dp(230), padding=dp(4))

        self.campo_categoria = MDRaisedButton(text=f"Categoria: {self.categoria_selecionada}")
        self.campo_categoria.bind(on_release=self._abrir_menu_categoria)

        self.campo_link = MDTextField(hint_text="Cole um link (YouTube, Instagram, TikTok, Facebook)")
        self.campo_titulo = MDTextField(hint_text="Ou digite um titulo manualmente")
        self.campo_desc = MDTextField(hint_text="Descricao (opcional)")

        conteudo.add_widget(self.campo_categoria)
        conteudo.add_widget(self.campo_link)
        conteudo.add_widget(self.campo_titulo)
        conteudo.add_widget(self.campo_desc)

        self.add_dialog = MDDialog(
            title="Adicionar novo item",
            type="custom",
            content_cls=conteudo,
            buttons=[
                MDFlatButton(text="CANCELAR", on_release=lambda x: self.add_dialog.dismiss()),
                MDRaisedButton(text="SALVAR", on_release=lambda x: self._salvar_novo_item()),
            ],
        )
        self.add_dialog.open()

    def _abrir_menu_categoria(self, botao):
        itens = [
            {
                "text": cat,
                "on_release": lambda c=cat: self._escolher_categoria(c),
            }
            for cat in CATEGORIAS
        ]
        self.menu_categoria = MDDropdownMenu(caller=botao, items=itens, width_mult=4)
        self.menu_categoria.open()

    def _escolher_categoria(self, categoria):
        self.categoria_selecionada = categoria
        self.campo_categoria.text = f"Categoria: {categoria}"
        if self.menu_categoria:
            self.menu_categoria.dismiss()

    def _salvar_novo_item(self):
        link = self.campo_link.text.strip()
        titulo_manual = self.campo_titulo.text.strip()
        desc_manual = self.campo_desc.text.strip()
        categoria = self.categoria_selecionada

        if link:
            meta = buscar_metadados(link)
            titulo = titulo_manual or meta["titulo"]
            descricao = desc_manual or meta["descricao"]
            self.db.adicionar(
                categoria=categoria, titulo=titulo, descricao=descricao,
                url=link, thumbnail=meta["thumbnail"], origem=meta["origem"],
            )
            Snackbar(text=f"Salvo de {meta['origem']}!").open()
        elif titulo_manual:
            self.db.adicionar(categoria=categoria, titulo=titulo_manual,
                               descricao=desc_manual, origem=categoria)
            Snackbar(text="Item salvo!").open()
        else:
            Snackbar(text="Digite um titulo ou cole um link.").open()
            return

        self.add_dialog.dismiss()
        self.atualizar_todas_listas()


if __name__ == "__main__":
    MeuCofreApp().run()
