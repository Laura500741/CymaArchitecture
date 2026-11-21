# CymaArchitecture

Motor de **cimática** que transforma os modos de vibração de placas retangulares em
**padrões de Chladni vetoriais**, exportados em **SVG** e **DXF** prontos para corte laser/CNC,
fresagem ou desenho técnico. Inclui uma interface web responsiva (Streamlit) que funciona
no computador e no telemóvel, através do navegador.

---

## Como funciona

```
Placa (dimensões, material, contorno)
   └─► Física Kirchhoff-Love ─► campo de deslocamento
         └─► Marching Squares ─► linhas nodais contínuas
               └─► Geometria neutra (camadas) ─► SVG / DXF
```

1. **Física** (`src/cymaarchitecture/cymatics/`)
   - Placa fina isotrópica (teoria de Kirchhoff-Love), rigidez `D = E·h³ / 12(1−ν²)`.
   - **Simplesmente apoiada**: modos e frequências exatos.
   - **Livre** (experiência clássica de Chladni): aproximação por funções cosseno, com pares
     simétricos/antissimétricos nas placas quadradas.
   - Resposta forçada por sobreposição modal com amortecimento (excitação no centro).
   - Solver numérico de diferenças finitas para validar a solução analítica.
2. **Linhas nodais**: Marching Squares com tratamento de pontos de sela e ligação dos
   segmentos em polilinhas contínuas, sem traços soltos.
3. **Geometria** (`src/cymaarchitecture/geometry/`): primitivas imutáveis (`Point2D`,
   `Polyline2D`, `GeometryLayer`, `GeometryDocument`) e simplificação Ramer-Douglas-Peucker.
4. **Áudio** (`src/audio_module/`, isolado do motor físico)
   - Lê `.wav` (biblioteca padrão) e `.mp3`/`.ogg` (via `soundfile`).
   - FFT com janela de Hann (`scipy.fft`, ou `numpy.fft` se o scipy não estiver instalado).
   - **Fundamental** por soma harmónica ponderada, que evita erros de oitava. Também deteta
     **picos** com nome da nota (ex.: `A4 +3¢`) e calcula a **assinatura média** da faixa
     pelo método de Welch.
   - As frequências obtidas são injetadas no solver como resposta forçada. Com vários picos,
     gera um **padrão composto**: a soma das respostas, ponderada pela energia espectral de
     cada pico.
5. **Exportação** (código próprio, sem bibliotecas externas)
   - **SVG** em escala real (mm, cm ou polegadas), uma camada `<g>` por layer.
   - **DXF AutoCAD 2000 (AC1015)** com camadas `PLATE_OUTLINE` e `NODAL_LINES` (`LWPOLYLINE`).

## Métricas validadas

| Verificação | Resultado |
|---|---|
| Solver numérico vs. solução analítica (placa apoiada 300×200×1 mm, 6 primeiros modos) | erro máximo **0,32 %** |
| Geração em lote (`main.py`): 10 padrões, 20 ficheiros SVG + DXF | **~3 s** num portátil comum |
| Deteção de picos de áudio (tom puro de 440 Hz, trecho de 0,5 s) | erro **< 0,5 Hz** |
| Fundamental de um tom de 110 Hz com o 2.º harmónico mais forte | **110 Hz** detetado, sem erro de oitava |
| Testes automáticos (`pytest`) | **77 testes** a passar |

**Limitações a ter em conta**

- Nas placas **livres**, a forma das linhas nodais é correta, mas as frequências são
  aproximadas (podem desviar ~10–20 % de medições reais).
- A madeira é tratada como material isotrópico (aproximação).
- O DXF foi validado estruturalmente pelos testes. Faça uma peça de teste no seu CAD/CAM
  antes de avançar para produção.
- Por agora só são suportadas placas retangulares.

---

## Executar localmente

Requisitos: **Python 3.10 ou superior**.

```powershell
cd "C:\Users\pc\OneDrive\Documentos\LAURA\02_APP CINEMATICA\CymaArchitecture"
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

O navegador abre em `http://localhost:8501`.

### Abrir no telemóvel (mesma rede Wi-Fi)

```powershell
python -m streamlit run app.py --server.address 0.0.0.0
```

No telemóvel, abra `http://<IP-do-computador>:8501`. Para descobrir o IP, use `ipconfig`
(linha "Endereço IPv4"). Se o Windows perguntar, autorize o Python na firewall para redes privadas.

### Outros comandos

```powershell
python main.py                     # pipeline completa: valida o solver e exporta para saida/
python -m pip install pytest
python -m pytest                   # corre a suíte de testes
python src/prospeccao_mercado.py   # relatório de prospeção de mercado (MD + CSV em saida/)
python criarprojeto.py --check     # verifica a estrutura de pastas
```

---

## Usar a interface

Na barra lateral escolha o **modo de análise**. No telemóvel, a barra lateral abre-se no
botão **›** do canto superior esquerdo.

| Modo | O que faz |
|---|---|
| 🎛️ **Manual (Chladni)** | Escolhe um modo ressonante ou uma frequência em Hz. |
| 🎵 **Áudio / acorde específico** | Carrega um áudio, que pode ouvir na página. Seleciona um trecho, deteta a fundamental (ou o pico dominante) e injeta essa frequência na placa. |
| 📊 **Assinatura média da obra** | Analisa a faixa inteira, encontra os N picos de maior energia e gera um padrão composto. |

Nos modos de áudio, o **espectro de frequências** (Hz × amplitude) aparece antes da exportação,
com os picos e as notas assinalados. Pode **transpor por oitavas** para aproximar as frequências
musicais das ressonâncias da placa.

Passos comuns a todos os modos:

1. **Placa**: largura, altura e espessura (mm), material (latão, alumínio, aço, madeira) e
   condição de contorno.
2. **Excitação**: escolha um **modo ressonante** da lista (com a frequência correspondente) ou
   introduza uma **frequência livre** em Hz.
3. **Resultado**: pré-visualização imediata das linhas nodais (SVG) e do campo de deslocamento,
   com frequência, modo dominante, número de linhas e comprimento total de corte.
4. **Descarregar**: botões para os ficheiros `.svg` e `.dxf`, na unidade escolhida.

---

## Publicar online

O projeto já está pronto a publicar: `app.py` adiciona `src/` ao caminho de importação e
`requirements.txt` lista as dependências (`numpy`, `streamlit`, `scipy` e `soundfile`).
O `soundfile` já traz a libsndfile com suporte de MP3/OGG, por isso não é preciso instalar ffmpeg.

### Streamlit Community Cloud (gratuito)

1. Crie um repositório no GitHub e envie a pasta do projeto (sem a pasta `saida/`, se preferir).
2. Entre em <https://share.streamlit.io> com a sua conta GitHub.
3. Clique em **Create app** e escolha o repositório, o branch e o ficheiro principal `app.py`.
4. Clique em **Deploy**. Recebe um endereço `https://<nome>.streamlit.app`, que abre em
   qualquer computador ou telemóvel.

### Render

1. Envie o projeto para o GitHub.
2. Em <https://render.com>, crie um **New → Web Service** ligado ao repositório.
3. Configure:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
4. Clique em **Create Web Service**.

---

## Estrutura do projeto

```text
CymaArchitecture/
├── app.py                  # Interface web (Streamlit)
├── main.py                 # Pipeline de demonstração em linha de comandos
├── criarprojeto.py         # Criação/verificação da estrutura
├── requirements.txt        # Dependências para publicação
├── pyproject.toml          # Configuração do pacote
├── saida/                  # Ficheiros exportados
├── tests/                  # Testes pytest
└── src/
    ├── prospeccao_mercado.py
    ├── audio_module/       # loader (wav/mp3/ogg) e analysis (FFT, picos, fundamental)
    └── cymaarchitecture/
        ├── cymatics/       # rectangularplate, solver, batch_generator
        └── geometry/       # primitives, adapters/, exporters/ (SVG, DXF)
```
