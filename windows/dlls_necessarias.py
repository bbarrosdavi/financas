"""Copia de uma pasta só os executáveis pedidos e as DLLs que eles carregam (a cadeia inteira de importação).

    python windows/dlls_necessarias.py <origem> <destino> pdftotext.exe pdftoppm.exe

O poppler e o tesseract do Windows vêm com dezenas de ferramentas e bibliotecas que a leitura de .pdf e o OCR
não usam (o tesseract traz até as de treino, com o ICU). Lê a tabela de importação de cada PE (normal e com
carga atrasada) e segue as DLLs que existem na pasta; as do sistema ficam de fora.
"""

import shutil
import sys
from pathlib import Path

import pefile


def necessarias(origem: Path, exes: list[str]) -> list[Path]:
    locais = {p.name.lower(): p for p in origem.iterdir() if p.is_file()}
    fila, vistos = [e.lower() for e in exes], set()
    while fila:
        nome = fila.pop()
        if nome in vistos or nome not in locais:
            continue
        vistos.add(nome)
        pe = pefile.PE(str(locais[nome]), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                               pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        for entrada in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) + getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", []):
            fila.append(entrada.dll.decode().lower())
        pe.close()
    return sorted(locais[n] for n in vistos)


def main() -> None:
    origem, destino, exes = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    destino.mkdir(parents=True, exist_ok=True)
    arquivos = necessarias(origem, exes)
    for f in arquivos:
        shutil.copy2(f, destino / f.name)
    total = sum(f.stat().st_size for f in origem.iterdir() if f.is_file() and f.suffix.lower() in (".exe", ".dll"))
    copiado = sum(f.stat().st_size for f in arquivos)
    print(f"{len(arquivos)} arquivos, {copiado / 1e6:.1f} MB (a pasta tinha {total / 1e6:.1f} MB em .exe e .dll)")


if __name__ == "__main__":
    main()
