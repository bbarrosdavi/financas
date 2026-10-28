# PyInstaller (onedir): o runtime Python, o app e o site numa pasta só. Rodar da raiz do repositório:
#   pyinstaller --noconfirm windows/financas.spec
# O poppler e o tesseract entram depois, copiados para dist/Financas/poppler e dist/Financas/tesseract
# (ver .github/workflows/windows.yml).
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

raiz = SPECPATH + "/.."
a = Analysis(
    [raiz + "/windows/financas_win.py"],
    pathex=[raiz],
    datas=[(raiz + "/web", "web")] + collect_data_files("tzdata"),
    hiddenimports=collect_submodules("uvicorn") + [m for m in collect_submodules("app") if m != "app.ods_preencher"] + ["tzdata"],
    excludes=["tkinter", "pytest", "app.ods_preencher"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Financas", console=False, icon=raiz + "/windows/financas.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="Financas")
