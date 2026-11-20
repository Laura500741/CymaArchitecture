"""Prospeção de mercado do CymaArchitecture: perfis de cliente ideal (ICP).

Estrutura e categoriza os segmentos-alvo do motor de cimática + exportação CAD,
pontua-os segundo critérios de abordagem comercial e gera um relatório em
Markdown e/ou CSV na pasta ``saida/``.

As pontuações (1 a 5) são HIPÓTESES de trabalho para priorizar a prospeção;
devem ser validadas com entrevistas e dados reais de vendas.

Uso:
    python src/prospeccao_mercado.py                 # gera .md e .csv
    python src/prospeccao_mercado.py --formato md    # só Markdown
    python src/prospeccao_mercado.py --saida outra/pasta
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

__all__ = [
    "CRITERIOS",
    "CAPACIDADES_DO_PRODUTO",
    "LIMITACOES_A_COMUNICAR",
    "PerfilCliente",
    "PERFIS",
    "perfis_priorizados",
    "gerar_markdown",
    "gerar_csv",
    "exportar_relatorio",
]

PASTA_SAIDA_PADRAO = Path(__file__).resolve().parent.parent / "saida"

# Critérios de qualificação comercial e respetivo peso na pontuação final.
CRITERIOS: dict[str, tuple[str, float]] = {
    "aderencia_tecnica": ("Aderência técnica (usa vetores/CAD e padrões no dia a dia)", 0.35),
    "potencial_recorrencia": ("Potencial de uso recorrente / licença contínua", 0.25),
    "facilidade_acesso": ("Facilidade de chegar ao decisor", 0.20),
    "ciclo_venda_curto": ("Ciclo de venda curto (decisão rápida, pouca burocracia)", 0.20),
}

# Factos verificáveis do produto (medidos na pipeline atual: main.py e testes).
CAPACIDADES_DO_PRODUTO: tuple[str, ...] = (
    "Precisão modal: o solver numérico Kirchhoff-Love coincide com a solução analítica "
    "com erro < 0,5 % nos 6 primeiros modos (placa apoiada).",
    "Automação de vetores: 20 ficheiros SVG + DXF gerados em ~3 segundos num portátil comum.",
    "Linhas nodais contínuas (marching squares com junção de segmentos), prontas para corte, "
    "sem limpeza manual de traços.",
    "Exportação em escala real (mm, cm, m, polegadas): SVG para design/laser e DXF AutoCAD 2000 por camadas.",
    "Geração em lote: varrimentos de frequência e séries de modos ressonantes numa só execução.",
    "Parâmetros físicos reais: dimensões, espessura, material (E, densidade, Poisson) e condição de bordo.",
)

# Transparência comercial: o que NÃO prometer.
LIMITACOES_A_COMUNICAR: tuple[str, ...] = (
    "Placas de bordo livre usam uma aproximação clássica: a topologia das linhas nodais é correta, "
    "mas as frequências podem desviar ~10-20 % de medições reais.",
    "O DXF foi validado estruturalmente; recomenda-se um teste no CAD/CAM do cliente antes de produção.",
    "O motor gera padrões de placas retangulares; outras formas exigem desenvolvimento adicional.",
)


@dataclass(frozen=True)
class PerfilCliente:
    """Perfil de cliente ideal (ICP) com critérios de abordagem comercial."""

    codigo: str
    segmento: str
    descricao: str
    decisores: tuple[str, ...]
    dores: tuple[str, ...]
    como_resolvemos: tuple[str, ...]
    sinais_de_qualificacao: tuple[str, ...]
    canais_de_abordagem: tuple[str, ...]
    argumentos_de_venda: tuple[str, ...]
    objecoes_e_respostas: tuple[tuple[str, str], ...]
    formatos_chave: tuple[str, ...]
    notas: dict[str, int]  # critério -> 1..5

    def __post_init__(self) -> None:
        if set(self.notas) != set(CRITERIOS):
            raise ValueError(f"{self.codigo}: notas devem cobrir exatamente {sorted(CRITERIOS)}")
        for criterio, nota in self.notas.items():
            if not 1 <= nota <= 5:
                raise ValueError(f"{self.codigo}: nota de '{criterio}' fora de 1..5: {nota}")

    @property
    def pontuacao(self) -> float:
        """Pontuação ponderada de 1 a 5."""
        return round(sum(self.notas[c] * peso for c, (_, peso) in CRITERIOS.items()), 2)

    @property
    def prioridade(self) -> str:
        if self.pontuacao >= 4.0:
            return "A - abordar já"
        if self.pontuacao >= 3.3:
            return "B - nutrir"
        return "C - oportunista"


PERFIS: tuple[PerfilCliente, ...] = (
    PerfilCliente(
        codigo="ICP-01",
        segmento="Oficinas de corte a laser / CNC",
        descricao="Pequenas e médias oficinas de corte e gravação (laser, fresadora CNC, jato de água) "
        "que vendem peças decorativas, sinalética e trabalhos à medida.",
        decisores=("Proprietário / gerente", "Responsável de CAM / preparação de ficheiros"),
        dores=(
            "Horas perdidas a vetorizar e limpar desenhos antes de cortar.",
            "Catálogo de padrões genérico, igual ao da concorrência.",
            "Ficheiros de clientes com traços abertos ou duplicados que falham no CAM.",
        ),
        como_resolvemos=(
            "Gera padrões únicos já vetorizados, contínuos e em escala real em segundos.",
            "DXF por camadas (contorno vs. linhas nodais) pronto para atribuir operações de corte/gravação.",
            "Lotes de dezenas de variações para montar um catálogo próprio.",
        ),
        sinais_de_qualificacao=(
            "Vende produtos decorativos ou personalizados online (Etsy, loja própria, Instagram).",
            "Tem pelo menos uma máquina laser/CNC com fluxo SVG ou DXF.",
            "Procura diferenciação por design, não só por preço.",
        ),
        canais_de_abordagem=(
            "Grupos e fóruns de makers / laser (Facebook, Reddit, comunidades LightBurn).",
            "Feiras de fabrico digital e makerspaces/fablabs locais.",
            "Contacto direto com amostra física cortada a partir de um padrão Chladni.",
        ),
        argumentos_de_venda=(
            "\"Do som ao corte em segundos: padrões exclusivos sem horas de vetorização.\"",
            "Uma coleção de produtos com história (física real do som) que justifica preço premium.",
            "Ficheiros que entram direto no CAM, sem retrabalho.",
        ),
        objecoes_e_respostas=(
            ("Já tenho bibliotecas de padrões grátis.",
             "São iguais para todos; aqui cada frequência/material gera um padrão próprio e reproduzível."),
            ("O meu software CAM é exigente com DXF.",
             "Fazemos um teste piloto com o seu CAM antes de qualquer compromisso."),
        ),
        formatos_chave=("DXF", "SVG"),
        notas={"aderencia_tecnica": 5, "potencial_recorrencia": 4, "facilidade_acesso": 5, "ciclo_venda_curto": 5},
    ),
    PerfilCliente(
        codigo="ICP-02",
        segmento="Fabricantes de painéis acústicos decorativos",
        descricao="Empresas que produzem painéis acústicos em madeira, MDF, feltro PET ou gesso perfurado "
        "para escritórios, hotelaria, auditórios e residências.",
        decisores=("Diretor de produto / design", "Engenharia de produto", "Diretor comercial"),
        dores=(
            "Pressão para lançar coleções novas com frequência e com narrativa de marca.",
            "Desenvolvimento de novos padrões de perfuração/fresagem lento e manual.",
            "Dificuldade em ligar estética a um conceito acústico credível.",
        ),
        como_resolvemos=(
            "Padrões derivados de modos de vibração reais com precisão modal verificada (< 0,5 % no solver).",
            "Variações em lote por frequência para explorar coleções inteiras numa tarde.",
            "Saída DXF em escala real, pronta para fresagem CNC.",
        ),
        sinais_de_qualificacao=(
            "Lança pelo menos uma coleção por ano.",
            "Produz com CNC/laser interno.",
            "Já comunica design ou sustentabilidade como diferencial.",
        ),
        canais_de_abordagem=(
            "LinkedIn (diretores de produto e design).",
            "Feiras de interiores e construção (ex.: Orgatec, Clerkenwell Design Week, feiras nacionais).",
            "Proposta de coleção-piloto co-desenvolvida, com amostras.",
        ),
        argumentos_de_venda=(
            "\"Coleções com assinatura física: cada painel nasce de uma frequência real.\"",
            "Reduz semanas de desenvolvimento de padrões para horas.",
            "Narrativa de marketing forte: cimática, som e arquitetura no mesmo objeto.",
        ),
        objecoes_e_respostas=(
            ("O padrão melhora a absorção acústica?",
             "O padrão é de origem física e estética; o desempenho acústico depende da perfuração/material "
             "e deve ser ensaiado como em qualquer painel."),
            ("Temos designers internos.",
             "A ferramenta multiplica a produção deles: geram e escolhem, em vez de desenhar à mão."),
        ),
        formatos_chave=("DXF",),
        notas={"aderencia_tecnica": 5, "potencial_recorrencia": 5, "facilidade_acesso": 3, "ciclo_venda_curto": 3},
    ),
    PerfilCliente(
        codigo="ICP-03",
        segmento="Designers paramétricos / computacionais",
        descricao="Designers e arquitetos que trabalham com Grasshopper, Rhino, Houdini ou código "
        "para gerar forma a partir de regras e dados.",
        decisores=("O próprio designer (freelancer)", "Líder de design computacional em gabinetes"),
        dores=(
            "Construir e validar um simulador de placas do zero é demorado e propenso a erros.",
            "Padrões 'pseudo-Chladni' feitos com fórmulas simplificadas sem rigor físico.",
            "Converter campos escalares em curvas limpas exige scripts próprios.",
        ),
        como_resolvemos=(
            "Biblioteca Python modular com física Kirchhoff-Love validada por testes automáticos.",
            "API neutra (Point2D, Polyline2D, camadas) fácil de ligar a outras ferramentas.",
            "Exportação SVG/DXF imediata para seguir no Rhino/Illustrator.",
        ),
        sinais_de_qualificacao=(
            "Portefólio com trabalho generativo/paramétrico.",
            "Programa em Python ou usa scripting visual.",
            "Publica processos e experiências (Instagram, Behance, GitHub).",
        ),
        canais_de_abordagem=(
            "Comunidades Grasshopper/Food4Rhino, GitHub e Discord de design computacional.",
            "Workshops e webinars técnicos com demonstração ao vivo.",
            "Conteúdo técnico (artigos, vídeos curtos de som -> vetor).",
        ),
        argumentos_de_venda=(
            "\"Física real, não aproximação visual: modos validados contra a solução analítica.\"",
            "Poupa semanas de desenvolvimento de um solver próprio.",
            "Código aberto à integração, com testes que garantem os resultados.",
        ),
        objecoes_e_respostas=(
            ("Consigo programar isto sozinho.",
             "Sim, mas o solver, o marching squares e os exportadores já estão testados; foque-se no design."),
            ("Preciso de outras formas além de retângulos.",
             "É uma limitação atual; recolhemos esse pedido para o roadmap."),
        ),
        formatos_chave=("SVG", "DXF", "API Python"),
        notas={"aderencia_tecnica": 5, "potencial_recorrencia": 3, "facilidade_acesso": 4, "ciclo_venda_curto": 4},
    ),
    PerfilCliente(
        codigo="ICP-04",
        segmento="Estúdios de arquitetura de interiores",
        descricao="Gabinetes de interiores e arquitetura que especificam revestimentos, divisórias, "
        "tetos e peças à medida para projetos residenciais, comerciais e de hotelaria.",
        decisores=("Sócio / diretor criativo", "Arquiteto de projeto"),
        dores=(
            "Clientes exigem elementos exclusivos e com conceito.",
            "Desenvolver um padrão à medida e passá-lo a produção consome tempo do projeto.",
            "Falta de ficheiros técnicos fiáveis para enviar ao fabricante.",
        ),
        como_resolvemos=(
            "Padrões únicos ligados a um conceito (ex.: a frequência associada ao cliente ou ao espaço).",
            "Ficheiros DXF em escala real para orçamentar e produzir com o fabricante.",
            "Iterações rápidas em reunião: variações em segundos.",
        ),
        sinais_de_qualificacao=(
            "Projetos de hotelaria, retalho ou residencial de gama alta.",
            "Já especificou painéis, biombos ou tetos decorativos.",
            "Trabalha com fabricantes CNC/laser parceiros.",
        ),
        canais_de_abordagem=(
            "Apresentação de portefólio com amostras físicas (materioteca).",
            "Parcerias com fabricantes (ICP-01 e ICP-02) que levam a solução ao gabinete.",
            "Eventos de design de interiores e ordens/associações profissionais.",
        ),
        argumentos_de_venda=(
            "\"Um padrão que conta a história do espaço: som transformado em arquitetura.\"",
            "Exclusividade demonstrável: cada padrão é reproduzível a partir dos seus parâmetros.",
            "Ficheiros prontos para o fabricante, menos idas e voltas.",
        ),
        objecoes_e_respostas=(
            ("Não temos tempo para aprender software novo.",
             "Oferecemos o padrão como serviço por projeto, ou formação curta."),
            ("O cliente final precisa de ver antes.",
             "SVG imediato para apresentação e amostra física via fabricante parceiro."),
        ),
        formatos_chave=("SVG", "DXF"),
        notas={"aderencia_tecnica": 3, "potencial_recorrencia": 3, "facilidade_acesso": 3, "ciclo_venda_curto": 3},
    ),
    PerfilCliente(
        codigo="ICP-05",
        segmento="Designers de produto, joalharia e arte",
        descricao="Criadores independentes que produzem objetos, joias, gravuras ou instalações "
        "a partir de processos generativos ou ligados ao som.",
        decisores=("O próprio criador",),
        dores=(
            "Querem ligar som e forma de modo autêntico, sem ferramentas técnicas acessíveis.",
            "Vetorizar imagens de experiências físicas de Chladni é impreciso.",
        ),
        como_resolvemos=(
            "Padrões limpos a partir de parâmetros físicos, em qualquer escala.",
            "SVG direto para gravação, impressão ou corte.",
        ),
        sinais_de_qualificacao=(
            "Trabalho com tema de som, música ou geometria.",
            "Vende peças personalizadas (ex.: a 'frequência' de um nome ou data).",
        ),
        canais_de_abordagem=(
            "Instagram/TikTok com vídeos de processo.",
            "Marketplaces de criadores e residências artísticas.",
        ),
        argumentos_de_venda=(
            "\"Transforme frequências em peças únicas, com a física por trás de cada linha.\"",
            "Personalização escalável: cada encomenda, um padrão novo em segundos.",
        ),
        objecoes_e_respostas=(
            ("É caro para um criador independente.",
             "Plano de entrada ou pagamento por pacote de padrões."),
        ),
        formatos_chave=("SVG",),
        notas={"aderencia_tecnica": 4, "potencial_recorrencia": 2, "facilidade_acesso": 4, "ciclo_venda_curto": 5},
    ),
    PerfilCliente(
        codigo="ICP-06",
        segmento="Ensino e investigação (arquitetura, design, acústica)",
        descricao="Faculdades, escolas de design e laboratórios que ensinam vibração, acústica ou fabrico digital.",
        decisores=("Docente / coordenador de curso", "Responsável de fablab"),
        dores=(
            "Demonstrar modos de vibração de forma visual e ligada ao fabrico.",
            "Ferramentas de simulação comerciais caras e complexas para aulas.",
        ),
        como_resolvemos=(
            "Solver transparente e validado contra a solução analítica, ideal para ensino.",
            "Liga teoria (Kirchhoff-Love) a objetos físicos cortados no fablab.",
        ),
        sinais_de_qualificacao=(
            "Unidades curriculares de acústica, estruturas ou fabrico digital.",
            "Fablab com laser/CNC.",
        ),
        canais_de_abordagem=(
            "Contacto direto com docentes e propostas de workshop.",
            "Conferências académicas de design computacional e acústica.",
        ),
        argumentos_de_venda=(
            "\"Da equação à peça cortada numa só aula.\"",
            "Licença de turma e materiais didáticos.",
        ),
        objecoes_e_respostas=(
            ("Processos de compra lentos.",
             "Começar com workshop pago ou licença académica de baixo valor."),
        ),
        formatos_chave=("SVG", "DXF", "API Python"),
        notas={"aderencia_tecnica": 4, "potencial_recorrencia": 3, "facilidade_acesso": 3, "ciclo_venda_curto": 2},
    ),
)


def perfis_priorizados(perfis: tuple[PerfilCliente, ...] = PERFIS) -> list[PerfilCliente]:
    """Perfis ordenados por pontuação decrescente (desempate pelo código)."""
    return sorted(perfis, key=lambda p: (-p.pontuacao, p.codigo))


# ------------------------------------------------------------------ relatórios
def _lista(itens: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in itens)


def gerar_markdown(perfis: tuple[PerfilCliente, ...] = PERFIS, data: date | None = None) -> str:
    data = data or date.today()
    ordenados = perfis_priorizados(perfis)
    linhas = [
        "# CymaArchitecture — Prospeção de Mercado e Perfis de Cliente Ideal",
        "",
        f"_Gerado em {data.isoformat()} por `src/prospeccao_mercado.py`._",
        "",
        "> As pontuações são hipóteses de trabalho para priorizar a prospeção. "
        "Valide-as com entrevistas e dados reais.",
        "",
        "## Proposta de valor",
        "",
        "Motor de cimática que transforma modos de vibração de placas (física Kirchhoff-Love) "
        "em vetores SVG/DXF prontos para produção — **precisão modal** e **automação de vetores em segundos**.",
        "",
        "### Capacidades verificáveis",
        "",
        _lista(CAPACIDADES_DO_PRODUTO),
        "",
        "### Limitações a comunicar com transparência",
        "",
        _lista(LIMITACOES_A_COMUNICAR),
        "",
        "## Critérios de priorização",
        "",
        "| Critério | Peso |",
        "|---|---|",
        *[f"| {nome} | {peso:.0%} |" for nome, peso in CRITERIOS.values()],
        "",
        "## Ranking de segmentos",
        "",
        "| # | Código | Segmento | " + " | ".join(n.split(" (")[0] for n, _ in CRITERIOS.values())
        + " | Pontuação | Prioridade |",
        "|---|---|---|" + "---|" * len(CRITERIOS) + "---|---|",
    ]
    for i, p in enumerate(ordenados, start=1):
        notas = " | ".join(str(p.notas[c]) for c in CRITERIOS)
        linhas.append(f"| {i} | {p.codigo} | {p.segmento} | {notas} | **{p.pontuacao:.2f}** | {p.prioridade} |")
    linhas.append("")

    for p in ordenados:
        linhas += [
            f"## {p.codigo} — {p.segmento}",
            "",
            f"**Pontuação:** {p.pontuacao:.2f} · **Prioridade:** {p.prioridade} · "
            f"**Formatos-chave:** {', '.join(p.formatos_chave)}",
            "",
            p.descricao,
            "",
            "**Decisores:** " + "; ".join(p.decisores),
            "",
            "### Dores do cliente",
            _lista(p.dores),
            "",
            "### Como o CymaArchitecture resolve",
            _lista(p.como_resolvemos),
            "",
            "### Sinais de qualificação",
            _lista(p.sinais_de_qualificacao),
            "",
            "### Canais de abordagem",
            _lista(p.canais_de_abordagem),
            "",
            "### Argumentos de venda",
            _lista(p.argumentos_de_venda),
            "",
            "### Objeções e respostas",
            *[f"- **“{o}”** → {r}" for o, r in p.objecoes_e_respostas],
            "",
        ]
    return "\n".join(linhas)


COLUNAS_CSV = (
    "prioridade_rank", "codigo", "segmento", "pontuacao", "prioridade",
    *CRITERIOS.keys(),
    "descricao", "decisores", "dores", "como_resolvemos", "sinais_de_qualificacao",
    "canais_de_abordagem", "argumentos_de_venda", "objecoes_e_respostas", "formatos_chave",
)


def gerar_csv(caminho: Path, perfis: tuple[PerfilCliente, ...] = PERFIS) -> Path:
    """CSV com ';' e UTF-8 com BOM (abre corretamente no Excel em português)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(COLUNAS_CSV)
        for rank, p in enumerate(perfis_priorizados(perfis), start=1):
            writer.writerow([
                rank, p.codigo, p.segmento, f"{p.pontuacao:.2f}".replace(".", ","), p.prioridade,
                *(p.notas[c] for c in CRITERIOS),
                p.descricao,
                " | ".join(p.decisores),
                " | ".join(p.dores),
                " | ".join(p.como_resolvemos),
                " | ".join(p.sinais_de_qualificacao),
                " | ".join(p.canais_de_abordagem),
                " | ".join(p.argumentos_de_venda),
                " | ".join(f"{o} -> {r}" for o, r in p.objecoes_e_respostas),
                ", ".join(p.formatos_chave),
            ])
    return caminho.resolve()


def exportar_relatorio(pasta: Path = PASTA_SAIDA_PADRAO, formato: str = "ambos") -> list[Path]:
    """Gera o(s) relatório(s) em ``pasta``. ``formato``: 'md', 'csv' ou 'ambos'."""
    if formato not in ("md", "csv", "ambos"):
        raise ValueError("formato deve ser 'md', 'csv' ou 'ambos'")
    pasta.mkdir(parents=True, exist_ok=True)
    gerados: list[Path] = []
    if formato in ("md", "ambos"):
        md = pasta / "prospeccao_mercado.md"
        md.write_text(gerar_markdown(), encoding="utf-8")
        gerados.append(md.resolve())
    if formato in ("csv", "ambos"):
        gerados.append(gerar_csv(pasta / "prospeccao_mercado.csv"))
    return gerados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Relatório de prospeção de mercado do CymaArchitecture")
    parser.add_argument("--formato", choices=("md", "csv", "ambos"), default="ambos")
    parser.add_argument("--saida", type=Path, default=PASTA_SAIDA_PADRAO)
    args = parser.parse_args(argv)

    for p in perfis_priorizados():
        print(f"{p.codigo}  {p.pontuacao:.2f}  {p.prioridade:<16} {p.segmento}")
    for caminho in exportar_relatorio(args.saida, args.formato):
        print(f"Gerado: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
