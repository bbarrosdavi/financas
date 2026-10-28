"""Corrige o modelo da planilha antiga (app/modelo/planilha.ods), uma vez.

Os totais do Budget Planning (linhas 20, 36 e 46) vieram do Excel como fórmulas de matriz com tamanhos
errados e encavaladas: a de Expenses ocupa as linhas 36 a 48 e engole o bloco de Savings, e a de Savings
(46:47) fica dentro dela. O LibreOffice não consegue limpar nem reescrever essas células. Aqui elas viram
fórmulas comuns (SUM(INDIRECT(...)) funciona igual fora de matriz); as outras abas ficam como estão.

    python scripts/limpar_modelo_ods.py app/modelo/planilha.ods
"""

import re
import sys
import zipfile

ATRIBUTOS = re.compile(r' table:number-matrix-(?:columns|rows)-spanned="\d+"')


def limpar(caminho: str) -> int:
    with zipfile.ZipFile(caminho) as z:
        arquivos = {n: z.read(n) for n in z.namelist()}
        ordem = z.namelist()
    xml = arquivos["content.xml"].decode("utf-8")
    ini = xml.index('<table:table table:name="Budget Planning"')
    fim = xml.index("</table:table>", ini)
    trecho, n = ATRIBUTOS.subn("", xml[ini:fim])
    arquivos["content.xml"] = (xml[:ini] + trecho + xml[fim:]).encode("utf-8")
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), arquivos["mimetype"], compress_type=zipfile.ZIP_STORED)
        for nome in ordem:
            if nome != "mimetype":
                z.writestr(nome, arquivos[nome], compress_type=zipfile.ZIP_DEFLATED)
    return n


if __name__ == "__main__":
    print(limpar(sys.argv[1]), "atributos de matriz removidos")
