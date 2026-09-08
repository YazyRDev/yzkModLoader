"""
yzkModLoader
-------------
App desktop para buscar e baixar mods, resource packs e plugins do Modrinth,
com opcao de enviar plugins direto para um servidor Purpur via SFTP.

Tambem cria e compartilha modpacks (.yzk) e pacotes de resource packs (.yzkrp)
customizados, com associacao automatica de extensao no Windows.

Repositorio: https://github.com/YzkModLoad/yzkModLoader
Licenca: MIT (veja LICENSE)

Requisitos:
    pip install -r requirements.txt
"""

import os
import sys
import json
import threading
import queue
import webbrowser
import platform
from pathlib import Path

import requests
import customtkinter as ctk
from tkinter import filedialog, messagebox

try:
    import paramiko
    PARAMIKO_OK = True
except ImportError:
    PARAMIKO_OK = False

try:
    import winreg
    WINREG_OK = (platform.system() == "Windows")
except ImportError:
    WINREG_OK = False

try:
    import ctypes
except ImportError:
    ctypes = None


# ----------------------------------------------------------------------
# Configuracao geral
# ----------------------------------------------------------------------

APP_NAME = "yzkModLoader"
CONFIG_PATH = Path.home() / ".yzkmodloader_config.json"
MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "YzkModLoad/yzkModLoader/1.0 (https://github.com/YzkModLoad/yzkModLoader)"

YZK_EXTENSION = ".yzk"
YZKRP_EXTENSION = ".yzkrp"
MODPACKS_DIR = Path.home() / "yzkModLoader" / "Meus Modpacks"
RPACKS_DIR = Path.home() / "yzkModLoader" / "Meus Resource Packs"

# Loaders de mod suportados na busca/filtro. "Qualquer" nao aplica filtro de loader.
MOD_LOADERS = ["Qualquer", "Fabric", "Forge", "NeoForge", "Quilt"]

# Popular a lista de mods "em alta" assim que a aba Mods e aberta
POPULAR_MODS_QUERY = ""  # busca vazia + sort por downloads = mods mais populares

# Caminho do icone customizado (.ico). Coloque um arquivo icon.ico na mesma pasta
# do script (ou do .exe, quando compilado com PyInstaller --add-data) para que
# a janela do app e o registro no Windows usem esse icone.
def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

ICON_PATH = get_base_dir() / "icon.ico"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Paleta customizada (estilo Modrinth: verde/escuro)
COL_BG = "#0f1113"
COL_PANEL = "#17191c"
COL_PANEL_2 = "#1e2124"
COL_ACCENT = "#1bd96a"
COL_ACCENT_HOVER = "#17b859"
COL_TEXT_DIM = "#9aa0a6"
COL_BORDER = "#2a2d31"


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


# ----------------------------------------------------------------------
# Formato .yzk (modpacks)
# ----------------------------------------------------------------------

def build_yzk_data(name: str, mc_version: str, loader: str, mods: list, resourcepacks: list = None):
    """Monta a estrutura de dados de um modpack .yzk."""
    return {
        "format": "yzkmodloader-pack",
        "format_version": 1,
        "name": name,
        "mc_version": mc_version,
        "loader": loader,
        "mods": mods,               # lista de {"project_id":..., "title":...}
        "resourcepacks": resourcepacks or [],
    }


def save_yzk_file(data: dict, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest_path


def load_yzk_file(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def list_my_modpacks():
    MODPACKS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(MODPACKS_DIR.glob(f"*{YZK_EXTENSION}"))


def build_yzkrp_data(name: str, mc_version: str, resourcepacks: list):
    """Monta a estrutura de dados de um pacote de resource packs .yzkrp."""
    return {
        "format": "yzkmodloader-rpack",
        "format_version": 1,
        "name": name,
        "mc_version": mc_version,
        "resourcepacks": resourcepacks,  # lista de {"project_id":..., "title":..., "filename":...}
    }


def save_yzkrp_file(data: dict, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest_path


def load_yzkrp_file(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def list_my_rpacks():
    RPACKS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(RPACKS_DIR.glob(f"*{YZKRP_EXTENSION}"))


# Extensoes de arquivo reconhecidas em cada tipo de pasta, para escanear o que
# ja esta baixado localmente (mesmo de sessoes/instancias anteriores).
MOD_FILE_EXTENSIONS = (".jar",)
RESOURCEPACK_FILE_EXTENSIONS = (".zip",)


def scan_folder_items(folder: str, extensions: tuple) -> list:
    """
    Lista os arquivos de uma pasta local que batem com as extensoes dadas.
    Identificacao simples por nome de arquivo (sem checar hash/API) — cada
    item vira {"project_id": "", "title": nome_sem_extensao, "filename": nome_completo}.
    """
    items = []
    if not folder:
        return items
    p = Path(folder)
    if not p.is_dir():
        return items
    for f in sorted(p.iterdir()):
        if f.is_file() and f.suffix.lower() in extensions:
            items.append({"project_id": "", "title": f.stem, "filename": f.name})
    return items


# ----------------------------------------------------------------------
# Registro da extensão .yzk no Windows (auto-associacao)
# ----------------------------------------------------------------------

def get_launch_command() -> str:
    """
    Monta o comando usado para reabrir o app com um arquivo .yzk como argumento.
    Funciona tanto rodando via 'python yzkModLoader.py' quanto empacotado como .exe
    (ex: com PyInstaller, onde sys.frozen existe).
    """
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return f'"{exe}" "%1"'
    else:
        python_exe = sys.executable
        script_path = str(Path(__file__).resolve())
        return f'"{python_exe}" "{script_path}" "%1"'


def _is_running_as_admin() -> bool:
    if not (WINREG_OK and ctypes):
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _extension_registered(extension: str, prog_id: str, root=None) -> bool:
    """Confere se a extensao ja aponta pro comando de lancamento atual, em HKCR/HKLM."""
    if not WINREG_OK:
        return False
    root = root if root is not None else winreg.HKEY_CLASSES_ROOT
    try:
        with winreg.OpenKey(root, rf"Software\Classes\{extension}" if root == winreg.HKEY_CURRENT_USER else extension) as key:
            current_progid, _ = winreg.QueryValueEx(key, "")
        base = rf"Software\Classes\{current_progid}" if root == winreg.HKEY_CURRENT_USER else current_progid
        with winreg.OpenKey(root, base + r"\shell\open\command") as cmd_key:
            current_cmd, _ = winreg.QueryValueEx(cmd_key, "")
        return current_cmd == get_launch_command() and current_progid == prog_id
    except Exception:
        return False


def is_yzk_registered() -> bool:
    return _extension_registered(YZK_EXTENSION, "yzkModLoader.Modpack")


def is_yzkrp_registered() -> bool:
    return _extension_registered(YZKRP_EXTENSION, "yzkModLoader.RPack")


def _write_extension_keys(root, extension: str, prog_id: str, friendly_name: str, launch_cmd: str):
    """
    Escreve as chaves de associacao de extensao. Quando root=HKEY_CLASSES_ROOT,
    a associacao vale para TODOS os usuarios da maquina (exige admin). O caminho
    de chave e diferente conforme a hive usada.
    """
    if root == winreg.HKEY_CURRENT_USER:
        ext_key_path = rf"Software\Classes\{extension}"
        progid_key_path = rf"Software\Classes\{prog_id}"
        cmd_key_path = rf"Software\Classes\{prog_id}\shell\open\command"
    else:
        ext_key_path = extension
        progid_key_path = prog_id
        cmd_key_path = rf"{prog_id}\shell\open\command"

    with winreg.CreateKey(root, ext_key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, prog_id)

    with winreg.CreateKey(root, progid_key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, friendly_name)
        if ICON_PATH.exists():
            with winreg.CreateKey(root, progid_key_path + r"\DefaultIcon") as icon_key:
                winreg.SetValueEx(icon_key, "", 0, winreg.REG_SZ, str(ICON_PATH))

    with winreg.CreateKey(root, cmd_key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, launch_cmd)


def register_extensions_as_admin() -> bool:
    """
    Associa .yzk e .yzkrp ao yzkModLoader em HKEY_CLASSES_ROOT, valendo para
    TODOS os usuarios da maquina. Isso exige privilegios de administrador —
    se o processo atual nao for admin, relanca o proprio app elevado via UAC
    (o Windows mostra o prompt "Permitir que este app faça alterações?").
    """
    if not WINREG_OK:
        return False

    if not _is_running_as_admin():
        return _relaunch_as_admin_for_registration()

    try:
        launch_cmd = get_launch_command()
        _write_extension_keys(
            winreg.HKEY_CLASSES_ROOT, YZK_EXTENSION, "yzkModLoader.Modpack",
            "Modpack do yzkModLoader", launch_cmd,
        )
        _write_extension_keys(
            winreg.HKEY_CLASSES_ROOT, YZKRP_EXTENSION, "yzkModLoader.RPack",
            "Pacote de Resource Packs do yzkModLoader", launch_cmd,
        )
        try:
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _relaunch_as_admin_for_registration() -> bool:
    """
    Relanca o app com privilegios elevados (UAC) apenas para registrar as
    extensoes, passando uma flag interna que o app detecta na inicializacao.
    Retorna False aqui pois o registro real acontece no processo elevado.
    """
    if not (WINREG_OK and ctypes):
        return False
    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = "--register-extensions"
        else:
            exe = sys.executable
            params = f'"{Path(__file__).resolve()}" --register-extensions'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return False
    except Exception:
        return False


# ----------------------------------------------------------------------
# Cliente da API do Modrinth
# ----------------------------------------------------------------------

class ModrinthClient:
    def __init__(self, api_key: str = ""):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.set_api_key(api_key)

    def set_api_key(self, api_key: str):
        # A API de busca/download nao exige chave. A chave (PAT) so e usada
        # para endpoints autenticados (ex: dados da propria conta).
        if api_key:
            self.session.headers["Authorization"] = api_key
        else:
            self.session.headers.pop("Authorization", None)

    def search(self, query: str, project_type: str, loader: str = "", limit: int = 20, index: str = "relevance"):
        facets = [[f"project_type:{project_type}"]]
        if loader:
            facets.append([f"categories:{loader}"])
        params = {
            "query": query,
            "limit": limit,
            "facets": json.dumps(facets),
            "index": index,
        }
        r = self.session.get(f"{MODRINTH_API}/search", params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("hits", [])

    def get_versions(self, project_id: str, loader: str = "", game_version: str = ""):
        params = {}
        if loader:
            params["loaders"] = json.dumps([loader])
        if game_version:
            params["game_versions"] = json.dumps([game_version])
        r = self.session.get(
            f"{MODRINTH_API}/project/{project_id}/version", params=params, timeout=15
        )
        r.raise_for_status()
        return r.json()

    def get_project(self, project_id: str):
        r = self.session.get(f"{MODRINTH_API}/project/{project_id}", timeout=15)
        r.raise_for_status()
        return r.json()

    def get_game_versions(self, releases_only: bool = True):
        """Retorna a lista de versoes do Minecraft conhecidas pelo Modrinth,
        da mais nova pra mais antiga. Usado para preencher o seletor de
        versao e evitar erro de digitacao."""
        r = self.session.get(f"{MODRINTH_API}/tag/game_version", timeout=15)
        r.raise_for_status()
        data = r.json()
        if releases_only:
            data = [v for v in data if v.get("version_type") == "release"]
        return [v["version"] for v in data]

    def download_file(self, url: str, dest_path: Path, progress_cb=None):
        with self.session.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        if progress_cb and total:
                            progress_cb(done / total)
        return dest_path


# ----------------------------------------------------------------------
# Widget: linha de resultado de busca
# ----------------------------------------------------------------------

class ResultRow(ctk.CTkFrame):
    def __init__(self, master, hit, on_download, button_text="Baixar", bulk_mode=False,
                 on_toggle_select=None, selected=False, **kwargs):
        super().__init__(master, fg_color=COL_PANEL_2, corner_radius=10, **kwargs)
        self.hit = hit
        self.on_download = on_download
        self.bulk_mode = bulk_mode
        self.on_toggle_select = on_toggle_select

        col_offset = 1 if bulk_mode else 0
        self.grid_columnconfigure(1 + col_offset, weight=1)

        title = hit.get("title", "Sem nome")
        desc = hit.get("description", "")
        downloads = hit.get("downloads", 0)
        author = hit.get("author", "")

        if bulk_mode:
            self.select_var = ctk.BooleanVar(value=selected)
            check = ctk.CTkCheckBox(
                self, text="", variable=self.select_var, width=20,
                fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER, border_color=COL_BORDER,
                command=lambda: self.on_toggle_select(self.hit, self.select_var.get()),
            )
            check.grid(row=0, column=0, rowspan=3, padx=(14, 0), pady=10, sticky="n")

        name_lbl = ctk.CTkLabel(
            self, text=title, font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        )
        name_lbl.grid(row=0, column=col_offset, columnspan=2, sticky="w", padx=14, pady=(10, 0))

        meta = f"por {author}  ·  {downloads:,} downloads".replace(",", ".")
        meta_lbl = ctk.CTkLabel(
            self, text=meta, font=ctk.CTkFont(size=11), text_color=COL_TEXT_DIM, anchor="w"
        )
        meta_lbl.grid(row=1, column=col_offset, columnspan=2, sticky="w", padx=14, pady=(0, 2))

        desc_lbl = ctk.CTkLabel(
            self,
            text=(desc[:110] + "...") if len(desc) > 110 else desc,
            font=ctk.CTkFont(size=12),
            text_color="#c7cacd",
            anchor="w",
            justify="left",
            wraplength=500 if bulk_mode else 520,
        )
        desc_lbl.grid(row=2, column=col_offset, columnspan=2, sticky="w", padx=14, pady=(0, 10))

        btn = ctk.CTkButton(
            self,
            text=button_text,
            width=90,
            fg_color=COL_ACCENT,
            hover_color=COL_ACCENT_HOVER,
            text_color="#0b0d0e",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self.on_download(self.hit),
        )
        btn.grid(row=0, column=2 + col_offset, rowspan=3, padx=14, pady=10, sticky="e")
        self.grid_columnconfigure(2 + col_offset, weight=0)


# ----------------------------------------------------------------------
# Widget: linha de modpack local (.yzk)
# ----------------------------------------------------------------------

class ModpackRow(ctk.CTkFrame):
    def __init__(self, master, pack_path: Path, data: dict, on_install, on_open_folder, **kwargs):
        super().__init__(master, fg_color=COL_PANEL_2, corner_radius=10, **kwargs)
        self.pack_path = pack_path
        self.data = data
        self.on_install = on_install
        self.on_open_folder = on_open_folder

        self.grid_columnconfigure(1, weight=1)

        name = data.get("name", pack_path.stem)
        mc_version = data.get("mc_version", "?")
        loader = data.get("loader", "?")
        n_mods = len(data.get("mods", []))

        name_lbl = ctk.CTkLabel(
            self, text=name, font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        )
        name_lbl.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 0))

        meta = f"MC {mc_version}  ·  {loader}  ·  {n_mods} mod(s)  ·  {pack_path.name}"
        meta_lbl = ctk.CTkLabel(
            self, text=meta, font=ctk.CTkFont(size=11), text_color=COL_TEXT_DIM, anchor="w"
        )
        meta_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 10))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=2, rowspan=2, padx=14, pady=10, sticky="e")

        install_btn = ctk.CTkButton(
            btn_frame, text="Reinstalar", width=100,
            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER, text_color="#0b0d0e",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self.on_install(self.pack_path, self.data),
        )
        install_btn.pack(side="left", padx=(0, 6))

        folder_btn = ctk.CTkButton(
            btn_frame, text="Abrir pasta", width=100,
            fg_color="transparent", hover_color=COL_BORDER, text_color="#e8e8e8",
            border_width=1, border_color=COL_BORDER,
            font=ctk.CTkFont(size=13),
            command=self.on_open_folder,
        )
        folder_btn.pack(side="left")


# ----------------------------------------------------------------------
# Widget: linha de pack de resource packs local (.yzkrp)
# ----------------------------------------------------------------------

class RPackRow(ctk.CTkFrame):
    def __init__(self, master, pack_path: Path, data: dict, on_install, on_open_folder, **kwargs):
        super().__init__(master, fg_color=COL_PANEL_2, corner_radius=10, **kwargs)
        self.pack_path = pack_path
        self.data = data
        self.on_install = on_install
        self.on_open_folder = on_open_folder

        self.grid_columnconfigure(1, weight=1)

        name = data.get("name", pack_path.stem)
        mc_version = data.get("mc_version", "?")
        n_packs = len(data.get("resourcepacks", []))

        name_lbl = ctk.CTkLabel(
            self, text=name, font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        )
        name_lbl.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 0))

        meta = f"MC {mc_version}  ·  {n_packs} resource pack(s)  ·  {pack_path.name}"
        meta_lbl = ctk.CTkLabel(
            self, text=meta, font=ctk.CTkFont(size=11), text_color=COL_TEXT_DIM, anchor="w"
        )
        meta_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 10))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=2, rowspan=2, padx=14, pady=10, sticky="e")

        install_btn = ctk.CTkButton(
            btn_frame, text="Reinstalar", width=100,
            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER, text_color="#0b0d0e",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self.on_install(self.pack_path, self.data),
        )
        install_btn.pack(side="left", padx=(0, 6))

        folder_btn = ctk.CTkButton(
            btn_frame, text="Abrir pasta", width=100,
            fg_color="transparent", hover_color=COL_BORDER, text_color="#e8e8e8",
            border_width=1, border_color=COL_BORDER,
            font=ctk.CTkFont(size=13),
            command=self.on_open_folder,
        )
        folder_btn.pack(side="left")


# ----------------------------------------------------------------------
# App principal
# ----------------------------------------------------------------------

class YzkModLoaderApp(ctk.CTk):
    PROJECT_TYPES = {
        "Mods": "mod",
        "Resource Packs": "resourcepack",
        "Plugins": "plugin",
        "Modpacks": "modpack",
    }

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x680")
        self.minsize(860, 560)
        self.configure(fg_color=COL_BG)

        self.cfg = load_config()
        self.client = ModrinthClient(self.cfg.get("api_key", ""))
        self.task_queue = queue.Queue()

        self.mods_folder = self.cfg.get("mods_folder", "")
        self.rp_folder = self.cfg.get("rp_folder", "")
        self.server_cfg = self.cfg.get("server", {})

        self.current_type_key = "Mods"
        self.current_hits = []
        self.selected_hits = {}  # project_id/slug -> hit dict, usado no modo de selecao multipla
        self._loaded_tabs = set()  # abas que ja fizeram autoload de populares

        # Sessao de mods/resourcepacks baixados nesta sessao (usado para exportar)
        self.session_mods = []  # lista de {"project_id":..., "title":..., "filename":...}
        self.session_rpacks = []  # idem, mas para resource packs

        self._build_layout()
        self._poll_queue()

        # Define o icone da janela, se um icon.ico estiver presente
        if ICON_PATH.exists():
            try:
                self.iconbitmap(str(ICON_PATH))
            except Exception:
                pass

        # Se foi relancado so pra registrar as extensoes como admin (via UAC),
        # faz o registro, avisa e fecha — nao abre a janela principal de verdade.
        if "--register-extensions" in sys.argv[1:]:
            ok = register_extensions_as_admin()
            if ok:
                messagebox.showinfo(APP_NAME, f"Arquivos {YZK_EXTENSION} e {YZKRP_EXTENSION} agora abrem no {APP_NAME} para todos os usuários deste PC.")
            else:
                messagebox.showerror(APP_NAME, "Não foi possível registrar as extensões. Tente novamente ou registre manualmente.")
            self.after(10, self.destroy)
            return

        # Registra as extensoes .yzk/.yzkrp (pede admin via UAC) se ainda nao estiverem
        if WINREG_OK and not (is_yzk_registered() and is_yzkrp_registered()):
            self.after(200, self._auto_register_extensions)

        # Se o app foi aberto clicando em um arquivo .yzk/.yzkrp, importa direto
        pack_arg, arg_kind = self._get_pack_arg()
        if pack_arg:
            if arg_kind == "modpack":
                self.after(600, lambda: self._import_modpack_file(pack_arg))
            else:
                self.after(600, lambda: self._import_rpack_file(pack_arg))
        # Se ainda nao configurou pastas, avisa e abre a aba de config
        elif not self.mods_folder or not self.rp_folder:
            self.after(400, self._prompt_initial_setup)

    def _get_pack_arg(self):
        for arg in sys.argv[1:]:
            low = arg.lower()
            if low.endswith(YZKRP_EXTENSION):
                p = Path(arg)
                if p.exists():
                    return p, "rpack"
            elif low.endswith(YZK_EXTENSION):
                p = Path(arg)
                if p.exists():
                    return p, "modpack"
        return None, None

    def _auto_register_extensions(self):
        """
        Pede elevacao de administrador (UAC) para registrar .yzk/.yzkrp para
        todos os usuarios do Windows. Se o usuario cancelar o prompt do UAC,
        o app segue funcionando normalmente, só sem a associação automática.
        """
        self.status_bar.configure(text="Solicitando permissão de administrador para associar arquivos .yzk/.yzkrp...")
        register_extensions_as_admin()
        # o registro de fato roda no processo elevado (se o usuario aceitar o UAC);
        # aqui so seguimos usando o app normalmente.

    # ------------------------------------------------------------------
    # Layout geral: sidebar + area de conteudo
    # ------------------------------------------------------------------

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        sidebar = ctk.CTkFrame(self, fg_color=COL_PANEL, width=220, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nswe")
        sidebar.grid_propagate(False)

        logo = ctk.CTkLabel(
            sidebar,
            text="yzkModLoader",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COL_ACCENT,
        )
        logo.pack(pady=(24, 4), padx=20, anchor="w")

        sub = ctk.CTkLabel(
            sidebar, text="Modrinth downloader", font=ctk.CTkFont(size=12), text_color=COL_TEXT_DIM
        )
        sub.pack(pady=(0, 24), padx=20, anchor="w")

        self.nav_buttons = {}
        for label in ["Mods", "Resource Packs", "Plugins", "Modpacks", "Meus Modpacks", "Meus Resource Packs"]:
            b = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                fg_color="transparent",
                hover_color=COL_PANEL_2,
                text_color="#e8e8e8",
                font=ctk.CTkFont(size=14),
                height=40,
                corner_radius=8,
                command=lambda l=label: self._switch_type(l),
            )
            b.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[label] = b

        sep = ctk.CTkFrame(sidebar, height=1, fg_color=COL_BORDER)
        sep.pack(fill="x", padx=16, pady=16)

        cfg_btn = ctk.CTkButton(
            sidebar,
            text="⚙  Configurações",
            anchor="w",
            fg_color="transparent",
            hover_color=COL_PANEL_2,
            text_color="#e8e8e8",
            font=ctk.CTkFont(size=14),
            height=40,
            corner_radius=8,
            command=self._open_settings,
        )
        cfg_btn.pack(fill="x", padx=12, side="bottom", pady=(0, 20))

        self._highlight_nav("Mods")

        # Area de conteudo
        content = ctk.CTkFrame(self, fg_color=COL_BG, corner_radius=0)
        content.grid(row=0, column=1, sticky="nswe")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(3, weight=1)

        # Barra de busca + filtros
        self.top_bar = ctk.CTkFrame(content, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        self.top_bar.grid_columnconfigure(0, weight=1)
        top_bar = self.top_bar

        self.search_entry = ctk.CTkEntry(
            top_bar,
            placeholder_text="Buscar mods no Modrinth...",
            height=42,
            corner_radius=10,
            font=ctk.CTkFont(size=14),
            fg_color=COL_PANEL_2,
            border_color=COL_BORDER,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self._do_search())

        search_btn = ctk.CTkButton(
            top_bar,
            text="Buscar",
            width=110,
            height=42,
            corner_radius=10,
            fg_color=COL_ACCENT,
            hover_color=COL_ACCENT_HOVER,
            text_color="#0b0d0e",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._do_search,
        )
        search_btn.grid(row=0, column=1)

        # Filtros: versao do MC + destino (local ou servidor, so aparece p/ plugins)
        self.filt_bar = ctk.CTkFrame(content, fg_color="transparent")
        self.filt_bar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        filt_bar = self.filt_bar

        ctk.CTkLabel(filt_bar, text="Versão do Minecraft:", text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=12)).pack(side="left")
        self.version_entry = ctk.CTkComboBox(
            filt_bar, values=["Qualquer"], width=130, height=30,
            fg_color=COL_PANEL_2, border_color=COL_BORDER, button_color=COL_PANEL_2,
            button_hover_color=COL_BORDER, dropdown_fg_color=COL_PANEL_2,
            command=lambda _=None: self._on_version_changed(),
        )
        self.version_entry.pack(side="left", padx=(8, 20))
        # Combobox do customtkinter permite digitar tambem, entao filtramos as
        # opcoes exibidas conforme a pessoa digita, pra sempre bater com uma
        # versao real (evita erro de digitacao tipo "1.2O.1").
        self.version_entry.bind("<KeyRelease>", self._filter_version_options)
        last_version = self.cfg.get("last_version", "")
        self.version_entry.set(last_version if last_version else "Qualquer")
        self._all_versions = ["Qualquer"]
        self._load_game_versions()

        ctk.CTkLabel(filt_bar, text="Loader:", text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=12)).pack(side="left")
        self.loader_var = ctk.StringVar(value="Fabric")
        self.loader_menu = ctk.CTkOptionMenu(
            filt_bar, values=MOD_LOADERS, variable=self.loader_var, width=120, height=30,
            fg_color=COL_PANEL_2, button_color=COL_PANEL_2, button_hover_color=COL_BORDER,
            dropdown_fg_color=COL_PANEL_2, command=lambda _=None: self._on_loader_changed(),
        )
        self.loader_menu.pack(side="left", padx=(8, 20))

        self.bulk_var = ctk.BooleanVar(value=False)
        self.bulk_check = ctk.CTkCheckBox(
            filt_bar, text="Selecionar vários", variable=self.bulk_var,
            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER, border_color=COL_BORDER,
            command=self._toggle_bulk_mode,
        )
        self.bulk_check.pack(side="left", padx=(0, 20))

        self.bulk_download_btn = ctk.CTkButton(
            filt_bar, text="Baixar selecionados (0)", height=30, width=170,
            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER, text_color="#0b0d0e",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._download_selected,
        )
        # so aparece quando bulk_mode esta ativo e ha selecoes; empacotado sob demanda

        self.dest_var = ctk.StringVar(value="local")
        self.dest_local_rb = ctk.CTkRadioButton(
            filt_bar, text="Salvar localmente", variable=self.dest_var, value="local",
            fg_color=COL_ACCENT, border_color=COL_BORDER,
        )
        self.dest_server_rb = ctk.CTkRadioButton(
            filt_bar, text="Enviar para servidor Purpur", variable=self.dest_var, value="server",
            fg_color=COL_ACCENT, border_color=COL_BORDER,
        )
        # so mostrados na aba Plugins, montados sob demanda em _switch_type

        # Status / caminho atual
        self.path_label = ctk.CTkLabel(
            content, text="", font=ctk.CTkFont(size=12), text_color=COL_TEXT_DIM, anchor="w"
        )
        self.path_label.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 8))

        # Lista de resultados (scrollable)
        self.results_frame = ctk.CTkScrollableFrame(
            content, fg_color="transparent"
        )
        self.results_frame.grid(row=3, column=0, sticky="nswe", padx=24, pady=(0, 10))
        self.results_frame.grid_columnconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self.results_frame,
            text="Busque algo para ver resultados aqui.",
            text_color=COL_TEXT_DIM,
            font=ctk.CTkFont(size=13),
        )
        self.empty_label.grid(row=0, column=0, pady=40)

        # Barra de status inferior
        self.status_bar = ctk.CTkLabel(
            content, text="Pronto.", font=ctk.CTkFont(size=12), text_color=COL_TEXT_DIM, anchor="w"
        )
        self.status_bar.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 14))

        self.progress = ctk.CTkProgressBar(content, height=6, progress_color=COL_ACCENT)
        self.progress.set(0)
        self.progress.grid(row=5, column=0, sticky="ew", padx=24, pady=(0, 20))

        self._update_path_label()

        # Inicializa tudo consistente com a aba padrao (Mods): destaque no menu
        # lateral, loader visivel, e autoload dos mods mais populares.
        self._switch_type("Mods")

    def _highlight_nav(self, label):
        for k, b in self.nav_buttons.items():
            b.configure(fg_color=(COL_PANEL_2 if k == label else "transparent"))

    # ------------------------------------------------------------------
    # Versao do Minecraft (combobox pesquisavel, evita erro de digitacao)
    # ------------------------------------------------------------------

    def _load_game_versions(self):
        def worker():
            try:
                versions = self.client.get_game_versions(releases_only=True)
                self.task_queue.put(("versions_loaded", versions))
            except Exception:
                pass  # sem internet ainda no boot, tudo bem: combobox so fica com "Qualquer"
        threading.Thread(target=worker, daemon=True).start()

    def _on_versions_loaded(self, versions):
        self._all_versions = ["Qualquer"] + versions
        current = self.version_entry.get()
        self.version_entry.configure(values=self._all_versions)
        # mantem o que a pessoa ja tinha digitado/selecionado
        self.version_entry.set(current if current else "Qualquer")

    def _filter_version_options(self, event=None):
        typed = self.version_entry.get().strip()
        if not typed or typed == "Qualquer":
            self.version_entry.configure(values=self._all_versions)
            return
        matches = [v for v in self._all_versions if typed in v]
        self.version_entry.configure(values=matches or self._all_versions)

    def _on_version_changed(self):
        if self.search_entry.get().strip():
            self._do_search()
        elif self.current_type_key in self._loaded_tabs:
            self._load_popular(self.current_type_key)

    def _on_loader_changed(self):
        # Se ja tem uma busca digitada, refaz a busca com o novo loader;
        # senao, recarrega os populares filtrados pelo novo loader.
        if self.search_entry.get().strip():
            self._do_search()
        else:
            self._load_popular(self.current_type_key)

    def _get_version_filter(self) -> str:
        v = self.version_entry.get().strip()
        return "" if (not v or v == "Qualquer") else v

    def _get_loader_filter(self) -> str:
        """So aplica filtro de loader na aba Mods. 'Qualquer' = sem filtro."""
        if self.current_type_key != "Mods":
            return ""
        loader = self.loader_var.get()
        return "" if loader == "Qualquer" else loader.lower()

    # ------------------------------------------------------------------
    # Selecao multipla (bulk download)
    # ------------------------------------------------------------------

    def _toggle_bulk_mode(self):
        self.selected_hits = {}
        self._update_bulk_button()
        self._render_results(self.current_hits)

    def _hit_key(self, hit):
        return hit.get("project_id") or hit.get("slug")

    def _on_toggle_select(self, hit, is_selected):
        key = self._hit_key(hit)
        if is_selected:
            self.selected_hits[key] = hit
        else:
            self.selected_hits.pop(key, None)
        self._update_bulk_button()

    def _update_bulk_button(self):
        n = len(self.selected_hits)
        self.bulk_download_btn.configure(text=f"Baixar selecionados ({n})")
        if self.bulk_var.get() and n > 0:
            self.bulk_download_btn.pack(side="left")
        else:
            self.bulk_download_btn.pack_forget()

    def _download_selected(self):
        if not self.selected_hits:
            return
        hits = list(self.selected_hits.values())
        self.status_bar.configure(text=f"Baixando {len(hits)} item(ns) selecionado(s)...")
        for hit in hits:
            self._start_download(hit)
        self.selected_hits = {}
        self._update_bulk_button()
        self._render_results(self.current_hits)

    # ------------------------------------------------------------------
    # Navegacao entre tipos
    # ------------------------------------------------------------------

    def _switch_type(self, label):
        self.current_type_key = label
        self._highlight_nav(label)
        self._clear_results()
        self._update_path_label()

        if label == "Plugins":
            self.dest_local_rb.pack(side="left", padx=(20, 6))
            self.dest_server_rb.pack(side="left", padx=6)
        else:
            self.dest_local_rb.pack_forget()
            self.dest_server_rb.pack_forget()

        if label == "Mods":
            self.loader_menu.pack(side="left", padx=(8, 20))
        else:
            self.loader_menu.pack_forget()

        # Reseta selecao multipla ao trocar de aba
        self.bulk_var.set(False)
        self.selected_hits = {}
        self.bulk_download_btn.pack_forget()

        if label == "Meus Modpacks":
            # Esconde a barra de busca e filtros, mostra a tela de modpacks locais
            self.top_bar.grid_remove()
            self.filt_bar.grid_remove()
            self._render_my_modpacks()
        elif label == "Meus Resource Packs":
            self.top_bar.grid_remove()
            self.filt_bar.grid_remove()
            self._render_my_rpacks()
        else:
            self.top_bar.grid()
            self.filt_bar.grid()
            self.search_entry.configure(placeholder_text=f"Buscar {label.lower()} no Modrinth...")
            # Carrega automaticamente os itens mais populares deste tipo na
            # primeira vez que a aba e aberta, pra ja aparecer conteudo relevante.
            if label not in self._loaded_tabs and label != "Modpacks":
                self._loaded_tabs.add(label)
                self._load_popular(label)

    def _update_path_label(self):
        label = self.current_type_key
        if label == "Mods":
            path = self.mods_folder or "(nenhuma pasta escolhida — vá em Configurações)"
        elif label == "Resource Packs":
            path = self.rp_folder or "(nenhuma pasta escolhida — vá em Configurações)"
        elif label == "Modpacks":
            path = self.mods_folder or "(nenhuma pasta escolhida — vá em Configurações)"
        elif label == "Meus Modpacks":
            path = str(MODPACKS_DIR)
        elif label == "Meus Resource Packs":
            path = str(RPACKS_DIR)
        else:
            local_part = self.mods_folder or "(pasta local não definida)"
            srv = self.server_cfg.get("host", "")
            server_part = f"servidor: {srv}" if srv else "(servidor não configurado)"
            path = f"Local: {local_part}   |   {server_part}"
        self.path_label.configure(text=f"Destino atual: {path}")

    def _clear_results(self):
        for w in self.results_frame.winfo_children():
            w.destroy()
        self.current_hits = []

    # ------------------------------------------------------------------
    # Busca
    # ------------------------------------------------------------------

    def _do_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        project_type = self.PROJECT_TYPES[self.current_type_key]
        loader = self._get_loader_filter()

        self.status_bar.configure(text=f"Buscando '{query}'...")
        self._clear_results()

        def worker():
            try:
                hits = self.client.search(query, project_type, loader=loader, limit=25)
                self.task_queue.put(("search_done", hits))
            except Exception as e:
                self.task_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _load_popular(self, label):
        """Carrega automaticamente os itens mais baixados desta aba, pra ja
        aparecer conteudo relevante assim que a pessoa entra nela."""
        project_type = self.PROJECT_TYPES.get(label)
        if not project_type:
            return
        loader = self._get_loader_filter()
        self.status_bar.configure(text=f"Carregando {label.lower()} mais populares...")

        def worker():
            try:
                hits = self.client.search("", project_type, loader=loader, limit=20, index="downloads")
                self.task_queue.put(("search_done", hits))
            except Exception as e:
                self.task_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _render_results(self, hits):
        self._clear_results()
        self.current_hits = hits
        if not hits:
            lbl = ctk.CTkLabel(
                self.results_frame, text="Nenhum resultado encontrado.",
                text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=13)
            )
            lbl.grid(row=0, column=0, pady=40)
            return

        is_modpack_tab = self.current_type_key == "Modpacks"
        handler = self._start_modpack_install if is_modpack_tab else self._start_download
        btn_text = "Instalar" if is_modpack_tab else "Baixar"
        bulk_mode = self.bulk_var.get() and not is_modpack_tab

        for i, hit in enumerate(hits):
            selected = self._hit_key(hit) in self.selected_hits
            row = ResultRow(
                self.results_frame, hit, on_download=handler, button_text=btn_text,
                bulk_mode=bulk_mode, on_toggle_select=self._on_toggle_select, selected=selected,
            )
            row.grid(row=i, column=0, sticky="ew", pady=6)
        self.status_bar.configure(text=f"{len(hits)} resultado(s) encontrado(s).")

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _start_download(self, hit):
        project_id = hit.get("project_id") or hit.get("slug")
        title = hit.get("title", project_id)
        version_filter = self._get_version_filter()
        project_type = self.PROJECT_TYPES[self.current_type_key]
        loader = self._get_loader_filter()

        # Validacao de destino
        if self.current_type_key == "Mods" and not self.mods_folder:
            messagebox.showwarning(APP_NAME, "Escolha a pasta de mods em Configurações antes de baixar.")
            return
        if self.current_type_key == "Resource Packs" and not self.rp_folder:
            messagebox.showwarning(APP_NAME, "Escolha a pasta de resource packs em Configurações antes de baixar.")
            return
        if self.current_type_key == "Plugins" and self.dest_var.get() == "server":
            if not self.server_cfg.get("host"):
                messagebox.showwarning(APP_NAME, "Configure os dados do servidor Purpur em Configurações antes de enviar.")
                return
        elif self.current_type_key == "Plugins" and not self.mods_folder:
            # plugins salvos localmente vao para a mesma pasta base escolhida (mods_folder serve de referencia)
            messagebox.showwarning(APP_NAME, "Escolha uma pasta local em Configurações antes de baixar.")
            return

        self.status_bar.configure(text=f"Buscando versões de '{title}'...")
        self.progress.set(0)

        def worker():
            try:
                versions = self.client.get_versions(project_id, loader=loader, game_version=version_filter)
                if not versions:
                    # tenta sem filtro de loader (resourcepacks e plugins nao usam fabric)
                    versions = self.client.get_versions(project_id, loader="", game_version=version_filter)
                if not versions:
                    self.task_queue.put(("error", f"Nenhuma versão compatível encontrada para {title}."))
                    return

                latest = versions[0]
                files = latest.get("files", [])
                primary = next((f for f in files if f.get("primary")), files[0] if files else None)
                if not primary:
                    self.task_queue.put(("error", f"Nenhum arquivo disponível para {title}."))
                    return

                file_url = primary["url"]
                file_name = primary["filename"]

                if self.current_type_key == "Mods":
                    dest = Path(self.mods_folder) / file_name
                    self._download_local(file_url, dest, title)
                    self._track_session_mod(project_id, title, file_name)
                elif self.current_type_key == "Resource Packs":
                    dest = Path(self.rp_folder) / file_name
                    self._download_local(file_url, dest, title)
                    self._track_session_rpack(project_id, title, file_name)
                else:  # Plugins
                    if self.dest_var.get() == "server":
                        self._download_and_upload_sftp(file_url, file_name, title)
                    else:
                        dest = Path(self.mods_folder) / file_name
                        self._download_local(file_url, dest, title)

            except Exception as e:
                self.task_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _download_local(self, url, dest_path, title):
        def progress_cb(frac):
            self.task_queue.put(("progress", frac))
        self.client.download_file(url, dest_path, progress_cb=progress_cb)
        self.task_queue.put(("done", f"'{title}' salvo em {dest_path}"))

    def _download_and_upload_sftp(self, url, file_name, title):
        if not PARAMIKO_OK:
            self.task_queue.put(("error", "paramiko não está instalado. Rode: pip install paramiko"))
            return

        tmp_dir = Path.home() / ".yzkmodloader_tmp"
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / file_name

        def progress_cb(frac):
            self.task_queue.put(("progress", frac * 0.5))  # metade da barra = download

        self.client.download_file(url, tmp_path, progress_cb=progress_cb)

        host = self.server_cfg.get("host")
        port = int(self.server_cfg.get("port", 22))
        user = self.server_cfg.get("user")
        password = self.server_cfg.get("password", "")
        key_path = self.server_cfg.get("key_path", "")
        remote_dir = self.server_cfg.get("plugins_path", "/plugins")

        transport = paramiko.Transport((host, port))
        try:
            if key_path:
                pkey = paramiko.RSAKey.from_private_key_file(key_path)
                transport.connect(username=user, pkey=pkey)
            else:
                transport.connect(username=user, password=password)

            sftp = paramiko.SFTPClient.from_transport(transport)
            remote_path = remote_dir.rstrip("/") + "/" + file_name

            filesize = tmp_path.stat().st_size

            def sftp_progress(sent, total):
                frac = 0.5 + (sent / total) * 0.5 if total else 0.5
                self.task_queue.put(("progress", frac))

            sftp.put(str(tmp_path), remote_path, callback=sftp_progress)
            sftp.close()
        finally:
            transport.close()
            try:
                tmp_path.unlink()
            except Exception:
                pass

        self.task_queue.put(("done", f"'{title}' enviado para o servidor em {remote_dir}"))

    def _track_session_mod(self, project_id, title, filename=""):
        if not any(m.get("project_id") == project_id and project_id for m in self.session_mods) and \
           not any(m.get("filename") == filename and filename for m in self.session_mods):
            self.session_mods.append({"project_id": project_id, "title": title, "filename": filename})

    def _track_session_rpack(self, project_id, title, filename=""):
        if not any(m.get("project_id") == project_id and project_id for m in self.session_rpacks) and \
           not any(m.get("filename") == filename and filename for m in self.session_rpacks):
            self.session_rpacks.append({"project_id": project_id, "title": title, "filename": filename})

    def _get_exportable_mods(self) -> list:
        """
        Junta os mods baixados nesta sessao com os que ja existem na pasta de
        mods configurada (de sessoes/instancias anteriores), sem duplicar por
        nome de arquivo.
        """
        combined = list(self.session_mods)
        seen_files = {m.get("filename") for m in combined if m.get("filename")}
        for item in scan_folder_items(self.mods_folder, MOD_FILE_EXTENSIONS):
            if item["filename"] not in seen_files:
                combined.append(item)
                seen_files.add(item["filename"])
        return combined

    def _get_exportable_rpacks(self) -> list:
        """Igual a _get_exportable_mods, mas para a pasta de resource packs."""
        combined = list(self.session_rpacks)
        seen_files = {m.get("filename") for m in combined if m.get("filename")}
        for item in scan_folder_items(self.rp_folder, RESOURCEPACK_FILE_EXTENSIONS):
            if item["filename"] not in seen_files:
                combined.append(item)
                seen_files.add(item["filename"])
        return combined

    # ------------------------------------------------------------------
    # Modpacks — instalar um modpack do Modrinth (aba "Modpacks")
    # ------------------------------------------------------------------

    def _start_modpack_install(self, hit):
        """
        Modpacks no Modrinth sao publicados como arquivo .mrpack (um zip com
        um manifesto listando os mods). Aqui baixamos o .mrpack, lemos o
        manifesto e baixamos cada mod individualmente para a pasta de mods.
        """
        if not self.mods_folder:
            messagebox.showwarning(APP_NAME, "Escolha a pasta de mods em Configurações antes de instalar.")
            return

        project_id = hit.get("project_id") or hit.get("slug")
        title = hit.get("title", project_id)
        version_filter = self._get_version_filter()

        self.status_bar.configure(text=f"Preparando modpack '{title}'...")
        self.progress.set(0)

        def worker():
            try:
                versions = self.client.get_versions(project_id, game_version=version_filter)
                if not versions:
                    versions = self.client.get_versions(project_id)
                if not versions:
                    self.task_queue.put(("error", f"Nenhuma versão encontrada para o modpack {title}."))
                    return

                latest = versions[0]
                files = latest.get("files", [])
                primary = next((f for f in files if f.get("primary")), files[0] if files else None)
                if not primary:
                    self.task_queue.put(("error", f"Nenhum arquivo disponível para {title}."))
                    return

                import zipfile, tempfile

                tmp_dir = Path(tempfile.gettempdir()) / "yzkmodloader_mrpack"
                tmp_dir.mkdir(exist_ok=True)
                mrpack_path = tmp_dir / primary["filename"]

                def dl_progress(frac):
                    self.task_queue.put(("progress", frac * 0.2))

                self.client.download_file(primary["url"], mrpack_path, progress_cb=dl_progress)

                with zipfile.ZipFile(mrpack_path, "r") as zf:
                    with zf.open("modrinth.index.json") as f:
                        manifest = json.load(f)

                mc_version = manifest.get("dependencies", {}).get("minecraft", "")
                deps = manifest.get("dependencies", {})
                if "fabric-loader" in deps:
                    loader = "fabric"
                elif "neoforge" in deps:
                    loader = "neoforge"
                elif "forge" in deps:
                    loader = "forge"
                elif "quilt-loader" in deps:
                    loader = "quilt"
                else:
                    loader = ""
                pack_files = manifest.get("files", [])
                total = len(pack_files) or 1

                exported_mods = []
                for i, pf in enumerate(pack_files):
                    downloads = pf.get("downloads", [])
                    if not downloads:
                        continue
                    file_url = downloads[0]
                    rel_path = pf.get("path", "")
                    file_name = Path(rel_path).name
                    # so instalamos o que for de fato pra pasta de mods
                    if "mods/" in rel_path or rel_path.startswith("mods"):
                        dest = Path(self.mods_folder) / file_name
                    elif "resourcepacks/" in rel_path and self.rp_folder:
                        dest = Path(self.rp_folder) / file_name
                    else:
                        dest = Path(self.mods_folder) / file_name

                    self.client.download_file(file_url, dest)
                    exported_mods.append({"project_id": "", "title": file_name})
                    self.task_queue.put(("progress", 0.2 + 0.8 * ((i + 1) / total)))

                # Salva automaticamente uma copia do pack em Meus Modpacks
                data = build_yzk_data(title, mc_version, loader, exported_mods)
                safe_name = "".join(c for c in title if c.isalnum() or c in " _-").strip() or "modpack"
                save_yzk_file(data, MODPACKS_DIR / f"{safe_name}{YZK_EXTENSION}")

                try:
                    mrpack_path.unlink()
                except Exception:
                    pass

                self.task_queue.put(("done", f"Modpack '{title}' instalado ({len(exported_mods)} arquivos) em {self.mods_folder}"))

            except KeyError:
                self.task_queue.put(("error", f"'{title}' não é um modpack (.mrpack) válido do Modrinth."))
            except Exception as e:
                self.task_queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Meus Modpacks — exportar sessao atual / listar / importar .yzk
    # ------------------------------------------------------------------

    def _render_my_modpacks(self):
        self._clear_results()

        # Cabecalho com botao de exportar a sessao atual
        header_row = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header_row.grid_columnconfigure(0, weight=1)

        exportable = self._get_exportable_mods()
        info = ctk.CTkLabel(
            header_row,
            text=f"{len(exportable)} mod(s) disponível(is) para exportar "
                 f"({len(self.session_mods)} desta sessão + os já existentes na pasta de mods).",
            text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=12), wraplength=560, justify="left",
        )
        info.grid(row=0, column=0, sticky="w")

        export_btn = ctk.CTkButton(
            header_row, text="Exportar como .yzk", height=36,
            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER, text_color="#0b0d0e",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._export_session_as_yzk,
        )
        export_btn.grid(row=0, column=1, sticky="e")

        import_btn = ctk.CTkButton(
            header_row, text="Importar .yzk de outra pessoa", height=36,
            fg_color=COL_PANEL_2, hover_color=COL_BORDER, text_color="#e8e8e8",
            font=ctk.CTkFont(size=13),
            command=self._import_modpack_dialog,
        )
        import_btn.grid(row=0, column=2, sticky="e", padx=(8, 0))

        sep = ctk.CTkFrame(self.results_frame, height=1, fg_color=COL_BORDER)
        sep.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        packs = list_my_modpacks()
        if not packs:
            lbl = ctk.CTkLabel(
                self.results_frame,
                text="Nenhum modpack criado ainda. Baixe mods na aba Mods (ou já tenha mods na "
                     "pasta configurada) e exporte aqui, ou instale um modpack do Modrinth.",
                text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=13), wraplength=600, justify="left",
            )
            lbl.grid(row=2, column=0, pady=20, sticky="w")
            return

        for i, pack_path in enumerate(packs):
            try:
                data = load_yzk_file(pack_path)
            except Exception:
                continue
            row = ModpackRow(
                self.results_frame, pack_path, data,
                on_install=self._install_local_yzk,
                on_open_folder=self._open_modpacks_folder,
            )
            row.grid(row=2 + i, column=0, sticky="ew", pady=6)

    def _export_session_as_yzk(self):
        exportable = self._get_exportable_mods()
        if not exportable:
            messagebox.showinfo(
                APP_NAME,
                "Nenhum mod encontrado para exportar. Baixe mods na aba Mods, ou confira se a "
                "pasta de mods configurada em Configurações está correta e já tem arquivos .jar."
            )
            return

        from tkinter import simpledialog
        name = simpledialog.askstring(APP_NAME, "Nome do modpack:", initialvalue="Meu Modpack")
        if not name:
            return

        mc_version = self._get_version_filter() or "desconhecida"
        loader = self.loader_var.get()
        loader = loader.lower() if loader != "Qualquer" else "fabric"
        data = build_yzk_data(name, mc_version, loader, exportable)
        safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip() or "modpack"
        dest = MODPACKS_DIR / f"{safe_name}{YZK_EXTENSION}"

        try:
            save_yzk_file(data, dest)
            messagebox.showinfo(
                APP_NAME,
                f"Modpack salvo em:\n{dest}\n\n{len(exportable)} mod(s) incluído(s).\n\n"
                "Envie esse arquivo .yzk para quem quiser instalar o mesmo pack."
            )
            self._render_my_modpacks()
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def _open_modpacks_folder(self):
        MODPACKS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(MODPACKS_DIR))  # Windows
        except AttributeError:
            import subprocess
            subprocess.Popen(["xdg-open", str(MODPACKS_DIR)])

    def _import_modpack_dialog(self):
        path = filedialog.askopenfilename(
            title="Escolha um arquivo .yzk", filetypes=[("Modpack yzkModLoader", f"*{YZK_EXTENSION}")]
        )
        if path:
            self._import_modpack_file(Path(path))

    def _import_modpack_file(self, path: Path):
        try:
            data = load_yzk_file(path)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Não foi possível ler o arquivo .yzk:\n{e}")
            return

        # Garante que a janela principal esteja visivel e na aba certa
        self._switch_type("Meus Modpacks")

        name = data.get("name", path.stem)
        mods = data.get("mods", [])
        confirm = messagebox.askyesno(
            APP_NAME,
            f"Instalar o modpack '{name}'?\n\n{len(mods)} mod(s) serão baixados para:\n"
            f"{self.mods_folder or '(nenhuma pasta configurada — configure antes de continuar)'}"
        )
        if not confirm:
            return
        self._install_local_yzk(path, data)

    def _install_local_yzk(self, path: Path, data: dict = None):
        if not self.mods_folder:
            messagebox.showwarning(APP_NAME, "Escolha a pasta de mods em Configurações antes de instalar.")
            return

        if data is None:
            try:
                data = load_yzk_file(path)
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))
                return

        mods = data.get("mods", [])
        loader = data.get("loader", "fabric")
        mc_version = data.get("mc_version", "")
        name = data.get("name", path.stem)

        # so instalamos entradas que tem project_id valido (modpacks exportados via .mrpack
        # podem ter entradas so com o nome do arquivo, essas sao ignoradas aqui)
        installable = [m for m in mods if m.get("project_id")]
        unidentified = [m for m in mods if not m.get("project_id")]

        if unidentified:
            names = ", ".join(m.get("filename") or m.get("title", "?") for m in unidentified[:8])
            more = "..." if len(unidentified) > 8 else ""
            messagebox.showwarning(
                APP_NAME,
                f"{len(unidentified)} item(ns) deste modpack foram detectados só pelo nome do "
                f"arquivo (sem ID do Modrinth), então não podem ser rebaixados automaticamente:\n\n"
                f"{names}{more}\n\nVocê precisará copiar esses arquivos manualmente para quem for "
                f"instalar o pack."
            )

        if not installable:
            if not unidentified:
                messagebox.showinfo(APP_NAME, f"'{name}' não tem mods com ID reconhecível para reinstalar automaticamente.")
            return

        self.status_bar.configure(text=f"Instalando modpack '{name}'...")
        self.progress.set(0)

        def worker():
            total = len(installable)
            errors = []
            for i, m in enumerate(installable):
                try:
                    versions = self.client.get_versions(m["project_id"], loader=loader, game_version=mc_version)
                    if not versions:
                        versions = self.client.get_versions(m["project_id"], game_version=mc_version)
                    if not versions:
                        errors.append(m.get("title", m["project_id"]))
                        continue
                    latest = versions[0]
                    files = latest.get("files", [])
                    primary = next((f for f in files if f.get("primary")), files[0] if files else None)
                    if not primary:
                        errors.append(m.get("title", m["project_id"]))
                        continue
                    dest = Path(self.mods_folder) / primary["filename"]
                    self.client.download_file(primary["url"], dest)
                except Exception:
                    errors.append(m.get("title", m["project_id"]))
                self.task_queue.put(("progress", (i + 1) / total))

            if errors:
                self.task_queue.put((
                    "done",
                    f"Modpack '{name}' instalado com {total - len(errors)}/{total} mods "
                    f"(falharam: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''})"
                ))
            else:
                self.task_queue.put(("done", f"Modpack '{name}' instalado com sucesso ({total} mods) em {self.mods_folder}"))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Fila de eventos (thread worker -> UI thread)
    # ------------------------------------------------------------------

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.task_queue.get_nowait()
                if kind == "search_done":
                    self._render_results(payload)
                elif kind == "versions_loaded":
                    self._on_versions_loaded(payload)
                elif kind == "progress":
                    self.progress.set(payload)
                elif kind == "done":
                    self.progress.set(1)
                    self.status_bar.configure(text=payload)
                    self.after(1200, lambda: self.progress.set(0))
                elif kind == "error":
                    self.status_bar.configure(text=f"Erro: {payload}")
                    messagebox.showerror(APP_NAME, payload)
                    self.progress.set(0)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    # ------------------------------------------------------------------
    # Meus Resource Packs — exportar sessao/pasta atual, listar, importar .yzkrp
    # ------------------------------------------------------------------

    def _render_my_rpacks(self):
        self._clear_results()

        header_row = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header_row.grid_columnconfigure(0, weight=1)

        exportable = self._get_exportable_rpacks()
        info = ctk.CTkLabel(
            header_row,
            text=f"{len(exportable)} resource pack(s) disponível(is) para exportar "
                 f"({len(self.session_rpacks)} desta sessão + os já existentes na pasta configurada).",
            text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=12), wraplength=560, justify="left",
        )
        info.grid(row=0, column=0, sticky="w")

        export_btn = ctk.CTkButton(
            header_row, text="Exportar como .yzkrp", height=36,
            fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER, text_color="#0b0d0e",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._export_session_as_yzkrp,
        )
        export_btn.grid(row=0, column=1, sticky="e")

        import_btn = ctk.CTkButton(
            header_row, text="Importar .yzkrp de outra pessoa", height=36,
            fg_color=COL_PANEL_2, hover_color=COL_BORDER, text_color="#e8e8e8",
            font=ctk.CTkFont(size=13),
            command=self._import_rpack_dialog,
        )
        import_btn.grid(row=0, column=2, sticky="e", padx=(8, 0))

        sep = ctk.CTkFrame(self.results_frame, height=1, fg_color=COL_BORDER)
        sep.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        packs = list_my_rpacks()
        if not packs:
            lbl = ctk.CTkLabel(
                self.results_frame,
                text="Nenhum pacote de resource packs criado ainda. Baixe resource packs na aba "
                     "Resource Packs (ou já tenha alguns na pasta configurada) e exporte aqui.",
                text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=13), wraplength=600, justify="left",
            )
            lbl.grid(row=2, column=0, pady=20, sticky="w")
            return

        for i, pack_path in enumerate(packs):
            try:
                data = load_yzkrp_file(pack_path)
            except Exception:
                continue
            row = RPackRow(
                self.results_frame, pack_path, data,
                on_install=self._install_local_yzkrp,
                on_open_folder=self._open_rpacks_folder,
            )
            row.grid(row=2 + i, column=0, sticky="ew", pady=6)

    def _export_session_as_yzkrp(self):
        exportable = self._get_exportable_rpacks()
        if not exportable:
            messagebox.showinfo(
                APP_NAME,
                "Nenhum resource pack encontrado para exportar. Baixe resource packs na aba "
                "Resource Packs, ou confira se a pasta configurada em Configurações está certa "
                "e já tem arquivos."
            )
            return

        from tkinter import simpledialog
        name = simpledialog.askstring(APP_NAME, "Nome do pacote de resource packs:", initialvalue="Meu Pacote de Resource Packs")
        if not name:
            return

        mc_version = self._get_version_filter() or "desconhecida"
        data = build_yzkrp_data(name, mc_version, exportable)
        safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip() or "resourcepacks"
        dest = RPACKS_DIR / f"{safe_name}{YZKRP_EXTENSION}"

        try:
            save_yzkrp_file(data, dest)
            messagebox.showinfo(
                APP_NAME,
                f"Pacote salvo em:\n{dest}\n\n{len(exportable)} resource pack(s) incluído(s).\n\n"
                "Envie esse arquivo .yzkrp para quem quiser instalar o mesmo pacote."
            )
            self._render_my_rpacks()
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def _open_rpacks_folder(self):
        RPACKS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(RPACKS_DIR))  # Windows
        except AttributeError:
            import subprocess
            subprocess.Popen(["xdg-open", str(RPACKS_DIR)])

    def _import_rpack_dialog(self):
        path = filedialog.askopenfilename(
            title="Escolha um arquivo .yzkrp", filetypes=[("Pacote de Resource Packs", f"*{YZKRP_EXTENSION}")]
        )
        if path:
            self._import_rpack_file(Path(path))

    def _import_rpack_file(self, path: Path):
        try:
            data = load_yzkrp_file(path)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Não foi possível ler o arquivo .yzkrp:\n{e}")
            return

        self._switch_type("Meus Resource Packs")

        name = data.get("name", path.stem)
        packs = data.get("resourcepacks", [])
        confirm = messagebox.askyesno(
            APP_NAME,
            f"Instalar o pacote de resource packs '{name}'?\n\n{len(packs)} item(ns) serão baixados para:\n"
            f"{self.rp_folder or '(nenhuma pasta configurada — configure antes de continuar)'}"
        )
        if not confirm:
            return
        self._install_local_yzkrp(path, data)

    def _install_local_yzkrp(self, path: Path, data: dict = None):
        if not self.rp_folder:
            messagebox.showwarning(APP_NAME, "Escolha a pasta de resource packs em Configurações antes de instalar.")
            return

        if data is None:
            try:
                data = load_yzkrp_file(path)
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))
                return

        packs = data.get("resourcepacks", [])
        mc_version = data.get("mc_version", "")
        name = data.get("name", path.stem)

        installable = [m for m in packs if m.get("project_id")]
        unidentified = [m for m in packs if not m.get("project_id")]

        if unidentified:
            names = ", ".join(m.get("filename") or m.get("title", "?") for m in unidentified[:8])
            more = "..." if len(unidentified) > 8 else ""
            messagebox.showwarning(
                APP_NAME,
                f"{len(unidentified)} item(ns) deste pacote foram detectados só pelo nome do "
                f"arquivo (sem ID do Modrinth), então não podem ser rebaixados automaticamente:\n\n"
                f"{names}{more}\n\nVocê precisará copiar esses arquivos manualmente para quem for "
                f"instalar o pacote."
            )

        if not installable:
            if not unidentified:
                messagebox.showinfo(APP_NAME, f"'{name}' não tem resource packs com ID reconhecível para reinstalar automaticamente.")
            return

        self.status_bar.configure(text=f"Instalando pacote '{name}'...")
        self.progress.set(0)

        def worker():
            total = len(installable)
            errors = []
            for i, m in enumerate(installable):
                try:
                    versions = self.client.get_versions(m["project_id"], game_version=mc_version)
                    if not versions:
                        versions = self.client.get_versions(m["project_id"])
                    if not versions:
                        errors.append(m.get("title", m["project_id"]))
                        continue
                    latest = versions[0]
                    files = latest.get("files", [])
                    primary = next((f for f in files if f.get("primary")), files[0] if files else None)
                    if not primary:
                        errors.append(m.get("title", m["project_id"]))
                        continue
                    dest = Path(self.rp_folder) / primary["filename"]
                    self.client.download_file(primary["url"], dest)
                except Exception:
                    errors.append(m.get("title", m["project_id"]))
                self.task_queue.put(("progress", (i + 1) / total))

            if errors:
                self.task_queue.put((
                    "done",
                    f"Pacote '{name}' instalado com {total - len(errors)}/{total} resource pack(s) "
                    f"(falharam: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''})"
                ))
            else:
                self.task_queue.put(("done", f"Pacote '{name}' instalado com sucesso ({total} resource pack(s)) em {self.rp_folder}"))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Configuracoes
    # ------------------------------------------------------------------

    def _prompt_initial_setup(self):
        messagebox.showinfo(
            APP_NAME,
            "Antes de começar, escolha a pasta de mods e a pasta de resource packs "
            "nas Configurações. O app sempre vai perguntar / usar essas pastas para salvar os arquivos."
        )
        self._open_settings()

    def _open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("Configurações — yzkModLoader")
        win.geometry("560x600")
        win.resizable(True, True)
        win.configure(fg_color=COL_BG)

        # Cabecalho fixo (nao rola) - empacotado primeiro, no topo
        header = ctk.CTkLabel(win, text="Configurações", font=ctk.CTkFont(size=20, weight="bold"))
        header.pack(side="top", anchor="w", padx=24, pady=(18, 6), fill="x")

        # Rodape fixo (nao rola) - empacotado ANTES do body, mas ancorado embaixo,
        # assim ele reserva seu espaco e o body scrollavel ocupa o resto
        footer = ctk.CTkFrame(win, fg_color=COL_BG)
        footer.pack(side="bottom", fill="x", padx=24, pady=(8, 18))

        # Corpo scrollavel — ocupa todo o espaco restante entre header e footer
        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(side="top", fill="both", expand=True, padx=0, pady=0)
        body.grid_columnconfigure(0, weight=1)

        # API Key
        ctk.CTkLabel(body, text="Chave da API do Modrinth (opcional)", text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=24)
        api_entry = ctk.CTkEntry(body, width=500, height=36, fg_color=COL_PANEL_2, border_color=COL_BORDER, show="•")
        api_entry.pack(fill="x", padx=24, pady=(4, 4))
        api_entry.insert(0, self.cfg.get("api_key", ""))
        ctk.CTkLabel(
            body, text="Só é necessária para ações vinculadas à sua conta. Busca e download funcionam sem ela.",
            text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=11), wraplength=500, justify="left"
        ).pack(anchor="w", padx=24, pady=(0, 10))

        # Pasta de mods
        ctk.CTkLabel(body, text="Pasta de mods", text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=24)
        mods_row = ctk.CTkFrame(body, fg_color="transparent")
        mods_row.pack(fill="x", padx=24, pady=(4, 10))
        mods_var = ctk.StringVar(value=self.mods_folder)
        mods_entry = ctk.CTkEntry(mods_row, textvariable=mods_var, height=36, fg_color=COL_PANEL_2, border_color=COL_BORDER)
        mods_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            mods_row, text="Escolher pasta...", width=130, fg_color=COL_PANEL_2, hover_color=COL_BORDER,
            command=lambda: self._pick_folder(mods_var)
        ).pack(side="left")

        # Pasta de resource packs
        ctk.CTkLabel(body, text="Pasta de resource packs", text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=24)
        rp_row = ctk.CTkFrame(body, fg_color="transparent")
        rp_row.pack(fill="x", padx=24, pady=(4, 10))
        rp_var = ctk.StringVar(value=self.rp_folder)
        rp_entry = ctk.CTkEntry(rp_row, textvariable=rp_var, height=36, fg_color=COL_PANEL_2, border_color=COL_BORDER)
        rp_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            rp_row, text="Escolher pasta...", width=130, fg_color=COL_PANEL_2, hover_color=COL_BORDER,
            command=lambda: self._pick_folder(rp_var)
        ).pack(side="left")

        sep = ctk.CTkFrame(body, height=1, fg_color=COL_BORDER)
        sep.pack(fill="x", padx=24, pady=(10, 14))

        ctk.CTkLabel(
            body, text="Servidor Purpur (opcional — só para Plugins)", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=24, pady=(0, 8))

        srv = self.server_cfg

        def labeled_entry(parent, label, value="", show=None):
            ctk.CTkLabel(parent, text=label, text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=24)
            e = ctk.CTkEntry(parent, height=32, fg_color=COL_PANEL_2, border_color=COL_BORDER, show=show)
            e.pack(fill="x", padx=24, pady=(4, 8))
            if value:
                e.insert(0, str(value))
            return e

        host_entry = labeled_entry(body, "Host / IP do servidor", srv.get("host", ""))
        port_entry = labeled_entry(body, "Porta SFTP", srv.get("port", 22))
        user_entry = labeled_entry(body, "Usuário", srv.get("user", ""))
        pass_entry = labeled_entry(body, "Senha (ou deixe em branco se usar chave)", srv.get("password", ""), show="•")

        key_row = ctk.CTkFrame(body, fg_color="transparent")
        ctk.CTkLabel(body, text="Caminho da chave privada (opcional)", text_color=COL_TEXT_DIM, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=24)
        key_row.pack(fill="x", padx=24, pady=(4, 8))
        key_var = ctk.StringVar(value=srv.get("key_path", ""))
        key_entry = ctk.CTkEntry(key_row, textvariable=key_var, height=32, fg_color=COL_PANEL_2, border_color=COL_BORDER)
        key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            key_row, text="Escolher...", width=100, fg_color=COL_PANEL_2, hover_color=COL_BORDER,
            command=lambda: self._pick_file(key_var)
        ).pack(side="left")

        plugins_path_entry = labeled_entry(body, "Pasta de plugins no servidor", srv.get("plugins_path", "/plugins"))

        if not PARAMIKO_OK:
            ctk.CTkLabel(
                body, text="⚠ paramiko não instalado — envio via SFTP não vai funcionar até rodar: pip install paramiko",
                text_color="#e0a020", font=ctk.CTkFont(size=11), wraplength=500, justify="left"
            ).pack(anchor="w", padx=24, pady=(0, 8))

        # espaco extra no final do scroll pra nao ficar colado
        ctk.CTkLabel(body, text="", height=1).pack(pady=(0, 10))

        def save_and_close():
            self.mods_folder = mods_var.get().strip()
            self.rp_folder = rp_var.get().strip()
            self.client.set_api_key(api_entry.get().strip())

            self.server_cfg = {
                "host": host_entry.get().strip(),
                "port": port_entry.get().strip() or "22",
                "user": user_entry.get().strip(),
                "password": pass_entry.get().strip(),
                "key_path": key_var.get().strip(),
                "plugins_path": plugins_path_entry.get().strip() or "/plugins",
            }

            self.cfg.update({
                "api_key": api_entry.get().strip(),
                "mods_folder": self.mods_folder,
                "rp_folder": self.rp_folder,
                "server": self.server_cfg,
                "last_version": self.version_entry.get().strip() if hasattr(self, "version_entry") else "",
            })
            save_config(self.cfg)
            self._update_path_label()
            win.destroy()

        # Botao de salvar, dentro do footer ja criado (fixo embaixo) no inicio do metodo
        ctk.CTkButton(
            footer, text="Salvar configurações", height=42, fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOVER,
            text_color="#0b0d0e", font=ctk.CTkFont(size=14, weight="bold"), command=save_and_close
        ).pack(fill="x")

        win.update_idletasks()
        win.grab_set()

    def _pick_folder(self, var: ctk.StringVar):
        path = filedialog.askdirectory(title="Escolha a pasta")
        if path:
            var.set(path)

    def _pick_file(self, var: ctk.StringVar):
        path = filedialog.askopenfilename(title="Escolha o arquivo de chave privada")
        if path:
            var.set(path)


if __name__ == "__main__":
    app = YzkModLoaderApp()
    app.mainloop()
